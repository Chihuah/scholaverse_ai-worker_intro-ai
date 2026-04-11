#!/usr/bin/env python3
"""學生學習旅程生圖腳本 — 模擬學生逐步完成 6 個單元，看角色如何演變。

每個階段對應到學生完成的單元數：
  Stage 1: 只完成 Unit 1 → 解鎖種族、性別
  Stage 2: 完成 Unit 1-2 → 加上職業
  Stage 3: 完成 Unit 1-3 → 加上服飾裝備
  Stage 4: 完成 Unit 1-4 → 加上武器品質、類型
  Stage 5: 完成 Unit 1-5 → 加上背景場景
  Stage 6: 完成 Unit 1-6 → 完整角色（表情、姿勢、外框）

使用方式：
    python scripts/student_journey.py --student-id 411234567

選項：
    --student-id    學生學號（必填，同時作為 seed 和暱稱）
    --profile       屬性等級：high / mid / low（預設 high）
    --scores        各單元自訂分數，逗號分隔 u1,u2,u3,u4,u5,u6（例：95,70,65,80,90,75）
    --lora          LoRA：moode / zart / desim / none（預設 desim）
    --cfg           CFG scale（預設 1.0）
    --steps         推理步數（預設 10）
    --stages        要生成的階段，逗號分隔（預設 1,2,3,4,5,6）
    --no-llm        不呼叫 Ollama，使用結構化描述直接送 sd-cli

輸出：
    outputs/journey/journey_{student_id}_{timestamp}/
    ├── stage1_unit1_seed{S}.png
    ├── stage2_unit12_seed{S}.png
    ├── ...
    └── index.html
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

# ─── 路徑設定 ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.prompt_builder import build_structured_description
from app.llm_service import generate_prompt, unload_model

# ─── 分數 → 屬性對應 ────────────────────────────────────────────────────────

RACE_BY_SCORE: list[tuple[int, list[str]]] = [
    (90, ["elf", "human", "orc", "dwarf", "dragon", "pixie"]),
    (70, ["human", "orc", "dwarf"]),
    (50, ["human", "goblin"]),
    (40, ["goblin", "pixie"]),
    (0,  ["plant", "slime"]),
]

GENDER_BY_LAST_DIGIT: dict[int, str] = {
    0: "male",   1: "female", 2: "male",    3: "female",
    4: "male",   5: "female", 6: "male",    7: "female",
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
    (90, "legendary"),
    (70, "fine"),
    (50, "common"),
    (40, "crude"),
    (0,  "broken"),
]

WEAPON_QUALITY_BY_SCORE: list[tuple[int, str]] = [
    (90, "artifact"),
    (70, "fine"),
    (50, "common"),
    (40, "crude"),
    (0,  "primitive"),
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
    (90, "gold"),
    (70, "silver"),
    (50, "steel"),
    (0,  "bronze"),
]

EXPRESSION_BY_SCORE: list[tuple[int, str]] = [
    (90, "regal"),
    (70, "confident"),
    (50, "calm"),
    (0,  "weary"),
]

POSE_BY_SCORE: list[tuple[int, str]] = [
    (90, "charging"),
    (70, "battle_ready"),
    (50, "standing"),
    (0,  "crouching"),
]

RARITY_BY_AVG: list[tuple[int, str]] = [
    (95, "UR"),
    (85, "SSR"),
    (70, "SR"),
    (50, "R"),
    (0,  "N"),
]

PROFILES: dict[str, list[int]] = {
    "high": [95, 92, 90, 88, 93, 91],
    "mid":  [65, 62, 68, 60, 64, 63],
    "low":  [35, 38, 32, 30, 36, 34],
}

STAGE_LABELS = [
    "Stage 1 — Unit 1：種族＋性別",
    "Stage 2 — Unit 1-2：加上職業",
    "Stage 3 — Unit 1-3：加上服飾",
    "Stage 4 — Unit 1-4：加上武器",
    "Stage 5 — Unit 1-5：加上背景",
    "Stage 6 — Unit 1-6：完整角色",
]


# ─── 輔助函式 ───────────────────────────────────────────────────────────────
def pick_by_score(table: list[tuple[int, Any]], score: int, rng: random.Random) -> Any:
    for threshold, value in table:
        if score >= threshold:
            if isinstance(value, list):
                return rng.choice(value)
            return value
    value = table[-1][1]
    return rng.choice(value) if isinstance(value, list) else value


def derive_rarity(avg: float) -> str:
    for threshold, rarity in RARITY_BY_AVG:
        if avg >= threshold:
            return rarity
    return "N"


def build_card_config(student_id: str, scores: list[int], stage: int) -> dict[str, Any]:
    """各階段 card_config，未解鎖屬性設為 None 讓 LLM 自由發揮。"""
    rng = random.Random(int(student_id))
    u = [scores[i] if stage > i else None for i in range(6)]

    config: dict[str, Any] = {}

    # Unit 1 → 種族、性別
    config["race"]   = pick_by_score(RACE_BY_SCORE, u[0], rng) if u[0] is not None else None
    config["gender"] = GENDER_BY_LAST_DIGIT.get(int(student_id[-1]), "neutral") if u[0] is not None else None

    # Unit 2 → 職業
    config["class"] = pick_by_score(CLASS_BY_SCORE, u[1], rng) if u[1] is not None else None

    # Unit 3 → 服飾
    config["equipment"] = pick_by_score(EQUIPMENT_BY_SCORE, u[2], rng) if u[2] is not None else None

    # Unit 4 → 武器（類型依職業）
    if u[3] is not None:
        config["weapon_quality"] = pick_by_score(WEAPON_QUALITY_BY_SCORE, u[3], rng)
        if u[3] >= 40 and config.get("class"):
            weapon_options = CLASS_WEAPON_MAP.get(config["class"], ["sword"])
        else:
            weapon_options = ["wooden_stick", "stone"]
        config["weapon_type"] = rng.choice(weapon_options)
    else:
        config["weapon_quality"] = None
        config["weapon_type"]    = None

    # Unit 5 → 背景
    config["background"] = pick_by_score(BACKGROUND_BY_SCORE, u[4], rng) if u[4] is not None else None

    # Unit 6 → 表情、姿勢、外框
    if u[5] is not None:
        config["expression"] = pick_by_score(EXPRESSION_BY_SCORE, u[5], rng)
        config["pose"]       = pick_by_score(POSE_BY_SCORE, u[5], rng)
        config["border"]     = pick_by_score(BORDER_BY_SCORE, u[5], rng)
    else:
        config["expression"] = None
        config["pose"]       = None
        config["border"]     = "bronze"

    completed = [s for s in u[:stage] if s is not None]
    avg = sum(completed) / len(completed) if completed else 30
    config["level"]  = max(1, min(100, int(avg)))
    config["rarity"] = derive_rarity(avg)

    return config


def build_learning_data(scores: list[int], stage: int) -> dict[str, Any]:
    return {
        "unit_scores": {f"unit_{i+1}": scores[i] for i in range(stage)},
        "overall_completion": stage / 6.0,
    }


# ─── HTML 報告 ──────────────────────────────────────────────────────────────
def generate_index_html(
    student_id: str,
    scores: list[int],
    results: list[dict],
    out_dir: Path,
    lora: str,
    cfg: float,
    steps: int,
) -> Path:
    rows = []
    for r in results:
        si = r["stage"] - 1
        label = STAGE_LABELS[si] if si < len(STAGE_LABELS) else f"Stage {r['stage']}"
        img_name = r.get("filename", "")
        cfg_info = html.escape(f"seed={r['seed']}  lora={lora}  cfg={cfg}  steps={steps}")
        attrs = r.get("attrs", {})
        attrs_html = "<br>".join(
            f"<b>{html.escape(k)}</b>: {html.escape(str(v))}"
            for k, v in attrs.items() if v is not None
        )
        elapsed_str = f"{r.get('elapsed', 0):.1f}s"

        img_tag = (
            f'<img src="{html.escape(img_name)}" '
            'style="width:220px;height:320px;object-fit:cover;border:2px solid #d4a847;">'
            if r.get("success") and img_name
            else '<div style="width:220px;height:320px;background:#333;display:flex;'
                 'align-items:center;justify-content:center;color:#888;">失敗</div>'
        )

        rows.append(f"""
        <div style="text-align:center;padding:10px;">
          <div style="color:#d4a847;font-family:monospace;font-size:9px;margin-bottom:6px;">{html.escape(label)}</div>
          {img_tag}
          <div style="color:#aaa;font-size:10px;margin-top:4px;">{cfg_info}</div>
          <div style="color:#ccc;font-size:10px;margin-top:4px;line-height:1.6;">{attrs_html}</div>
          <div style="color:#888;font-size:10px;margin-top:2px;">耗時 {html.escape(elapsed_str)}</div>
        </div>""")

    html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>學生 {html.escape(student_id)} 學習旅程</title>
<style>
  body {{ background:#1a1a2e; color:#e8d5b0; font-family:sans-serif; margin:20px; }}
  h1 {{ font-family:monospace; font-size:14px; color:#d4a847; text-align:center; }}
  .sub {{ text-align:center; color:#aaa; font-size:12px; margin-bottom:16px; }}
  .grid {{ display:flex; flex-wrap:wrap; gap:20px; justify-content:center; }}
  .meta {{ text-align:center; color:#888; font-size:11px; margin-top:20px; }}
</style>
</head>
<body>
<h1>學生學習旅程 — {html.escape(student_id)}</h1>
<div class="sub">各單元分數：{html.escape(' / '.join(str(s) for s in scores))} &nbsp;|&nbsp; Seed = {html.escape(student_id)}</div>
<div class="grid">{"".join(rows)}</div>
<div class="meta">生成時間：{html.escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))} &nbsp;|&nbsp; lora={html.escape(lora)} cfg={cfg} steps={steps}</div>
</body>
</html>"""

    index_path = out_dir / "index.html"
    index_path.write_text(html_content, encoding="utf-8")
    return index_path


# ─── 主程式 ─────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="學生學習旅程生圖腳本")
    p.add_argument("--student-id", required=True, help="學生學號（seed＋暱稱）")
    p.add_argument("--profile",    default="high", choices=["high", "mid", "low"])
    p.add_argument("--scores",     default=None,
                   help="自訂各單元分數，逗號分隔共 6 個（例：95,70,65,80,90,75）")
    p.add_argument("--lora",       default="desim",
                   help="LoRA：moode / zart / desim / none（預設 desim）")
    p.add_argument("--cfg",        type=float, default=1.0)
    p.add_argument("--steps",      type=int,   default=10)
    p.add_argument("--stages",     default="1,2,3,4,5,6")
    p.add_argument("--no-llm",     action="store_true",
                   help="不呼叫 Ollama，直接把結構化描述送 gen_single.py")
    return p.parse_args()


async def async_main() -> None:
    args = parse_args()

    student_id = args.student_id.strip()
    try:
        seed = int(student_id)
    except ValueError:
        print(f"[錯誤] --student-id 必須為純數字學號", file=sys.stderr)
        sys.exit(1)

    scores = (
        [int(s.strip()) for s in args.scores.split(",")]
        if args.scores
        else PROFILES[args.profile]
    )
    if len(scores) != 6:
        print(f"[錯誤] --scores 需要 6 個數字", file=sys.stderr)
        sys.exit(1)

    stages = [int(s.strip()) for s in args.stages.split(",")]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "outputs" / "journey" / f"journey_{student_id}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    gen_single = SCRIPTS_DIR / "gen_single.py"
    python_bin = "/home/chihuah/miniconda3/envs/sd-env/bin/python"

    print(f"\n{'='*60}")
    print(f"學生學習旅程生圖")
    print(f"  學號（Seed）: {student_id}")
    print(f"  各單元分數:  {' / '.join(str(s) for s in scores)}")
    print(f"  LoRA={args.lora}  CFG={args.cfg}  Steps={args.steps}")
    print(f"  階段: {stages}")
    print(f"  輸出: {out_dir}")
    print(f"{'='*60}\n")

    results: list[dict] = []

    for stage in stages:
        if not 1 <= stage <= 6:
            print(f"[警告] 無效階段 {stage}，跳過", file=sys.stderr)
            continue

        unit_label = "".join(str(i) for i in range(1, stage + 1))
        filename   = f"stage{stage}_unit{unit_label}_seed{seed}.png"
        output_path = out_dir / filename

        print(f"─── Stage {stage}（Unit 1-{stage} 完成）{'─'*30}")

        card_config   = build_card_config(student_id, scores, stage)
        learning_data = build_learning_data(scores, stage)

        # 屬性摘要（顯示 + HTML 報告）
        attrs = {
            "種族": card_config.get("race"),
            "性別": card_config.get("gender"),
            "職業": card_config.get("class"),
            "服飾": card_config.get("equipment"),
            "武器": (
                f"{card_config.get('weapon_quality')} {card_config.get('weapon_type')}"
                if card_config.get("weapon_quality") else None
            ),
            "背景": card_config.get("background"),
            "外框": card_config.get("border"),
            "表情": card_config.get("expression"),
            "姿勢": card_config.get("pose"),
            "等級": card_config.get("level"),
            "稀有度": card_config.get("rarity"),
        }
        for k, v in attrs.items():
            if v is not None:
                print(f"  {k}: {v}")

        # 取得 prompt
        structured_desc = build_structured_description(
            card_config=card_config,
            learning_data=learning_data,
            student_nickname=student_id,
            rng_seed=seed,
        )

        if args.no_llm:
            prompt = structured_desc
            print("  [--no-llm] 跳過 Ollama")
        else:
            print("  呼叫 Ollama...", flush=True)
            t0 = time.time()
            try:
                prompt = await generate_prompt(structured_desc)
                print(f"  LLM 完成（{time.time()-t0:.1f}s）：{prompt[:100]}...")
            except Exception as e:
                print(f"  [LLM 失敗] {e}，使用結構化描述", file=sys.stderr)
                prompt = structured_desc
            finally:
                # 卸載 Ollama 模型釋放 VRAM，確保 sd-cli 有足夠記憶體
                await unload_model()
                print("  Ollama 已卸載，VRAM 已釋放")

        # 呼叫 gen_single.py
        print(f"  生圖（seed={seed}）...", flush=True)
        t_gen = time.time()
        result = subprocess.run(
            [
                python_bin, str(gen_single),
                "--prompt", prompt,
                "--seed",   str(seed),
                "--lora",   args.lora,
                "--cfg",    str(args.cfg),
                "--steps",  str(args.steps),
            ],
            capture_output=True,
            text=True,
        )
        elapsed = time.time() - t_gen

        # 從 gen_single.py stdout 找 OUTPUT_PATH
        gen_output_path: Path | None = None
        for line in result.stdout.splitlines():
            if line.startswith("OUTPUT_PATH="):
                gen_output_path = Path(line.split("=", 1)[1].strip())
                break

        success = result.returncode == 0 and gen_output_path and gen_output_path.exists()

        # 把圖片搬到我們的 journey 目錄
        if success and gen_output_path:
            import shutil
            shutil.copy2(gen_output_path, output_path)
            print(f"  [OK] {elapsed:.1f}s → {filename}")
        else:
            err = result.stderr.strip()[-200:] if result.stderr else "(no stderr)"
            print(f"  [FAIL] {elapsed:.1f}s — {err}", file=sys.stderr)

        results.append({
            "stage":    stage,
            "success":  bool(success),
            "filename": filename if success else "",
            "elapsed":  elapsed,
            "seed":     seed,
            "attrs":    attrs,
        })
        print()

    index_path = generate_index_html(
        student_id=student_id,
        scores=scores,
        results=results,
        out_dir=out_dir,
        lora=args.lora,
        cfg=args.cfg,
        steps=args.steps,
    )

    ok_count = sum(1 for r in results if r["success"])
    print(f"\n{'='*60}")
    print(f"完成！{ok_count}/{len(results)} 張成功")
    print(f"報告：{index_path}")
    print(f"{'='*60}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
