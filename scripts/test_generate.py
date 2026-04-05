#!/usr/bin/env python3
"""手動測試腳本 — 向本機 AI Worker 送出一個生圖請求。

使用方式：
    conda activate sd-env
    python scripts/test_generate.py
"""

import json
import os
import sys
import time
import uuid

import httpx

BASE_URL = "http://localhost:8000"

# 測試用的 request body
TEST_REQUEST = {
    "job_id": str(uuid.uuid4()),
    "card_id": 1,
    "student_id": "411234567",
    "card_config": {
        "race": "elf",
        "gender": "female",
        "class": "mage",
        "body": "slim",
        "equipment": "legendary",
        "weapon_quality": "artifact",
        "weapon_type": "staff",
        "background": "magic_tower",
        "expression": "confident",
        "pose": "battle_ready",
        "border": "gold",
        "level": 8,
    },
    "learning_data": {
        "unit_scores": {
            "unit_1": {"quiz": 92, "homework": 85, "completion": 95},
            "unit_2": {"quiz": 88, "homework": 78, "completion": 90},
            "unit_3": {"quiz": 76, "homework": 80, "completion": 85},
            "unit_4": {"quiz": 82, "homework": 70, "completion": 80},
            "unit_5": {"quiz": 90, "homework": 88, "completion": 92},
        },
        "overall_completion": 88.4,
    },
    "callback_url": f"{os.getenv('WEB_SERVER_BASE_URL', 'http://192.168.60.111')}/api/internal/generation-callback",
}


def main():
    print("=" * 60)
    print("Scholaverse AI Worker — 手動測試")
    print("=" * 60)

    # 1. 健康檢查
    print("\n[1] 健康檢查...")
    try:
        resp = httpx.get(f"{BASE_URL}/api/health", timeout=10.0)
        print(f"    Status: {resp.status_code}")
        print(f"    Body:   {json.dumps(resp.json(), indent=2)}")
    except Exception as e:
        print(f"    失敗: {e}")
        print("    請確認服務已啟動: uvicorn main:app --host 0.0.0.0 --port 8000")
        sys.exit(1)

    # 2. 提交生圖任務
    print(f"\n[2] 提交生圖任務 (job_id={TEST_REQUEST['job_id']})...")
    resp = httpx.post(f"{BASE_URL}/api/generate", json=TEST_REQUEST, timeout=10.0)
    print(f"    Status: {resp.status_code}")
    print(f"    Body:   {json.dumps(resp.json(), indent=2)}")

    if resp.status_code != 202:
        print("    任務提交失敗!")
        sys.exit(1)

    job_id = TEST_REQUEST["job_id"]

    # 3. 輪詢任務狀態
    print(f"\n[3] 輪詢任務狀態 (每 5 秒)...")
    while True:
        time.sleep(5)
        resp = httpx.get(f"{BASE_URL}/api/jobs/{job_id}", timeout=10.0)
        data = resp.json()
        status = data["status"]
        print(f"    [{time.strftime('%H:%M:%S')}] Status: {status}")

        if status == "completed":
            print(f"\n    任務完成!")
            print(f"    Image:     {data.get('image_path')}")
            print(f"    Thumbnail: {data.get('thumbnail_path')}")
            print(f"    Prompt:    {data.get('prompt', '')[:100]}...")
            break
        elif status == "failed":
            print(f"\n    任務失敗!")
            print(f"    Error: {data.get('error')}")
            break

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
