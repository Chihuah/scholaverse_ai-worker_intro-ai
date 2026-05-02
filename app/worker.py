"""Worker Loop — 串接 LLM prompt、雲端／本地生圖、上傳與 callback。"""

import asyncio
import logging
from datetime import datetime, timezone

from pathlib import Path

from app.callback import send_callback
from app.cloud_image_gen import (
    CloudImageGenError,
    generate_cloud_image,
    is_enabled as cloud_is_enabled,
)
from app.config import settings
from app.llm_service import generate_prompt, unload_model
from app.prompt_builder import (
    build_prompt_spec,
    build_style_prefix,
    render_prompt_spec_for_llm,
)
from app.prompt_builder_cloud_v2 import (
    build_prompt_spec as build_prompt_spec_cloud,
    render_prompt_spec_for_cloud_image,
)
from app.queue import JobQueue
from app.sd_runner import create_thumbnail, run_sd_cli
from app.storage_uploader import upload_images

logger = logging.getLogger(__name__)


async def _build_local_prompt(job) -> tuple[str, dict]:
    """Build the LLM-rewritten prompt for local SD via Ollama.

    Sets job.llm_model. Returns (rewritten_prompt, prompt_spec) so the caller
    can derive style_prefix / border / etc. for sd-cli from the same spec.
    """
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
    job.llm_model = active_ollama_model
    return prompt, prompt_spec


def _build_cloud_prompt(job) -> str:
    """Build a direct-to-image prompt using the cloud-optimized renderer.

    Skips Ollama entirely. Sets job.llm_model = None to make it explicit that
    no LLM rewriting layer was used.
    """
    prompt_spec = build_prompt_spec_cloud(
        job.card_config,
        job.learning_data,
        job.student_nickname,
        rng_seed=job.requested_seed,
        style_hint=job.style_hint,
    )
    job.llm_model = None
    return render_prompt_spec_for_cloud_image(prompt_spec)


async def _run_local_image(job, prompt: str, prompt_spec: dict) -> str:
    """Run sd-cli pipeline. Sets job.lora_used / job.seed / job.final_prompt
    and returns the local PNG output path."""
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
    job.backend_used = "local"
    return output_path


async def _run_cloud_image(job, prompt: str) -> str:
    """Call OpenAI gpt-image-2 (Phase 1a, generate-only). Sets cloud-related
    job fields and returns local PNG output path. Raises on failure so the
    caller can decide whether to fallback to local."""
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / f"{job.job_id}_cloud.png")

    cloud_meta = await generate_cloud_image(
        prompt=prompt,
        output_path=output_path,
        model=job.cloud_model or settings.cloud_image_model,
    )
    # Cloud has no LoRA / seed: keep null (per design)
    job.lora_used = None
    job.seed = None
    job.final_prompt = prompt
    job.backend_used = "cloud"
    job.cloud_model = cloud_meta["model"]
    job.cloud_mode = "generate"
    job.cloud_quality = cloud_meta.get("quality")
    return output_path


async def _fallback_to_local(job, reason: str) -> str:
    """Cloud → local fallback path.

    Used when:
      - backend=cloud but cloud is disabled (no API key / feature flag off)
      - backend=cloud but the OpenAI call itself failed

    Sets job.fallback_from_cloud + job.cloud_error, then runs the full local
    pipeline (Ollama prompt → unload → sd-cli). Returns the SD output path.
    """
    job.fallback_from_cloud = True
    job.cloud_error = reason
    logger.warning(
        "[fallback] cloud → local for job=%s reason=%s",
        job.job_id, reason,
    )

    logger.info("[fallback/Step 1] Generating Ollama prompt (post-cloud-failure)...")
    prompt, prompt_spec = await _build_local_prompt(job)
    job.prompt = prompt

    logger.info("[fallback/Step 1.5] Unloading Ollama to free GPU VRAM...")
    await unload_model(model_name=job.llm_model)

    logger.info("[fallback/Step 2] Running sd-cli image generation...")
    return await _run_local_image(job, prompt, prompt_spec)


def _build_upload_metadata(job) -> dict:
    """Metadata dict to attach to the db-storage upload (full image only)."""
    return {
        "prompt": job.prompt,
        "model_name": job.llm_model,
        "lora_used": job.lora_used,
        "seed": job.seed,
        "steps": settings.default_steps if job.backend_used == "local" else None,
        "cfg_scale": settings.default_cfg if job.backend_used == "local" else None,
        "width": settings.default_width if job.backend_used == "local" else None,
        "height": settings.default_height if job.backend_used == "local" else None,
        "generation_time_ms": None,  # local: not yet measured; cloud: filled below
        "generated_at": (
            job.generated_at.isoformat() if job.generated_at else None
        ),
        "backend_used": job.backend_used,
        "cloud_model": job.cloud_model,
        "cloud_mode": job.cloud_mode,
        "cloud_quality": job.cloud_quality,
        "fallback_from_cloud": job.fallback_from_cloud,
        "cloud_error": job.cloud_error,
        "reference_card_id": job.reference_card_id,
    }


async def _process_job(job) -> None:
    """Process a generation job (Steps 1~5). Wrapped with overall timeout.

    Backend selection:
      - backend=local: Ollama prompt → unload → sd-cli (unchanged from Phase 1a)
      - backend=cloud + cloud enabled: cloud-v2 prompt (no Ollama) → gpt-image-2
        - on cloud failure: fallback to local (which DOES need Ollama)
      - backend=cloud + cloud disabled: fallback to local immediately
    """
    job.status = "processing"

    output_path: str

    if job.backend == "cloud":
        if not cloud_is_enabled():
            output_path = await _fallback_to_local(
                job, "雲端生圖未啟用（enable_cloud_image_gen=False 或未設 OPENAI_API_KEY）"
            )
        else:
            logger.info("[Step 1/cloud] Building cloud prompt (skipping Ollama)...")
            cloud_prompt = _build_cloud_prompt(job)
            job.prompt = cloud_prompt
            logger.info(
                "[Step 1/cloud] Cloud prompt built (%d chars)", len(cloud_prompt)
            )

            try:
                logger.info("[Step 2/cloud] Calling gpt-image-2 ...")
                output_path = await _run_cloud_image(job, cloud_prompt)
                logger.info("[Step 2/cloud] Image generated: %s", output_path)
            except CloudImageGenError as exc:
                output_path = await _fallback_to_local(job, str(exc))
    else:
        # backend == "local"
        logger.info("[Step 1/local] Generating prompt via Ollama...")
        prompt, prompt_spec = await _build_local_prompt(job)
        job.prompt = prompt
        logger.info(
            "[Step 1/local] Prompt generated: %s",
            prompt[:100] + "..." if len(prompt) > 100 else prompt,
        )

        logger.info("[Step 1.5/local] Unloading Ollama to free GPU VRAM...")
        await unload_model(model_name=job.llm_model)

        logger.info("[Step 2/local] Running sd-cli image generation...")
        output_path = await _run_local_image(job, prompt, prompt_spec)
        logger.info(
            "[Step 2/local] Image generated: %s (lora=%s)",
            output_path, job.lora_used,
        )

    # Step 3: Generate thumbnail
    logger.info("[Step 3] Creating thumbnail...")
    thumbnail_path = await create_thumbnail(output_path)
    logger.info("[Step 3] Thumbnail created: %s", thumbnail_path)

    # Stamp generated_at BEFORE upload so metadata carries it
    job.generated_at = datetime.now(timezone.utc)

    # Step 4: Upload to vm-db-storage (with metadata)
    logger.info("[Step 4] Uploading images (backend=%s)...", job.backend_used)
    job.status = "uploading"
    metadata = _build_upload_metadata(job)
    image_paths = await upload_images(
        output_path, thumbnail_path, job.student_id, job.card_id,
        metadata=metadata,
    )
    job.image_path = image_paths["full"]
    job.thumbnail_path = image_paths["thumbnail"]
    logger.info("[Step 4] Upload complete: %s", image_paths)

    # Step 5: Callback
    job.status = "completed"
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
        "backend_used": job.backend_used,
        "cloud_model": job.cloud_model,
        "cloud_mode": job.cloud_mode,
        "cloud_quality": job.cloud_quality,
        "fallback_from_cloud": job.fallback_from_cloud,
        "cloud_error": job.cloud_error,
        "reference_card_id": job.reference_card_id,
    })

    logger.info(
        "Job %s completed (backend_used=%s, fallback=%s)",
        job.job_id, job.backend_used, job.fallback_from_cloud,
    )


async def worker_loop(queue: JobQueue) -> None:
    """主要 worker loop。從 queue 取出 job 後依序處理：

    流程：
      Step 1:   Prompt 構建（雲端：跳過 Ollama；本地：Ollama qwen2.5-14b）
      Step 1.5: 卸載 Ollama 釋放 VRAM（僅本地路徑）
      Step 2:   生圖（cloud 走 gpt-image-2；local 走 sd-cli）
      Step 3:   縮圖（Pillow）
      Step 4:   上傳到 vm-db-storage
      Step 5:   callback 回 vm-web-server

    雲端失敗時 fallback 到本地，並補呼叫 Ollama 取得 SD 可用的改寫 prompt。

    整個 job 包在 settings.overall_job_timeout（預設 600s）的 timeout 中。
    """
    logger.info("Worker loop started, waiting for jobs...")

    while True:
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
