"""sd-cli subprocess 封裝 — 自動加入 LoRA 觸發詞 / 風格前綴（seed 使用 -1 隨機）"""

import asyncio
import logging
import random
from pathlib import Path

from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

# 可用的 LoRA 風格選項（None 代表不使用 LoRA）
# 每次生成隨機挑選一種，讓不同學生的卡牌有視覺多樣性
LORA_OPTIONS = [
    "<lora:moode_fantasy_Impressions:0.5>",
    "<lora:Z-Art-3:0.5>",
    "<lora:Desimulate:0.5>",
    None,  # 不使用 LoRA
]


def _pick_random_lora_prefix(style_prefix: str) -> str:
    """隨機挑選一個 LoRA 風格，組裝並回傳 prompt 前綴。

    style_prefix 由 prompt_builder.build_style_prefix() 動態生成，
    依 LV 和稀有度調整氛圍與視覺品質。
    """
    lora = random.choice(LORA_OPTIONS)
    if lora:
        return f"{lora} {style_prefix}"
    return style_prefix


async def run_sd_cli(prompt: str, job_id: str, student_id: str,
                     style_prefix: str) -> tuple[str, str, int, str]:
    """呼叫 sd-cli 生成圖片，回傳 (輸出檔案路徑, lora_tag, seed, final_prompt)。

    Args:
        prompt: Ollama 產出的純角色描述（不含 LoRA / 前綴）。
        job_id: 任務 UUID，用於命名輸出檔案。
        student_id: 學號（目前未使用，保留供未來擴充）。
        style_prefix: 由 build_style_prefix(level, rarity) 動態生成的風格前綴。

    Returns:
        (output_path, lora_tag) — lora_tag 為 "none" 代表未使用 LoRA。

    Raises:
        Exception: sd-cli 執行失敗或超時。
    """
    # 隨機挑選 LoRA 風格並組裝最終 prompt
    prompt_prefix = _pick_random_lora_prefix(style_prefix)
    final_prompt = f"{prompt_prefix} {prompt}"
    seed = -1  # 使用隨機 seed，每次生成結果不同，確保重新生成有意義

    # 輸出路徑
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{job_id}.png"

    # 組裝 sd-cli 指令
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

    lora_tag = prompt_prefix.split(" ")[0] if prompt_prefix.startswith("<lora:") else "none"
    logger.info(
        "Starting sd-cli: job_id=%s, seed=%s (random), lora=%s, output=%s",
        job_id, seed, lora_tag, output_path,
    )
    logger.debug("sd-cli command: %s", cmd)

    # 執行 subprocess
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
        raise Exception(
            f"sd-cli timed out after {settings.job_timeout} seconds"
        )

    # 檢查 returncode
    if process.returncode != 0:
        stderr_text = stderr.decode(errors="replace").strip()
        logger.error(
            "sd-cli failed (rc=%d): job_id=%s, stderr=%s",
            process.returncode, job_id, stderr_text,
        )
        raise Exception(
            f"sd-cli exited with code {process.returncode}: {stderr_text}"
        )

    # 檢查輸出檔案是否存在
    if not output_path.exists():
        logger.error("sd-cli finished but output file missing: %s", output_path)
        raise Exception(
            f"sd-cli completed but output file not found: {output_path}"
        )

    logger.info("sd-cli completed: job_id=%s, output=%s", job_id, output_path)
    return str(output_path), lora_tag, seed, final_prompt


async def create_thumbnail(image_path: str) -> str:
    """產生縮圖 (220x320)。

    Args:
        image_path: 原始圖片路徑。

    Returns:
        縮圖檔案路徑字串。
    """
    src = Path(image_path)
    thumbnail_path = src.with_name(f"{src.stem}_thumb{src.suffix}")

    logger.info("Creating thumbnail: %s -> %s", src, thumbnail_path)

    img = Image.open(src)
    thumb = img.resize((220, 320), Image.LANCZOS)
    thumb.save(str(thumbnail_path), "PNG")

    logger.info("Thumbnail created: %s", thumbnail_path)
    return str(thumbnail_path)
