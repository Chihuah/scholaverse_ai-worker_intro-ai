"""Worker Loop — 持續從佇列取出任務並處理，一次一張圖。"""

import asyncio
import logging
from datetime import datetime, timezone

from app.callback import send_callback
from app.config import settings
from app.llm_service import generate_prompt, unload_model
from app.prompt_builder import build_structured_description, build_style_prefix
from app.queue import JobQueue
from app.sd_runner import create_thumbnail, run_sd_cli
from app.storage_uploader import upload_images

logger = logging.getLogger(__name__)


async def _process_job(job) -> None:
    """執行單一任務的完整五步驟流程（含整體 timeout 保護）。"""
    job.status = "processing"

    # Step 1: LLM prompt generation
    logger.info("[Step 1] Generating prompt via Ollama...")
    structured_desc = build_structured_description(
        job.card_config, job.learning_data, job.student_nickname
    )
    prompt = await generate_prompt(structured_desc)
    job.prompt = prompt
    job.llm_model = settings.ollama_model
    logger.info("[Step 1] Prompt generated: %s", prompt[:100] + "..." if len(prompt) > 100 else prompt)

    # Step 1.5: Unload Ollama model to free GPU VRAM
    logger.info("[Step 1.5] Unloading Ollama model to free GPU VRAM...")
    await unload_model()

    # Step 2: sd-cli image generation
    logger.info("[Step 2] Running sd-cli image generation...")
    level = int(job.card_config.get("level", 1))
    rarity = job.card_config.get("rarity", "N")
    style_prefix = build_style_prefix(level, rarity)
    output_path, lora_tag, seed, final_prompt = await run_sd_cli(
        prompt, job.job_id, job.student_id, style_prefix
    )
    job.lora_used = lora_tag
    job.seed = seed
    job.final_prompt = final_prompt
    logger.info("[Step 2] Image generated: %s (lora=%s)", output_path, lora_tag)

    # Step 3: Generate thumbnail
    logger.info("[Step 3] Creating thumbnail...")
    thumbnail_path = await create_thumbnail(output_path)
    logger.info("[Step 3] Thumbnail created: %s", thumbnail_path)

    # Step 4: Upload to vm-db-storage
    logger.info("[Step 4] Uploading images...")
    job.status = "uploading"
    image_paths = await upload_images(
        output_path, thumbnail_path, job.student_id, job.card_id
    )
    job.image_path = image_paths["full"]
    job.thumbnail_path = image_paths["thumbnail"]
    logger.info("[Step 4] Upload complete: %s", image_paths)

    # Step 5: Callback
    job.status = "completed"
    job.generated_at = datetime.now(timezone.utc)
    logger.info("[Step 5] Sending callback to %s...", job.callback_url)

    await send_callback(job.callback_url, {
        "job_id": job.job_id,
        "card_id": job.card_id,
        "status": "completed",
        "image_path": job.image_path,
        "thumbnail_path": job.thumbnail_path,
        "generated_at": job.generated_at.isoformat(),
        "prompt": job.prompt,
        "final_prompt": job.final_prompt,
        "llm_model": job.llm_model,
        "lora_used": job.lora_used,
        "seed": job.seed,
    })

    logger.info("Job %s completed successfully", job.job_id)


async def worker_loop(queue: JobQueue) -> None:
    """持續從佇列取出任務並依序處理。

    流程：
      Step 1:   LLM prompt 生成 (Ollama)
      Step 1.5: 卸載 Ollama 模型 (keep_alive=0，釋放 VRAM)
      Step 2:   sd-cli 文生圖
      Step 3:   產生縮圖 (Pillow)
      Step 4:   上傳至 vm-db-storage（或 mock）
      Step 5:   回調 vm-web-server

    整體 timeout: settings.overall_job_timeout（預設 600s），
    防止任何單步驟掛起時整個 worker 被永久卡住。
    """
    logger.info("Worker loop started, waiting for jobs...")

    while True:
        # 從 queue 取出 job_id
        job_id = await queue._queue.get()
        job = queue.get_job(job_id)

        if job is None:
            logger.error("Job %s not found in registry, skipping", job_id)
            queue._queue.task_done()
            continue

        queue._current_job = job.job_id
        logger.info("Processing job %s (card_id=%d, student_id=%s)", job.job_id, job.card_id, job.student_id)

        try:
            await asyncio.wait_for(
                _process_job(job),
                timeout=settings.overall_job_timeout,
            )

        except asyncio.TimeoutError:
            job.status = "failed"
            job.error = f"Job timed out after {settings.overall_job_timeout}s (overall timeout)"
            logger.error(
                "Job %s timed out after %ds (overall_job_timeout)",
                job.job_id, settings.overall_job_timeout,
            )
            await send_callback(job.callback_url, {
                "job_id": job.job_id,
                "card_id": job.card_id,
                "status": "failed",
                "error": job.error,
            })

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            logger.error("Job %s failed: %s", job.job_id, e, exc_info=True)

            # 失敗也要送 callback
            await send_callback(job.callback_url, {
                "job_id": job.job_id,
                "card_id": job.card_id,
                "status": "failed",
                "error": str(e),
            })

        finally:
            queue._current_job = None
            queue._queue.task_done()
