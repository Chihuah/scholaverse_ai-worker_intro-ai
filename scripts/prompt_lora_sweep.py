#!/usr/bin/env python3
"""提示詞 × LoRA 掃描腳本

讀取預先準備好的提示詞檔案，對每個 LoRA 各跑一遍，全部結果放在同一個 HTML 頁面。

格式（prompts.txt）：
    # prompt 1
    <完整 prompt 文字>
    # prompt 2
    <完整 prompt 文字>
    ...

使用方式：
    python scripts/prompt_lora_sweep.py

選項：
    --prompts   prompts 檔案路徑（預設：scripts/prompts.txt）
    --seed      固定種子數（預設：413570001）
    --cfg       CFG scale（預設：1.0）
    --steps     steps（預設：8）
    --loras     LoRA 清單，逗號分隔（預設：moode,zart,desim,none）

輸出：
    outputs/prompt_lora_sweep/sweep_{seed}_{timestamp}/
    ├── {圖片 png...}
    └── index.html        （單一頁面：6 列提示詞 × 4 欄 LoRA）
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT        = Path(__file__).parent.parent
PYTHON_BIN  = "/home/chihuah/miniconda3/envs/sd-env/bin/python"
GEN_SINGLE  = Path(__file__).parent / "gen_single.py"

LORA_DISPLAY: dict[str, str] = {
    "moode": "moode_fantasy",
    "zart":  "Z-Art-3",
    "desim": "Desimulate",
    "none":  "No LoRA",
}


# ─── 解析 prompts 檔 ──────────────────────────────────────────────────────────
def parse_prompts(path: Path) -> list[str]:
    """解析 '# prompt N\\n<文字>' 格式，回傳 prompt 字串列表。"""
    prompts: list[str] = []
    current: list[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^#\s*prompt\s+\d+", line, re.IGNORECASE):
            if current:
                text = " ".join(current).strip()
                if text:
                    prompts.append(text)
            current = []
        else:
            stripped = line.strip()
            if stripped:
                current.append(stripped)

    if current:
        text = " ".join(current).strip()
        if text:
            prompts.append(text)

    return prompts


# ─── 單張生圖 ─────────────────────────────────────────────────────────────────
def run_gen(prompt: str, seed: int, lora: str, cfg: float, steps: int, out_path: Path) -> tuple[bool, float]:
    t0 = time.time()
    result = subprocess.run(
        [
            PYTHON_BIN, str(GEN_SINGLE),
            "--prompt", prompt,
            "--seed",   str(seed),
            "--lora",   lora,
            "--cfg",    str(cfg),
            "--steps",  str(steps),
        ],
        capture_output=True,
        text=True,
    )
    elapsed = time.time() - t0

    gen_path: Path | None = None
    for line in result.stdout.splitlines():
        if line.startswith("OUTPUT_PATH="):
            gen_path = Path(line.split("=", 1)[1].strip())
            break

    ok = result.returncode == 0 and gen_path and gen_path.exists()
    if ok:
        shutil.copy2(gen_path, out_path)
    else:
        err = result.stderr.strip()[-120:] if result.stderr else "(no stderr)"
        print(f"    FAIL: {err}", file=sys.stderr)

    return bool(ok), elapsed


# ─── HTML ──────────────────────────────────────────────────────────────────────
def make_html(
    seed: int,
    cfg: float,
    steps: int,
    loras: list[str],
    prompts: list[str],
    images: dict[tuple[int, str], str],    # (prompt_idx, lora) → filename | ""
    elapsed: dict[tuple[int, str], float],
) -> str:
    n_prompts = len(prompts)
    n_loras   = len(loras)

    # 欄標題（LoRA）
    th_loras = "".join(
        f'<th style="color:#d4a847;padding:8px 16px;font-size:11px;'
        f'white-space:nowrap;">{html.escape(LORA_DISPLAY.get(l, l))}</th>'
        for l in loras
    )

    rows = []
    for i, prompt_text in enumerate(prompts):
        # 每列左側：提示詞摘要
        preview = html.escape(prompt_text[:160]) + ("…" if len(prompt_text) > 160 else "")
        row_label = f"""
            <td style="vertical-align:top;padding:6px 10px;max-width:200px;
                        border-right:1px solid #2d3a1a;">
              <div style="color:#d4a847;font-size:10px;font-family:monospace;
                          margin-bottom:4px;">Prompt {i+1}</div>
              <div style="color:#888;font-size:9px;line-height:1.5;
                          word-break:break-word;">{preview}</div>
            </td>"""

        # 各 LoRA 格
        cells = [row_label]
        for lora in loras:
            fname = images.get((i, lora), "")
            t     = elapsed.get((i, lora), 0.0)
            if fname:
                img_tag = (
                    f'<img src="{html.escape(fname)}" '
                    'style="width:176px;height:256px;object-fit:cover;'
                    'border:2px solid #2d3a1a;display:block;">'
                )
            else:
                img_tag = (
                    '<div style="width:176px;height:256px;background:#111;'
                    'display:flex;align-items:center;justify-content:center;'
                    'color:#555;font-size:10px;">失敗</div>'
                )
            cells.append(f"""
            <td style="padding:6px 8px;vertical-align:top;">
              {img_tag}
              <div style="color:#666;font-size:9px;text-align:center;
                          margin-top:3px;">{t:.1f}s</div>
            </td>""")

        rows.append(f'<tr style="border-bottom:1px solid #1e2a1e;">{"".join(cells)}</tr>')

    total_ok = sum(1 for v in images.values() if v)
    total    = n_prompts * n_loras

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>Prompt × LoRA Sweep — seed {seed}</title>
<style>
  body {{
    background: #1a1a2e;
    color: #e8d5b0;
    font-family: sans-serif;
    margin: 20px;
  }}
  h1 {{
    font-family: monospace;
    font-size: 13px;
    color: #d4a847;
    margin-bottom: 4px;
  }}
  .meta {{
    color: #888;
    font-size: 11px;
    margin-bottom: 16px;
  }}
  table {{
    border-collapse: collapse;
    background: #12121f;
  }}
  thead th {{
    background: #12121f;
    border-bottom: 2px solid #2d3a1a;
  }}
  tr:hover td {{
    background: rgba(212,168,71,0.04);
  }}
</style>
</head>
<body>
<h1>Prompt × LoRA Sweep</h1>
<div class="meta">
  seed={seed} &nbsp;|&nbsp; cfg={cfg} &nbsp;|&nbsp; steps={steps}
  &nbsp;|&nbsp; {total_ok}/{total} 張成功
  &nbsp;|&nbsp; 生成時間：{html.escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}
</div>
<table>
  <thead>
    <tr>
      <th style="color:#d4a847;padding:8px 16px;font-size:11px;
                 text-align:left;border-right:1px solid #2d3a1a;">Prompt</th>
      {th_loras}
    </tr>
  </thead>
  <tbody>
    {"".join(rows)}
  </tbody>
</table>
</body>
</html>"""


# ─── 主程式 ────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    default_prompts = Path(__file__).parent / "prompts.txt"
    p = argparse.ArgumentParser(description="提示詞 × LoRA 掃描")
    p.add_argument("--prompts", default=str(default_prompts), help="prompts 檔案路徑")
    p.add_argument("--seed",    type=int,   default=413570001)
    p.add_argument("--cfg",     type=float, default=1.0)
    p.add_argument("--steps",   type=int,   default=8)
    p.add_argument("--loras",   default="moode,zart,desim,none")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    prompts_path = Path(args.prompts)
    if not prompts_path.exists():
        print(f"[錯誤] 找不到 prompts 檔：{prompts_path}", file=sys.stderr)
        sys.exit(1)

    prompts = parse_prompts(prompts_path)
    if not prompts:
        print("[錯誤] prompts 檔內找不到任何提示詞", file=sys.stderr)
        sys.exit(1)

    loras = [s.strip() for s in args.loras.split(",")]

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "outputs" / "prompt_lora_sweep" / f"sweep_{args.seed}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    total = len(prompts) * len(loras)
    print(f"\n{'='*60}")
    print(f"Prompt × LoRA Sweep")
    print(f"  seed={args.seed}  cfg={args.cfg}  steps={args.steps}")
    print(f"  {len(prompts)} 個提示詞 × {len(loras)} 個 LoRA = {total} 張")
    print(f"  輸出：{out_dir}")
    print(f"{'='*60}\n")

    images:  dict[tuple[int, str], str]   = {}
    elapsed: dict[tuple[int, str], float] = {}
    total_ok = 0

    for lora in loras:
        lora_display = LORA_DISPLAY.get(lora, lora)
        print(f"── LoRA: {lora_display} {'─'*40}")

        for i, prompt in enumerate(prompts):
            fname    = f"p{i+1}_{lora}_seed{args.seed}.png"
            out_path = out_dir / fname

            print(f"  Prompt {i+1} [{lora}]...", end=" ", flush=True)
            ok, t = run_gen(prompt, args.seed, lora, args.cfg, args.steps, out_path)
            elapsed[(i, lora)] = t

            if ok:
                images[(i, lora)] = fname
                total_ok += 1
                print(f"OK {t:.1f}s")
            else:
                images[(i, lora)] = ""
                print(f"FAIL {t:.1f}s")

        print()

    # HTML
    page = make_html(
        seed=args.seed,
        cfg=args.cfg,
        steps=args.steps,
        loras=loras,
        prompts=prompts,
        images=images,
        elapsed=elapsed,
    )
    index_path = out_dir / "index.html"
    index_path.write_text(page, encoding="utf-8")

    print(f"{'='*60}")
    print(f"完成！{total_ok}/{total} 張成功")
    print(f"報告：{index_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
