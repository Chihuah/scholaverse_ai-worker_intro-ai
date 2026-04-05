from __future__ import annotations

"""sd-cli subprocess wrapper with LoRA, style, readability, and cleanup blocks."""

import asyncio
import logging
import random
from pathlib import Path

from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

LORA_OPTIONS = [
    "<lora:moode_fantasy_Impressions:0.5>",
    "<lora:Z-Art-3:0.5>",
    "<lora:Desimulate:0.5>",
    None,
]

READABILITY_BLOCK = "face readable, pose readable, text readable"
CLEANUP_BLOCK = (
    "no extra characters, no extra weapons, no cluttered props, no obscured face, "
    "no unreadable text, no oversized weapon dominating the frame, no ambiguous pose, no silhouette, no backlit silhouette, no face in deep shadow"
)


def _pick_random_lora() -> str | None:
    return random.choice(LORA_OPTIONS)


def _compose_final_prompt(
    llm_prompt: str,
    style_block: str,
    lora_block: str | None,
) -> str:
    parts = []
    if lora_block:
        parts.append(lora_block)
    if style_block:
        parts.append(style_block)
    parts.append(llm_prompt)
    parts.append(READABILITY_BLOCK)
    parts.append(CLEANUP_BLOCK)
    return ", ".join(part.strip().rstrip(",") for part in parts if part and part.strip())


async def run_sd_cli(
    prompt: str,
    job_id: str,
    student_id: str,
    style_prefix: str,
    seed_override: int | None = None,
) -> tuple[str, str, int, str]:
    """Run sd-cli and return (output_path, lora_tag, seed, final_prompt)."""
    del student_id  # reserved for future deterministic seed strategies

    lora_block = _pick_random_lora()
    final_prompt = _compose_final_prompt(
        llm_prompt=prompt,
        style_block=style_prefix,
        lora_block=lora_block,
    )
    seed = seed_override if seed_override is not None else random.randint(0, 2_147_483_647)

    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{job_id}.png"

    cmd = [
        settings.sd_cli_path,
        "--diffusion-model", settings.model_path,
        "--vae", settings.vae_path,
        "--llm", settings.llm_model_path,
        "--cfg-scale", str(settings.default_cfg),
        "--steps", str(settings.default_steps),
        "--diffusion-fa",
        "-H", str(settings.default_height),
        "-W", str(settings.default_width),
        "-o", str(output_path),
        "-s", str(seed),
        "--lora-model-dir", settings.lora_dir,
        "-p", final_prompt,
    ]

    lora_tag = lora_block or "none"
    logger.info(
        "Starting sd-cli: job_id=%s, seed=%s, lora=%s, output=%s",
        job_id, seed, lora_tag, output_path,
    )
    logger.debug("sd-cli command: %s", cmd)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=settings.job_timeout,
        )
    except asyncio.TimeoutError:
        logger.error("sd-cli timed out after %ds, killing process: job_id=%s", settings.job_timeout, job_id)
        process.kill()
        await process.wait()
        raise Exception(f"sd-cli timed out after {settings.job_timeout} seconds")

    if process.returncode != 0:
        stderr_text = stderr.decode(errors="replace").strip()
        logger.error(
            "sd-cli failed (rc=%d): job_id=%s, stderr=%s",
            process.returncode, job_id, stderr_text,
        )
        raise Exception(f"sd-cli exited with code {process.returncode}: {stderr_text}")

    if not output_path.exists():
        logger.error("sd-cli finished but output file missing: %s", output_path)
        raise Exception(f"sd-cli completed but output file not found: {output_path}")

    logger.info("sd-cli completed: job_id=%s, output=%s", job_id, output_path)
    return str(output_path), lora_tag, seed, final_prompt


async def create_thumbnail(image_path: str) -> str:
    """Create thumbnail (220x320)."""
    src = Path(image_path)
    thumbnail_path = src.with_name(f"{src.stem}_thumb{src.suffix}")

    logger.info("Creating thumbnail: %s -> %s", src, thumbnail_path)

    img = Image.open(src)
    thumb = img.resize((220, 320), Image.LANCZOS)
    thumb.save(str(thumbnail_path), "PNG")

    logger.info("Thumbnail created: %s", thumbnail_path)
    return str(thumbnail_path)
