"""Worker Loop ? ???????????????????"""

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
from app.queue import JobQueue
from app.sd_runner import create_thumbnail, run_sd_cli
from app.storage_uploader import upload_images

logger = logging.getLogger(__name__)


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
    """Process a generation job (Steps 1~5). Wrapped with overall timeout."""
    job.status = "processing"

    # Step 1: LLM prompt generation (always; both backends use same prompt)
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
    logger.info(
        "[Step 1] Prompt generated: %s",
        prompt[:100] + "..." if len(prompt) > 100 else prompt,
    )

    # Step 1.5: Unload Ollama model to free GPU VRAM (only relevant for local)
    if job.backend == "local" or not cloud_is_enabled():
        logger.info("[Step 1.5] Unloading Ollama model to free GPU VRAM...")
        await unload_model(model_name=active_ollama_model)

    # Step 2: image generation — branch on requested backend
    output_path: str
    if job.backend == "cloud":
        if not cloud_is_enabled():
            logger.warning(
                "[Step 2/cloud] cloud requested but disabled; "
                "falling back to local. job=%s",
                job.job_id,
            )
            job.fallback_from_cloud = True
            job.cloud_error = "雲端生圖未啟用（enable_cloud_image_gen=False）"
            # Make sure Ollama is unloaded before SD takes the GPU
            await unload_model(model_name=active_ollama_model)
            output_path = await _run_local_image(job, prompt, prompt_spec)
        else:
            try:
                logger.info("[Step 2/cloud] Calling gpt-image-2 ...")
                output_path = await _run_cloud_image(job, prompt)
                logger.info("[Step 2/cloud] Image generated: %s", output_path)
            except CloudImageGenError as exc:
                logger.warning(
                    "[Step 2/cloud] Cloud generation failed, falling back to "
                    "local. job=%s err=%s",
                    job.job_id, exc,
                )
                job.fallback_from_cloud = True
                job.cloud_error = str(exc)
                # Free GPU before SD starts
                await unload_model(model_name=active_ollama_model)
                output_path = await _run_local_image(job, prompt, prompt_spec)
    else:
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
