#!/usr/bin/env python3
"""單張生圖腳本 — 直接呼叫 sd-cli 生成一張圖，不經過 FastAPI。

使用方式：
    python scripts/gen_single.py --prompt "a female elf mage..." [options]

選項：
    --prompt    生圖提示詞（必填）
    --cfg       CFG scale（預設 1.0）
    --steps     推理步數（預設 10）
    --lora      LoRA 縮寫：moode / zart / desim / none（預設 none）
    --seed      固定 seed（預設隨機）

輸出：
    outputs/manual/gen_YYYYMMDD_HHMMSS_seed{S}.png
    最後一行 stdout 格式：OUTPUT_PATH=/path/to/file.png
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

SD_CLI_PATH = os.getenv("SD_CLI_PATH",  "/home/chihuah/stable-diffusion.cpp/build/bin/sd-cli")
MODEL_PATH  = os.getenv("MODEL_PATH",   "/home/chihuah/stable-diffusion.cpp/models/z-image-turbo-Q8_0.gguf")
VAE_PATH    = os.getenv("VAE_PATH",     "/home/chihuah/stable-diffusion.cpp/models/FLUX_ae.safetensors")
LLM_PATH    = os.getenv("LLM_MODEL_PATH", "/home/chihuah/stable-diffusion.cpp/models/Qwen3-4b-Z-Image-Engineer-V4-Q8_0.gguf")
LORA_DIR    = os.getenv("LORA_DIR",     "/home/chihuah/stable-diffusion.cpp/models/lora")
DEFAULT_H   = int(os.getenv("DEFAULT_HEIGHT", "1280"))
DEFAULT_W   = int(os.getenv("DEFAULT_WIDTH",  "880"))

STYLE_BLOCK = (
    "Digital painting, epic fantasy art, painterly texture, "
    "majestic and awe-inspiring atmosphere, high detail"
)
CLEANUP_BLOCK = (
    "no extra characters, no extra weapons, no cluttered props, no obscured face, "
    "no unreadable text, no oversized weapon dominating the frame, no ambiguous pose, "
    "no silhouette, no backlit silhouette, no face in deep shadow"
)

# LoRA 縮寫對照
LORA_MAP: dict[str, str | None] = {
    "moode": "<lora:moode_fantasy_Impressions:0.5>",
    "zart":  "<lora:Z-Art-3:0.5>",
    "desim": "<lora:Desimulate:0.5>",
    "none":  None,
}


def resolve_lora(alias: str) -> tuple[str | None, str]:
    """回傳 (lora_block, display_name)"""
    key = alias.lower().strip()
    if key not in LORA_MAP:
        print(f"[警告] 不認識的 LoRA 縮寫「{alias}」，使用 none", file=sys.stderr)
        key = "none"
    return LORA_MAP[key], key


def compose_prompt(base_prompt: str, lora_block: str | None) -> str:
    parts = []
    if lora_block:
        parts.append(lora_block)
    parts.append(STYLE_BLOCK)
    parts.append(base_prompt.strip())
    parts.append(CLEANUP_BLOCK)
    return ", ".join(p.strip().rstrip(",") for p in parts if p and p.strip())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="單張生圖腳本")
    p.add_argument("--prompt", required=True, help="生圖提示詞")
    p.add_argument("--cfg",   type=float, default=1.0, help="CFG scale（預設 1.0）")
    p.add_argument("--steps", type=int,   default=10,  help="推理步數（預設 10）")
    p.add_argument("--lora",  default="none",          help="LoRA 縮寫：moode / zart / desim / none")
    p.add_argument("--seed",  type=int,   default=None, help="固定 seed（預設隨機）")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not Path(SD_CLI_PATH).exists():
        print(f"[錯誤] sd-cli 不存在：{SD_CLI_PATH}", file=sys.stderr)
        sys.exit(1)

    lora_block, lora_name = resolve_lora(args.lora)
    seed = args.seed if args.seed is not None else random.randint(0, 2_147_483_647)
    final_prompt = compose_prompt(args.prompt, lora_block)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(__file__).parent.parent / "outputs" / "manual"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"gen_{ts}_seed{seed}.png"

    print(f"cfg={args.cfg}  steps={args.steps}  lora={lora_name}  seed={seed}")
    print(f"輸出：{output_path}")
    print(f"Prompt：{final_prompt[:120]}{'...' if len(final_prompt) > 120 else ''}")
    print("生圖中...", flush=True)

    cmd = [
        SD_CLI_PATH,
        "--diffusion-model", MODEL_PATH,
        "--vae", VAE_PATH,
        "--llm", LLM_PATH,
        "--cfg-scale", str(args.cfg),
        "--steps", str(args.steps),
        "--diffusion-fa",
        "-H", str(DEFAULT_H),
        "-W", str(DEFAULT_W),
        "-o", str(output_path),
        "-s", str(seed),
        "--lora-model-dir", LORA_DIR,
        "-p", final_prompt,
    ]

    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0

    if result.returncode != 0:
        err = result.stderr.strip()[-300:] if result.stderr else "(no stderr)"
        print(f"[失敗] {elapsed:.1f}s — {err}", file=sys.stderr)
        sys.exit(1)

    if not output_path.exists():
        print("[失敗] sd-cli 完成但找不到輸出檔案", file=sys.stderr)
        sys.exit(1)

    print(f"完成！耗時 {elapsed:.1f}s")
    # skill 用來解析路徑的固定格式輸出
    print(f"OUTPUT_PATH={output_path}")


if __name__ == "__main__":
    main()
