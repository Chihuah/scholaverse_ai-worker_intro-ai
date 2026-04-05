#!/usr/bin/env python3
"""批次多圖測試腳本 — 一次送出 5 張圖片生成請求，每張隨機組合 RPG 屬性。

使用方式：
    conda activate sd-env
    python scripts/test_batch_generate.py

功能：
  - 隨機生成 5 組不重複的 card_config
  - 每組任務送出後即時顯示屬性摘要
  - 並行輪詢所有任務狀態，直到全部完成/失敗
  - 最終列出各圖使用的 LoRA（由 worker log 顯示，腳本層從 prompt 解析）
"""

import json
import os
import random
import sys
import time
import uuid

import httpx

BASE_URL = "http://localhost:8000"

# ── 屬性池（與 prompt_builder.py 對應）─────────────────────────────────────
RACES    = ["elf", "human", "orc", "dwarf", "dragon", "pixie", "plant", "slime"]
GENDERS  = ["male", "female", "neutral"]
CLASSES  = ["archmage", "paladin", "ranger", "assassin", "priest",
            "mage", "warrior", "archer", "militia", "apprentice", "farmer"]
BODIES   = ["muscular", "standard", "slim"]
EQUIPS   = ["legendary", "fine", "common", "crude", "broken"]
WPN_QUALITIES = ["artifact", "fine", "common", "crude", "primitive"]
WPN_TYPES     = ["sword", "shield", "staff", "spellbook", "bow",
                 "dagger", "mace", "spear", "short_sword", "club",
                 "wooden_stick", "stone"]
BACKGROUNDS   = ["palace_throne", "dragon_lair", "sky_city", "castle",
                 "magic_tower", "town", "market", "village", "wilderness", "ruins"]
EXPRESSIONS   = ["regal", "passionate", "confident", "calm", "weary"]
POSES         = ["charging", "battle_ready", "standing", "crouching"]
BORDERS       = ["copper", "silver", "gold"]

# ── LoRA 選項（與 sd_runner.py 同步）─────────────────────────────────────────
LORA_OPTIONS = [
    "<lora:moode_fantasy_Impressions:0.5>",
    "<lora:Z-Art-3:0.5>",
    "<lora:Desimulate:0.5>",
    None,
]

NICKNAMES = ["Alice", "Bob", "Carol", "Dave", "Eva"]


# ── 隨機組合一組 card_config ──────────────────────────────────────────────────

def random_card_config() -> dict:
    """隨機組合一組合法的 card_config。"""
    level = random.randint(1, 10)
    # 武器品質與類型，50% 機率省略其中之一
    wq = random.choice(WPN_QUALITIES) if random.random() > 0.15 else None
    wt = random.choice(WPN_TYPES)     if random.random() > 0.05 else None

    config = {
        "race":       random.choice(RACES),
        "gender":     random.choice(GENDERS),
        "class":      random.choice(CLASSES),
        "body":       random.choice(BODIES),
        "equipment":  random.choice(EQUIPS),
        "background": random.choice(BACKGROUNDS),
        "expression": random.choice(EXPRESSIONS),
        "pose":       random.choice(POSES),
        "border":     random.choice(BORDERS),
        "level":      level,
    }
    if wq:
        config["weapon_quality"] = wq
    if wt:
        config["weapon_type"] = wt

    return config


def random_learning_data() -> dict:
    """隨機產生學習數據。"""
    num_units = random.randint(3, 6)
    unit_scores = {}
    for i in range(1, num_units + 1):
        unit_scores[f"unit_{i}"] = {
            "quiz":       round(random.uniform(40, 100), 1),
            "homework":   round(random.uniform(50, 100), 1),
            "completion": round(random.uniform(60, 100), 1),
        }
    overall = round(random.uniform(40, 100), 1)
    return {"unit_scores": unit_scores, "overall_completion": overall}


# ── 屬性摘要顯示 ──────────────────────────────────────────────────────────────

def format_config_summary(idx: int, job_id: str, config: dict, nickname: str, learning: dict) -> str:
    """格式化單張圖片的屬性摘要，方便閱讀。"""
    wq = config.get("weapon_quality", "—")
    wt = config.get("weapon_type", "—")
    oc = learning["overall_completion"]

    lines = [
        f"  ┌─ 圖片 #{idx}  job_id={job_id[:8]}…",
        f"  │  Nickname : {nickname}",
        f"  │  Race     : {config['race']:<12}  Gender : {config['gender']}",
        f"  │  Class    : {config['class']:<12}  Body   : {config['body']}",
        f"  │  Equip    : {config['equipment']:<12}  Weapon : {wt} ({wq})",
        f"  │  BG       : {config['background']:<14}  Pose   : {config['pose']}",
        f"  │  Expr     : {config['expression']:<12}  Border : {config['border']}",
        f"  │  Level    : {config['level']}/10",
        f"  │  Overall  : {oc}%  ({len(learning['unit_scores'])} units)",
        f"  └──────────────────────────────────────────",
    ]
    return "\n".join(lines)


# ── 主程式 ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("Scholaverse AI Worker — 批次多圖測試 (5 張)")
    print("=" * 64)

    # ── Step 0: 健康檢查 ──────────────────────────────────────────────────────
    print("\n[0] 健康檢查...")
    try:
        resp = httpx.get(f"{BASE_URL}/api/health", timeout=10.0)
        health = resp.json()
        print(f"    Status     : {resp.status_code}")
        print(f"    GPU        : {health.get('gpu_available')}")
        print(f"    Ollama     : {health.get('ollama_available')}")
        print(f"    sd-cli     : {health.get('sd_cli_available')}")
        print(f"    Queue size : {health.get('queue_size')}")
    except Exception as e:
        print(f"    健康檢查失敗: {e}")
        print("    請確認服務已啟動: uvicorn main:app --host 0.0.0.0 --port 8000")
        sys.exit(1)

    # ── Step 1: 建立 5 組隨機任務 ──────────────────────────────────────────────
    NUM_IMAGES = 5
    jobs_meta = []  # list of (job_id, config, nickname, learning)

    print(f"\n[1] 建立 {NUM_IMAGES} 組隨機 card_config...")

    # 確保五組 class 盡量不重複（取樣 5 個不同 class）
    sampled_classes = random.sample(CLASSES, min(NUM_IMAGES, len(CLASSES)))

    for idx in range(1, NUM_IMAGES + 1):
        config = random_card_config()
        config["class"] = sampled_classes[idx - 1]   # 強制 class 不同
        learning = random_learning_data()
        nickname = NICKNAMES[idx - 1]
        job_id   = str(uuid.uuid4())
        jobs_meta.append((job_id, config, nickname, learning))
        print(format_config_summary(idx, job_id, config, nickname, learning))

    # ── Step 2: 依序送出任務（佇列式，伺服器端本來就依序執行）─────────────────
    print(f"\n[2] 送出 {NUM_IMAGES} 個生圖任務...")
    submitted_ids = []

    for idx, (job_id, config, nickname, learning) in enumerate(jobs_meta, 1):
        payload = {
            "job_id":           job_id,
            "card_id":          idx,
            "student_id":       f"41100{idx:04d}",
            "student_nickname": nickname,
            "card_config":      config,
            "learning_data":    learning,
            "callback_url":     f"{os.getenv('WEB_SERVER_BASE_URL', 'http://192.168.60.111')}/api/internal/generation-callback",
        }
        try:
            resp = httpx.post(f"{BASE_URL}/api/generate", json=payload, timeout=10.0)
            if resp.status_code == 202:
                data = resp.json()
                print(f"    ✓ #{idx} {job_id[:8]}… 已排隊 (position={data.get('position')})")
                submitted_ids.append(job_id)
            elif resp.status_code == 503:
                print(f"    ✗ #{idx} 佇列已滿，跳過: {resp.json().get('detail')}")
            else:
                print(f"    ✗ #{idx} 提交失敗 (HTTP {resp.status_code}): {resp.text}")
        except Exception as e:
            print(f"    ✗ #{idx} 連線錯誤: {e}")

    if not submitted_ids:
        print("\n沒有成功提交任何任務，結束。")
        sys.exit(1)

    # ── Step 3: 輪詢所有已提交任務 ─────────────────────────────────────────────
    print(f"\n[3] 輪詢 {len(submitted_ids)} 個任務狀態（每 10 秒輪詢一次）...")
    print("    等待 GPU 依序處理中，可能需要數分鐘...\n")

    pending = set(submitted_ids)
    results = {}   # job_id -> final status data
    poll_count = 0
    MAX_POLLS = 120  # 最多等 120 × 10s = 20 分鐘

    while pending and poll_count < MAX_POLLS:
        time.sleep(10)
        poll_count += 1
        ts = time.strftime("%H:%M:%S")

        completed_this_round = []
        for job_id in list(pending):
            try:
                resp = httpx.get(f"{BASE_URL}/api/jobs/{job_id}", timeout=10.0)
                data = resp.json()
                status = data.get("status", "unknown")

                if status in ("completed", "failed"):
                    results[job_id] = data
                    completed_this_round.append(job_id)
                    pending.discard(job_id)

                    icon = "✓" if status == "completed" else "✗"
                    print(f"    [{ts}] {icon} {job_id[:8]}… → {status}")
                    if status == "completed":
                        print(f"             Image     : {data.get('image_path')}")
                        print(f"             Thumbnail : {data.get('thumbnail_path')}")
            except Exception as e:
                print(f"    [{ts}] ? {job_id[:8]}… 查詢失敗: {e}")

        # 仍在跑的任務
        if pending:
            # 查一下正在處理哪個
            try:
                h = httpx.get(f"{BASE_URL}/api/health", timeout=5.0).json()
                cur = h.get("current_job") or "—"
                cur_short = cur[:8] + "…" if cur and cur != "—" else cur
            except Exception:
                cur_short = "?"
            print(f"    [{ts}] 還剩 {len(pending)} 個任務排隊中… (GPU 正在處理: {cur_short})")

    # ── Step 4: 最終彙整報告 ───────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("最終報告")
    print("=" * 64)

    for idx, (job_id, config, nickname, learning) in enumerate(jobs_meta, 1):
        if job_id not in submitted_ids:
            print(f"\n圖片 #{idx} [{job_id[:8]}…] — 未提交（佇列滿）")
            continue

        data = results.get(job_id)
        if data is None:
            print(f"\n圖片 #{idx} [{job_id[:8]}…] — 逾時未完成")
            continue

        status = data.get("status")
        wq = config.get("weapon_quality", "none")
        wt = config.get("weapon_type", "none")

        print(f"\n圖片 #{idx} [{job_id[:8]}…]  狀態: {status}")
        print(f"  Nickname  : {nickname}")
        print(f"  Race/Gender/Class : {config['race']} / {config['gender']} / {config['class']}")
        print(f"  Level     : {config['level']}/10")
        print(f"  Equip     : {config['equipment']}  |  Weapon: {wt} ({wq})")
        print(f"  BG        : {config['background']}  |  Pose: {config['pose']}")
        print(f"  Expression: {config['expression']}  |  Border: {config['border']}")
        print(f"  Overall   : {learning['overall_completion']}%")

        if status == "completed":
            lora_used = data.get("lora_used") or "none"
            print(f"  LoRA      : {lora_used}")
            print(f"  Image     : {data.get('image_path')}")
            print(f"  Thumbnail : {data.get('thumbnail_path')}")
            prompt_preview = (data.get("prompt") or "")[:120]
            print(f"  Prompt    : {prompt_preview}{'…' if len(data.get('prompt') or '') > 120 else ''}")
        else:
            print(f"  Error     : {data.get('error')}")

    # ── 統計 ───────────────────────────────────────────────────────────────────
    ok  = sum(1 for d in results.values() if d.get("status") == "completed")
    err = sum(1 for d in results.values() if d.get("status") == "failed")
    print(f"\n{'─' * 64}")
    print(f"完成: {ok} 張  |  失敗: {err} 張  |  共提交: {len(submitted_ids)} 張")
    print("─" * 64)
    print("\n提示：如需查閱完整 server log，請在跑 uvicorn 的終端視窗直接觀看輸出，")
    print("      或另開終端執行：")
    print("        tail -f /tmp/ai-worker.log   # 若有導向檔案")
    print("      搜尋 LoRA 記錄關鍵字：lora=")
    print("=" * 64)


if __name__ == "__main__":
    main()
