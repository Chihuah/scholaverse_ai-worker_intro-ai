"""Worker Loop ? ???????????????????"""

import asyncio
import logging
from datetime import datetime, timezone

from app.callback import send_callback
from app.config import settings
from app.llm_service import generate_prompt, unload_model
from app.prompt_builder import (
    build_prompt_spec,
    build_style_prefix,
    render_prompt_spec_for_llm,
)
from app.queue import JobQueue
from app.sd_runner import create_thumbnail, run_sd_cli
from app.storage_uploader import upload_images

logger = logging.getLogger(__name__)


async def _process_job(job) -> None:
    """?????????????????? timeout ????"""
    job.status = "processing"

    # Step 1: LLM prompt generation
    logger.info("[Step 1] Generating prompt via Ollama...")
    prompt_spec = build_prompt_spec(
        job.card_config,
        job.learning_data,
        job.student_nickname,
        rng_seed=job.requested_seed,
        style_hint=job.style_hint,
    )
    structured_desc = render_prompt_spec_for_llm(prompt_spec)
    active_ollama_model = job.ollama_model_override or settings.ollama_model
    prompt = await generate_prompt(structured_desc, model_name=active_ollama_model)
    job.prompt = prompt
    job.llm_model = active_ollama_model
    logger.info("[Step 1] Prompt generated: %s", prompt[:100] + "..." if len(prompt) > 100 else prompt)

    # Step 1.5: Unload Ollama model to free GPU VRAM
    logger.info("[Step 1.5] Unloading Ollama model to free GPU VRAM...")
    await unload_model(model_name=active_ollama_model)

    # Step 2: sd-cli image generation
    logger.info("[Step 2] Running sd-cli image generation...")
    character_facts = prompt_spec["character_facts"]
    direction_spec = prompt_spec["direction_spec"]
    level = int(character_facts.get("level", 1))
    rarity = character_facts.get("rarity", "N")
    border = character_facts.get("border", "bronze")
    style_profile = direction_spec.get("style_profile")
    style_block = build_style_prefix(level, rarity, border=border, style_profile=style_profile)
    output_path, lora_tag, seed, final_prompt = await run_sd_cli(
        prompt, job.job_id, job.student_id, style_block, seed_override=job.requested_seed
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
    """???????????????

    ???
      Step 1:   LLM prompt ?? (Ollama)
      Step 1.5: ?? Ollama ?? (keep_alive=0??? VRAM)
      Step 2:   sd-cli ???
      Step 3:   ???? (Pillow)
      Step 4:   ??? vm-db-storage?? mock?
      Step 5:   ?? vm-web-server

    ?? timeout: settings.overall_job_timeout??? 600s??
    ???????????? worker ??????
    """
    logger.info("Worker loop started, waiting for jobs...")

    while True:
        # ? queue ?? job_id
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

            await send_callback(job.callback_url, {
                "job_id": job.job_id,
                "card_id": job.card_id,
                "status": "failed",
                "error": str(e),
            })

        finally:
            queue._current_job = None
            queue._queue.task_done()
