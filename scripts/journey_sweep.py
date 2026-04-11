#!/usr/bin/env python3
"""學習旅程 × LoRA 掃描腳本

固定 seed，跑 6 個 stage 提示詞 × steps 8/9/10，每個 LoRA 一個頁面。

使用方式：
    python scripts/journey_sweep.py --student-id 410520001

選項：
    --student-id    學號（同時作為 seed 和暱稱，預設 410520001）
    --profile       high / mid / low（預設 high）
    --scores        自訂分數，逗號分隔共 6 個（例：95,70,65,80,90,75）
    --cfg           CFG scale（預設 1.0）
    --steps         要掃描的 steps，逗號分隔（預設 8,9,10）
    --loras         要掃描的 LoRA，逗號分隔（預設 moode,zart,desim,none）
    --stages        要生成的 stage，逗號分隔（預設 1,2,3,4,5,6）
    --no-llm        跳過 Ollama，直接用結構化描述

輸出目錄：
    outputs/journey_sweep/sweep_{student_id}_{timestamp}/
    ├── prompts.json          (各 stage 的 LLM 提示詞)
    ├── index.html
    ├── lora_moode.html
    ├── lora_zart.html
    ├── lora_desim.html
    └── lora_none.html
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.prompt_builder import build_structured_description
from app.llm_service import generate_prompt, unload_model

# ─── 常數 ────────────────────────────────────────────────────────────────────
PYTHON_BIN = "/home/chihuah/miniconda3/envs/sd-env/bin/python"
GEN_SINGLE  = Path(__file__).parent / "gen_single.py"

ALL_LORAS   = ["moode", "zart", "desim", "none"]
ALL_STEPS   = [8, 9, 10]

LORA_DISPLAY: dict[str, str] = {
    "moode": "moode_fantasy_Impressions",
    "zart":  "Z-Art-3",
    "desim": "Desimulate",
    "none":  "No LoRA (Base)",
}

# ─── 屬性對應（同 student_journey.py）────────────────────────────────────────
RACE_BY_SCORE: list[tuple[int, list[str]]] = [
    (90, ["elf", "human", "orc", "dwarf", "dragon", "pixie"]),
    (70, ["human", "orc", "dwarf"]),
    (50, ["human", "goblin"]),
    (40, ["goblin", "pixie"]),
    (0,  ["plant", "slime"]),
]
GENDER_BY_LAST: dict[int, str] = {
    0: "male", 1: "female", 2: "male",    3: "female",
    4: "male", 5: "female", 6: "male",    7: "female",
    8: "neutral", 9: "neutral",
}
CLASS_BY_SCORE: list[tuple[int, list[str]]] = [
    (90, ["archmage", "paladin", "ranger", "assassin", "priest"]),
    (70, ["mage", "warrior", "archer"]),
    (50, ["warrior", "archer", "militia"]),
    (40, ["apprentice", "militia"]),
    (0,  ["farmer"]),
]
EQUIPMENT_BY_SCORE: list[tuple[int, str]] = [
    (90, "legendary"), (70, "fine"), (50, "common"), (40, "crude"), (0, "broken"),
]
WEAPON_QUALITY_BY_SCORE: list[tuple[int, str]] = [
    (90, "artifact"), (70, "fine"), (50, "common"), (40, "crude"), (0, "primitive"),
]
CLASS_WEAPON_MAP: dict[str, list[str]] = {
    "archmage":   ["staff", "spellbook"],
    "priest":     ["staff", "mace"],
    "mage":       ["staff", "spellbook"],
    "apprentice": ["staff"],
    "paladin":    ["sword", "shield"],
    "warrior":    ["sword", "mace"],
    "militia":    ["short_sword", "spear"],
    "ranger":     ["bow", "dagger"],
    "archer":     ["bow"],
    "assassin":   ["dagger", "short_sword"],
    "farmer":     ["wooden_stick", "stone"],
}
BACKGROUND_BY_SCORE: list[tuple[int, list[str]]] = [
    (90, ["palace_throne", "dragon_lair", "sky_city"]),
    (70, ["castle", "magic_tower"]),
    (50, ["town", "market"]),
    (40, ["village", "wilderness"]),
    (0,  ["ruins"]),
]
BORDER_BY_SCORE: list[tuple[int, str]] = [
    (90, "gold"), (70, "silver"), (50, "steel"), (0, "bronze"),
]
EXPRESSION_BY_SCORE: list[tuple[int, str]] = [
    (90, "regal"), (70, "confident"), (50, "calm"), (0, "weary"),
]
POSE_BY_SCORE: list[tuple[int, str]] = [
    (90, "charging"), (70, "battle_ready"), (50, "standing"), (0, "crouching"),
]
RARITY_BY_AVG: list[tuple[int, str]] = [
    (95, "UR"), (85, "SSR"), (70, "SR"), (50, "R"), (0, "N"),
]
PROFILES: dict[str, list[int]] = {
    "high": [95, 92, 90, 88, 93, 91],
    "mid":  [65, 62, 68, 60, 64, 63],
    "low":  [35, 38, 32, 30, 36, 34],
}
STAGE_LABELS = [
    "Stage 1 — 種族＋性別",
    "Stage 2 — ＋職業",
    "Stage 3 — ＋服飾",
    "Stage 4 — ＋武器",
    "Stage 5 — ＋背景",
    "Stage 6 — 完整角色",
]


# ─── 輔助 ─────────────────────────────────────────────────────────────────────
def pick(table: list[tuple[int, Any]], score: int, rng: random.Random) -> Any:
    for thr, val in table:
        if score >= thr:
            return rng.choice(val) if isinstance(val, list) else val
    last = table[-1][1]
    return rng.choice(last) if isinstance(last, list) else last


def derive_rarity(avg: float) -> str:
    for thr, r in RARITY_BY_AVG:
        if avg >= thr:
            return r
    return "N"


def build_card_config(student_id: str, scores: list[int], stage: int) -> dict[str, Any]:
    rng = random.Random(int(student_id))
    u = [scores[i] if stage > i else None for i in range(6)]
    cfg: dict[str, Any] = {}

    cfg["race"]   = pick(RACE_BY_SCORE, u[0], rng) if u[0] is not None else None
    cfg["gender"] = GENDER_BY_LAST.get(int(student_id[-1]), "neutral") if u[0] is not None else None
    cfg["class"]  = pick(CLASS_BY_SCORE, u[1], rng) if u[1] is not None else None
    cfg["equipment"] = pick(EQUIPMENT_BY_SCORE, u[2], rng) if u[2] is not None else None

    if u[3] is not None:
        cfg["weapon_quality"] = pick(WEAPON_QUALITY_BY_SCORE, u[3], rng)
        opts = (
            CLASS_WEAPON_MAP.get(cfg.get("class") or "warrior", ["sword"])
            if u[3] >= 40
            else ["wooden_stick", "stone"]
        )
        cfg["weapon_type"] = rng.choice(opts)
    else:
        cfg["weapon_quality"] = cfg["weapon_type"] = None

    cfg["background"] = pick(BACKGROUND_BY_SCORE, u[4], rng) if u[4] is not None else None

    if u[5] is not None:
        cfg["expression"] = pick(EXPRESSION_BY_SCORE, u[5], rng)
        cfg["pose"]       = pick(POSE_BY_SCORE, u[5], rng)
        cfg["border"]     = pick(BORDER_BY_SCORE, u[5], rng)
    else:
        cfg["expression"] = cfg["pose"] = None
        cfg["border"] = "bronze"

    done = [s for s in u[:stage] if s is not None]
    avg = sum(done) / len(done) if done else 30
    cfg["level"]  = max(1, min(100, int(avg)))
    cfg["rarity"] = derive_rarity(avg)
    return cfg


def build_learning_data(scores: list[int], stage: int) -> dict[str, Any]:
    return {
        "unit_scores": {f"unit_{i+1}": scores[i] for i in range(stage)},
        "overall_completion": stage / 6.0,
    }


def attrs_summary(cfg: dict[str, Any]) -> dict[str, str | None]:
    return {
        "種族": cfg.get("race"),
        "性別": cfg.get("gender"),
        "職業": cfg.get("class"),
        "服飾": cfg.get("equipment"),
        "武器": (
            f"{cfg.get('weapon_quality')} {cfg.get('weapon_type')}"
            if cfg.get("weapon_quality") else None
        ),
        "背景": cfg.get("background"),
        "外框": cfg.get("border"),
        "稀有度": cfg.get("rarity"),
    }


# ─── HTML ──────────────────────────────────────────────────────────────────────
def lora_page_html(
    student_id: str,
    lora: str,
    stages: list[int],
    steps_list: list[int],
    images: dict[tuple[int, int], str],   # (stage, steps) → filename or ""
    elapsed: dict[tuple[int, int], float],
    prompts: dict[int, str],
    stage_attrs: dict[int, dict],
    cfg: float,
) -> str:
    lora_name = html.escape(LORA_DISPLAY.get(lora, lora))

    # Table header
    th_cells = "".join(
        f'<th style="color:#d4a847;padding:6px 12px;">steps={s}</th>'
        for s in steps_list
    )

    rows = []
    for stage in stages:
        si = stage - 1
        label = STAGE_LABELS[si] if si < len(STAGE_LABELS) else f"Stage {stage}"
        attrs = stage_attrs.get(stage, {})
        attrs_str = " / ".join(
            f"{k}: {html.escape(str(v))}"
            for k, v in attrs.items() if v is not None
        )
        prompt_preview = html.escape((prompts.get(stage) or "")[:120]) + "…"

        cells = [f"""
            <td style="vertical-align:top;padding:4px 8px;">
              <div style="font-size:10px;color:#888;">{html.escape(label)}</div>
              <div style="font-size:9px;color:#aaa;margin-top:2px;">{attrs_str}</div>
              <div style="font-size:8px;color:#666;margin-top:2px;font-style:italic;">{prompt_preview}</div>
            </td>"""]

        for s in steps_list:
            fname = images.get((stage, s), "")
            t = elapsed.get((stage, s), 0)
            if fname:
                img = (
                    f'<img src="{html.escape(fname)}" '
                    'style="width:176px;height:256px;object-fit:cover;'
                    'border:2px solid #2d3a1a;display:block;">'
                )
            else:
                img = (
                    '<div style="width:176px;height:256px;background:#1a1a2e;'
                    'display:flex;align-items:center;justify-content:center;'
                    'color:#555;font-size:10px;">失敗</div>'
                )
            cells.append(f"""
            <td style="padding:4px 8px;vertical-align:top;">
              {img}
              <div style="color:#666;font-size:9px;text-align:center;margin-top:2px;">{t:.1f}s</div>
            </td>""")

        rows.append(f'<tr>{"".join(cells)}</tr>')

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>LoRA: {lora_name} — {html.escape(student_id)}</title>
<style>
  body {{ background:#1a1a2e; color:#e8d5b0; font-family:sans-serif; margin:16px; }}
  h1 {{ font-family:monospace; font-size:13px; color:#d4a847; }}
  table {{ border-collapse:collapse; }}
  tr:nth-child(even) td {{ background:rgba(255,255,255,0.03); }}
  a {{ color:#d4a847; }}
</style>
</head>
<body>
<h1>LoRA: {lora_name}</h1>
<p style="color:#aaa;font-size:11px;">
  seed={html.escape(student_id)} &nbsp;|&nbsp; cfg={cfg} &nbsp;|&nbsp;
  <a href="index.html">← 回到索引</a>
</p>
<table>
  <thead><tr>
    <th style="color:#d4a847;padding:6px 12px;text-align:left;">Stage / 屬性</th>
    {th_cells}
  </tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>
<p style="color:#666;font-size:10px;margin-top:12px;">
  生成時間：{html.escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}
</p>
</body>
</html>"""


def index_html(
    student_id: str,
    scores: list[int],
    loras: list[str],
    stages: list[int],
    steps_list: list[int],
    cfg: float,
    total_ok: int,
    total: int,
) -> str:
    links = "".join(
        f'<li><a href="lora_{lora}.html">{html.escape(LORA_DISPLAY.get(lora, lora))}</a></li>'
        for lora in loras
    )
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>Journey Sweep — {html.escape(student_id)}</title>
<style>
  body {{ background:#1a1a2e; color:#e8d5b0; font-family:sans-serif; margin:24px; }}
  h1 {{ font-family:monospace; font-size:13px; color:#d4a847; }}
  li {{ margin:6px 0; }}
  a {{ color:#d4a847; font-size:13px; }}
</style>
</head>
<body>
<h1>學習旅程 × LoRA 掃描</h1>
<p style="color:#aaa;font-size:12px;">
  seed={html.escape(student_id)} &nbsp;|&nbsp;
  stages={html.escape(str(stages))} &nbsp;|&nbsp;
  steps={html.escape(str(steps_list))} &nbsp;|&nbsp;
  cfg={cfg}<br>
  各單元分數：{html.escape(" / ".join(str(s) for s in scores))}<br>
  共完成 {total_ok}/{total} 張
</p>
<ul>
{links}
</ul>
<p style="color:#666;font-size:10px;">生成時間：{html.escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</p>
</body>
</html>"""


# ─── 主程式 ────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="學習旅程 × LoRA 掃描")
    p.add_argument("--student-id", default="410520001")
    p.add_argument("--profile",    default="high", choices=["high", "mid", "low"])
    p.add_argument("--scores",     default=None)
    p.add_argument("--cfg",        type=float, default=1.0)
    p.add_argument("--steps",      default="8,9,10")
    p.add_argument("--loras",      default="moode,zart,desim,none")
    p.add_argument("--stages",     default="1,2,3,4,5,6")
    p.add_argument("--no-llm",     action="store_true")
    return p.parse_args()


async def async_main() -> None:
    args = parse_args()

    student_id = args.student_id.strip()
    seed = int(student_id)

    scores = (
        [int(s.strip()) for s in args.scores.split(",")]
        if args.scores
        else PROFILES[args.profile]
    )
    if len(scores) != 6:
        print("[錯誤] --scores 需要 6 個數字", file=sys.stderr); sys.exit(1)

    steps_list = [int(s.strip()) for s in args.steps.split(",")]
    loras      = [s.strip() for s in args.loras.split(",")]
    stages     = [int(s.strip()) for s in args.stages.split(",")]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "outputs" / "journey_sweep" / f"sweep_{student_id}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Journey Sweep")
    print(f"  seed={student_id}  cfg={args.cfg}")
    print(f"  scores: {' / '.join(str(s) for s in scores)}")
    print(f"  stages: {stages}")
    print(f"  steps:  {steps_list}")
    print(f"  loras:  {loras}")
    print(f"  輸出:   {out_dir}")
    print(f"{'='*60}\n")

    # ── Step 1: 為每個 stage 生成 prompt（只呼叫一次 LLM）──────────────────
    print("── 生成各 stage 提示詞 ──────────────────────────────────────────────")
    prompts:     dict[int, str]  = {}
    stage_attrs: dict[int, dict] = {}

    for stage in stages:
        card_cfg   = build_card_config(student_id, scores, stage)
        learn_data = build_learning_data(scores, stage)
        stage_attrs[stage] = attrs_summary(card_cfg)

        structured = build_structured_description(
            card_config=card_cfg,
            learning_data=learn_data,
            student_nickname=student_id,
            rng_seed=seed,
        )

        if args.no_llm:
            prompts[stage] = structured
            print(f"  Stage {stage}: [--no-llm] 使用結構化描述")
        else:
            print(f"  Stage {stage}: 呼叫 Ollama...", flush=True)
            t0 = time.time()
            try:
                prompts[stage] = await generate_prompt(structured)
                print(f"  Stage {stage}: 完成（{time.time()-t0:.1f}s）：{prompts[stage][:80]}...")
            except Exception as e:
                print(f"  Stage {stage}: [LLM 失敗] {e}", file=sys.stderr)
                prompts[stage] = structured
            finally:
                await unload_model()

    # 儲存 prompts
    prompts_file = out_dir / "prompts.json"
    prompts_file.write_text(
        json.dumps(
            {str(k): v for k, v in prompts.items()},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n提示詞已儲存：{prompts_file}\n")

    # ── Step 2: 生圖 ─────────────────────────────────────────────────────────
    # images[(lora, stage, steps)] = filename | ""
    images:  dict[tuple[str, int, int], str]   = {}
    elapsed: dict[tuple[str, int, int], float] = {}
    total_ok = 0
    total    = len(loras) * len(stages) * len(steps_list)

    for lora in loras:
        lora_display = LORA_DISPLAY.get(lora, lora)
        print(f"── LoRA: {lora_display} {'─'*40}")

        for stage in stages:
            for steps in steps_list:
                fname    = f"lora_{lora}_s{stage}_st{steps}_seed{seed}.png"
                out_path = out_dir / fname
                prompt   = prompts[stage]

                print(f"  [{lora}] stage={stage} steps={steps}...", end=" ", flush=True)
                t0 = time.time()
                result = subprocess.run(
                    [
                        PYTHON_BIN, str(GEN_SINGLE),
                        "--prompt", prompt,
                        "--seed",   str(seed),
                        "--lora",   lora,
                        "--cfg",    str(args.cfg),
                        "--steps",  str(steps),
                    ],
                    capture_output=True,
                    text=True,
                )
                t = time.time() - t0

                # 找 OUTPUT_PATH
                gen_path: Path | None = None
                for line in result.stdout.splitlines():
                    if line.startswith("OUTPUT_PATH="):
                        gen_path = Path(line.split("=", 1)[1].strip())
                        break

                ok = result.returncode == 0 and gen_path and gen_path.exists()
                if ok:
                    import shutil
                    shutil.copy2(gen_path, out_path)
                    images[(lora, stage, steps)]  = fname
                    elapsed[(lora, stage, steps)] = t
                    total_ok += 1
                    print(f"OK {t:.1f}s")
                else:
                    images[(lora, stage, steps)]  = ""
                    elapsed[(lora, stage, steps)] = t
                    err = result.stderr.strip()[-100:] if result.stderr else ""
                    print(f"FAIL {t:.1f}s — {err}", file=sys.stderr)

        print()

    # ── Step 3: HTML 報告 ─────────────────────────────────────────────────────
    print("── 生成 HTML 報告 ──")

    for lora in loras:
        page_images  = {(s, st): images.get((lora, s, st), "")
                        for s in stages for st in steps_list}
        page_elapsed = {(s, st): elapsed.get((lora, s, st), 0)
                        for s in stages for st in steps_list}
        page_html = lora_page_html(
            student_id=student_id,
            lora=lora,
            stages=stages,
            steps_list=steps_list,
            images=page_images,
            elapsed=page_elapsed,
            prompts=prompts,
            stage_attrs=stage_attrs,
            cfg=args.cfg,
        )
        page_path = out_dir / f"lora_{lora}.html"
        page_path.write_text(page_html, encoding="utf-8")
        print(f"  {page_path.name}")

    idx = index_html(
        student_id=student_id,
        scores=scores,
        loras=loras,
        stages=stages,
        steps_list=steps_list,
        cfg=args.cfg,
        total_ok=total_ok,
        total=total,
    )
    index_path = out_dir / "index.html"
    index_path.write_text(idx, encoding="utf-8")
    print(f"  {index_path.name}")

    print(f"\n{'='*60}")
    print(f"完成！{total_ok}/{total} 張成功")
    print(f"索引：{index_path}")
    print(f"{'='*60}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
