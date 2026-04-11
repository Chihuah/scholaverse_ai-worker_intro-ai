#!/usr/bin/env python3
"""參數掃描測試腳本 — 測試 Steps × CFG × LoRA 的生圖結果。

使用方式：
    cd /home/chihuah/ai-worker
    python scripts/param_sweep.py                          # 完整 48 張
    python scripts/param_sweep.py --steps 10,20 --cfgs 1.0,6.0 --loras none,moode_fantasy_Impressions
    python scripts/param_sweep.py --dry-run                # 只列組合，不生圖
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── 讀取 .env（與 app/config.py 一致的路徑）──────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # 如果沒有 python-dotenv，依賴環境變數本身

SD_CLI_PATH = os.getenv("SD_CLI_PATH",  "/home/chihuah/stable-diffusion.cpp/build/bin/sd-cli")
MODEL_PATH  = os.getenv("MODEL_PATH",   "/home/chihuah/stable-diffusion.cpp/models/z-image-turbo-Q8_0.gguf")
VAE_PATH    = os.getenv("VAE_PATH",     "/home/chihuah/stable-diffusion.cpp/models/FLUX_ae.safetensors")
LLM_PATH    = os.getenv("LLM_MODEL_PATH", "/home/chihuah/stable-diffusion.cpp/models/Qwen3-4b-Z-Image-Engineer-V4-Q8_0.gguf")
LORA_DIR    = os.getenv("LORA_DIR",     "/home/chihuah/stable-diffusion.cpp/models/lora")
DEFAULT_H   = int(os.getenv("DEFAULT_HEIGHT", "1280"))
DEFAULT_W   = int(os.getenv("DEFAULT_WIDTH",  "880"))

# ── 預設測試 Prompt ────────────────────────────────────────────────────────────
DEFAULT_PROMPT = (
    "a female elf mage in legendary robes, holding a glowing staff, "
    "standing in a magic tower interior, confident expression, "
    "battle ready pose, ornate gold card border, "
    "face readable, pose readable"
)

CLEANUP_BLOCK = (
    "no extra characters, no extra weapons, no cluttered props, no obscured face, "
    "no unreadable text, no oversized weapon dominating the frame"
)

STYLE_BLOCK = (
    "Digital painting, epic fantasy art, painterly texture, "
    "majestic and awe-inspiring atmosphere, high detail"
)

# ── LoRA 定義 ─────────────────────────────────────────────────────────────────
ALL_LORAS: dict[str, str | None] = {
    "moode_fantasy_Impressions": "<lora:moode_fantasy_Impressions:0.5>",
    "Z-Art-3":                   "<lora:Z-Art-3:0.5>",
    "Desimulate":                "<lora:Desimulate:0.5>",
    "none":                      None,
}


# ── Prompt 組合 ───────────────────────────────────────────────────────────────

def compose_prompt(base_prompt: str, lora_tag: str | None) -> str:
    parts = []
    if lora_tag:
        parts.append(lora_tag)
    parts.append(STYLE_BLOCK)
    parts.append(base_prompt)
    parts.append(CLEANUP_BLOCK)
    return ", ".join(p.strip().rstrip(",") for p in parts if p and p.strip())


# ── 執行單張生圖 ───────────────────────────────────────────────────────────────

def run_one(
    output_path: Path,
    prompt: str,
    steps: int,
    cfg: float,
    seed: int,
) -> tuple[bool, float, str]:
    """執行一次 sd-cli，回傳 (成功, 耗時秒, 錯誤訊息)。"""
    cmd = [
        SD_CLI_PATH,
        "--diffusion-model", MODEL_PATH,
        "--vae", VAE_PATH,
        "--llm", LLM_PATH,
        "--cfg-scale", str(cfg),
        "--steps", str(steps),
        "--diffusion-fa",
        "-H", str(DEFAULT_H),
        "-W", str(DEFAULT_W),
        "-o", str(output_path),
        "-s", str(seed),
        "--lora-model-dir", LORA_DIR,
        "-p", prompt,
    ]

    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0

    if result.returncode != 0:
        err = result.stderr.strip()[-300:] if result.stderr else "(no stderr)"
        return False, elapsed, err

    if not output_path.exists():
        return False, elapsed, "sd-cli exited 0 but output file missing"

    return True, elapsed, ""


# ── HTML 報告產生 ──────────────────────────────────────────────────────────────

def generate_html(
    out_dir: Path,
    results: list[dict],
    steps_list: list[int],
    cfgs_list: list[float],
    loras_list: list[str],
    seed: int,
    base_prompt: str,
) -> Path:
    html_path = out_dir / "index.html"

    # 建立 lora -> steps -> cfg -> result 的巢狀索引
    idx: dict[str, dict[int, dict[float, dict]]] = {}
    for r in results:
        idx.setdefault(r["lora"], {}).setdefault(r["steps"], {})[r["cfg"]] = r

    tab_buttons = []
    tab_contents = []

    for i, lora in enumerate(loras_list):
        active_btn = "active" if i == 0 else ""
        display = "block" if i == 0 else "none"
        tab_id = f"tab_{lora}"

        tab_buttons.append(
            f'<button class="tab-btn {active_btn}" onclick="showTab(\'{tab_id}\')">'
            f'{"(none)" if lora == "none" else lora}</button>'
        )

        # header row
        header_cells = "<th>CFG / Steps</th>" + "".join(
            f"<th>Steps {s}</th>" for s in steps_list
        )

        rows = []
        for cfg in cfgs_list:
            cells = [f"<td class='cfg-label'>CFG {cfg}</td>"]
            for steps in steps_list:
                r = idx.get(lora, {}).get(steps, {}).get(cfg)
                if r is None:
                    cells.append("<td>-</td>")
                elif not r["ok"]:
                    cells.append(f"<td class='err'>FAIL<br><small>{r['error'][:80]}</small></td>")
                else:
                    fname = r["filename"]
                    t = r["elapsed"]
                    cells.append(
                        f"<td>"
                        f"<a href='{fname}' target='_blank'>"
                        f"<img src='{fname}' loading='lazy'>"
                        f"</a>"
                        f"<div class='label'>steps={steps} cfg={cfg}<br>{t:.1f}s</div>"
                        f"</td>"
                    )
            rows.append("<tr>" + "".join(cells) + "</tr>")

        table_html = (
            f"<table><thead><tr>{header_cells}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

        tab_contents.append(
            f'<div id="{tab_id}" class="tab-content" style="display:{display}">'
            f"{table_html}</div>"
        )

    tabs_html = "".join(tab_buttons)
    contents_html = "".join(tab_contents)

    total_ok = sum(1 for r in results if r["ok"])
    total = len(results)
    total_time = sum(r["elapsed"] for r in results)

    prompt_display = base_prompt[:120] + ("..." if len(base_prompt) > 120 else "")
    model_name = Path(MODEL_PATH).name

    html = (
        "<!DOCTYPE html>\n"
        '<html lang="zh-TW">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        f"<title>param_sweep - {out_dir.name}</title>\n"
        "<style>\n"
        "  body { font-family: monospace; background: #1a1a1a; color: #e0e0e0; padding: 20px; }\n"
        "  h1 { color: #d4a847; }\n"
        "  .meta { background: #2a2a2a; padding: 12px; border-radius: 4px; margin-bottom: 16px; font-size: 13px; }\n"
        "  .tabs { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }\n"
        "  .tab-btn { background: #333; color: #ccc; border: 1px solid #555; padding: 6px 14px;\n"
        "             cursor: pointer; border-radius: 4px; font-size: 13px; }\n"
        "  .tab-btn.active { background: #d4a847; color: #000; border-color: #d4a847; }\n"
        "  table { border-collapse: collapse; }\n"
        "  th, td { border: 1px solid #444; padding: 6px 8px; text-align: center; vertical-align: top; }\n"
        "  th { background: #333; font-size: 13px; }\n"
        "  .cfg-label { background: #2d2d2d; font-weight: bold; font-size: 13px; white-space: nowrap; }\n"
        "  td img { width: 110px; height: 160px; object-fit: cover; display: block; cursor: pointer; }\n"
        "  .label { font-size: 11px; color: #aaa; margin-top: 4px; }\n"
        "  .err { color: #f87; font-size: 12px; max-width: 120px; }\n"
        "  .summary { margin-top: 16px; color: #aaa; font-size: 13px; }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        "<h1>param_sweep 結果報告</h1>\n"
        '<div class="meta">\n'
        f"  <b>目錄：</b>{out_dir.name}<br>\n"
        f"  <b>Seed：</b>{seed}<br>\n"
        f"  <b>Prompt：</b>{prompt_display}<br>\n"
        f"  <b>模型：</b>{model_name}<br>\n"
        f"  <b>完成：</b>{total_ok} / {total} 張 | <b>總耗時：</b>{total_time/60:.1f} 分鐘\n"
        "</div>\n"
        f'<div class="tabs">{tabs_html}</div>\n'
        f"{contents_html}\n"
        f'<div class="summary">圖片解析度：{DEFAULT_W}x{DEFAULT_H}px | 點擊圖片可開啟原始大小</div>\n'
        "<script>\n"
        "function showTab(id) {\n"
        "  document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');\n"
        "  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));\n"
        "  document.getElementById(id).style.display = 'block';\n"
        "  event.target.classList.add('active');\n"
        "}\n"
        "</script>\n"
        "</body>\n"
        "</html>"
    )

    html_path.write_text(html, encoding="utf-8")
    return html_path


# ── 解析 CLI 參數 ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ZIT 參數掃描測試腳本")
    p.add_argument("--steps",   default="10,20,30",
                   help="逗號分隔的 steps 清單（預設 10,20,30）")
    p.add_argument("--cfgs",    default="1.0,4.0,6.0,8.0",
                   help="逗號分隔的 CFG 清單（預設 1.0,4.0,6.0,8.0）")
    p.add_argument("--loras",   default="all",
                   help="all | none | 逗號分隔的 LoRA 名稱（預設 all）")
    p.add_argument("--seed",    type=int, default=None,
                   help="固定 seed（預設隨機產生後全程使用同一個）")
    p.add_argument("--prompt",  default=None,
                   help="覆蓋預設測試 prompt")
    p.add_argument("--tag",     default="sweep",
                   help="輸出資料夾前綴（預設 sweep）")
    p.add_argument("--dry-run", action="store_true",
                   help="只印組合清單，不實際生圖")
    return p.parse_args()


def resolve_loras(loras_arg: str) -> list[str]:
    if loras_arg == "all":
        return list(ALL_LORAS.keys())
    if loras_arg == "none":
        return ["none"]
    names = [n.strip() for n in loras_arg.split(",") if n.strip()]
    unknown = [n for n in names if n not in ALL_LORAS]
    if unknown:
        print(f"[警告] 未知的 LoRA 名稱：{unknown}，已忽略")
    return [n for n in names if n in ALL_LORAS]


# ── 主程式 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    steps_list = [int(s.strip()) for s in args.steps.split(",")]
    cfgs_list  = [float(c.strip()) for c in args.cfgs.split(",")]
    loras_list = resolve_loras(args.loras)
    seed       = args.seed if args.seed is not None else random.randint(0, 2_147_483_647)
    base_prompt = args.prompt or DEFAULT_PROMPT

    # 建立組合清單（lora 在外層，可在 HTML 做分頁）
    combos = [
        (steps, cfg, lora)
        for lora  in loras_list
        for cfg   in cfgs_list
        for steps in steps_list
    ]

    total = len(combos)
    print("=" * 64)
    print(f"param_sweep — {total} 個組合")
    print(f"  Steps : {steps_list}")
    print(f"  CFG   : {cfgs_list}")
    print(f"  LoRA  : {loras_list}")
    print(f"  Seed  : {seed}")
    print(f"  Prompt: {base_prompt[:80]}{'...' if len(base_prompt) > 80 else ''}")
    print("=" * 64)

    if args.dry_run:
        print("\n[dry-run] 組合清單：")
        for i, (steps, cfg, lora) in enumerate(combos, 1):
            print(f"  {i:3}. steps={steps:3}  cfg={cfg:4}  lora={lora}")
        print(f"\n共 {total} 張，不生圖。")
        return

    # 確認 sd-cli 存在
    if not Path(SD_CLI_PATH).exists():
        print(f"[錯誤] sd-cli 不存在：{SD_CLI_PATH}")
        sys.exit(1)

    # 建立輸出目錄
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(__file__).parent.parent / "param_test" / f"{args.tag}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n輸出目錄：{out_dir}\n")

    results: list[dict] = []
    grand_t0 = time.time()

    for i, (steps, cfg, lora) in enumerate(combos, 1):
        lora_tag = ALL_LORAS[lora]
        lora_short = lora[:24]
        fname = f"steps{steps:02d}_cfg{cfg}_lora_{lora_short}_seed{seed}.png"
        output_path = out_dir / fname

        prompt = compose_prompt(base_prompt, lora_tag)

        print(f"[{i:3}/{total}] steps={steps:2}  cfg={cfg:4}  lora={lora_short:<28} ", end="", flush=True)

        ok, elapsed, err = run_one(output_path, prompt, steps, cfg, seed)

        if ok:
            print(f"OK  {elapsed:.1f}s")
        else:
            print(f"FAIL  {elapsed:.1f}s  err={err[:60]}")

        results.append({
            "steps": steps, "cfg": cfg, "lora": lora,
            "filename": fname, "ok": ok,
            "elapsed": elapsed, "error": err,
        })

        time.sleep(5)  # 等待 CUDA 驅動釋放 VRAM 快取

    grand_elapsed = time.time() - grand_t0

    # 儲存 metadata JSON
    meta = {
        "timestamp": ts, "seed": seed,
        "prompt": base_prompt, "model": Path(MODEL_PATH).name,
        "steps_list": steps_list, "cfgs_list": cfgs_list, "loras_list": loras_list,
        "results": results,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    # 產生 HTML 報告
    html_path = generate_html(out_dir, results, steps_list, cfgs_list, loras_list, seed, base_prompt)

    # 最終摘要
    ok_count   = sum(1 for r in results if r["ok"])
    fail_count = total - ok_count
    print("\n" + "=" * 64)
    print(f"完成：{ok_count} 張  失敗：{fail_count} 張  總耗時：{grand_elapsed/60:.1f} 分鐘")
    print(f"HTML 報告：{html_path}")
    print("=" * 64)


if __name__ == "__main__":
    main()
