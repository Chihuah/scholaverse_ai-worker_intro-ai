# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- AI Worker 開發指引 -->

## 專案概述

本專案 (ai-worker) 是 Scholaverse 學習歷程卡牌平台的 **AI 圖片生成服務**。部署於 vm-ai-worker (192.168.60.110)，配有 NVIDIA RTX 5080 GPU。

核心功能：接收 vm-web-server 送來的 RPG 角色配置 (card_config) 與學習數據 (learning_data)，經 LLM prompt 生成 + sd-cli 文生圖，產出角色卡牌圖片。

## 架構位置（三台 VM）

```
vm-web-server (192.168.60.111)  — 前端 + API 閘道，送出生圖請求、接收回調
vm-ai-worker  (192.168.60.110)  — 本專案，AI 生圖服務 (GPU)
vm-db-storage (192.168.60.112)  — 圖片持久化儲存（尚未建置，目前用 mock）
```

## 技術棧

- Python 3.12+，Conda 環境 `sd-env`
- FastAPI + uvicorn（API 框架）
- Ollama（本機 LLM，用於 prompt 生成）
- sd-cli + Z-Image-Turbo（文生圖）
- httpx（HTTP 客戶端）、asyncio.Queue（任務佇列）、Pillow（縮圖）
- pytest + pytest-asyncio（測試）

## 專案目錄結構

```
ai-worker/                          # /home/chihuah/ai-worker
├── main.py                         # FastAPI app 入口
├── requirements.txt
├── .env                            # 環境變數（不入版控）
├── .env.example
├── CLAUDE.md                       # 本檔案
├── app/
│   ├── __init__.py
│   ├── config.py                   # 設定管理（讀取 .env）
│   ├── schemas.py                  # Pydantic request/response 模型
│   ├── queue.py                    # JobQueue + GenerationJob
│   ├── worker.py                   # worker_loop 主處理邏輯
│   ├── prompt_builder.py           # card_config → 結構化描述（映射表）
│   ├── llm_service.py              # Ollama API 呼叫封裝
│   ├── sd_runner.py                # sd-cli subprocess 封裝（自動加 LoRA/前綴/seed）
│   ├── storage_uploader.py         # vm-db-storage 上傳（含 mock）
│   ├── callback.py                 # vm-web-server 回調邏輯
│   └── routers/
│       ├── __init__.py
│       ├── generate.py             # POST /api/generate
│       ├── jobs.py                 # GET /api/jobs/{job_id}
│       └── health.py              # GET /api/health
├── outputs/                        # 生成圖片暫存目錄
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api.py                 # API 端點整合測試
│   ├── test_prompt_builder.py
│   ├── test_schemas.py
│   └── test_queue.py
├── scripts/
│   ├── test_generate.py            # 手動測試腳本（單筆）
│   └── test_batch_generate.py      # 手動測試腳本（批次）
└── docs/
    └── vm-ai-worker-spec.md        # 完整開發規格書
```

## sd-cli 與模型檔案（專案外部）

sd-cli 與 AI 模型位於 `/home/chihuah/stable-diffusion.cpp/`，與本專案各自獨立，透過 `.env` 環境變數指向。

```
stable-diffusion.cpp/
├── build/bin/sd-cli                        # 已編譯的文生圖執行檔
├── zimg.py                                 # sd-cli 的 Python wrapper（參考用，非本專案程式）
└── models/
    ├── z-image-turbo-Q8_0.gguf             # 主擴散模型 (~6.1GB)
    ├── FLUX_ae.safetensors                 # VAE 模型 (~320MB)
    ├── Qwen3-4b-Z-Image-Engineer-V4-Q8_0.gguf  # sd-cli 內建 LLM (~4.0GB)
    ├── lora/
    │   ├── moode_fantasy_Impressions.safetensors  # ★ 主要使用：奇幻繪畫風格 LoRA
    │   ├── Desimulate.safetensors
    │   ├── fantasy.safetensors
    │   └── Z-Art-3.safetensors
    ├── Qwen2.5-VL-7B-Instruct-UD-Q4_K_XL.gguf   # 其他模型（本專案不使用）
    ├── Qwen3-4B-Instruct-2507-Q4_K_M.gguf
    ├── qwen-image-2512-Q4_K_M.gguf
    ├── qwen-image-edit-2511-Q4_K_M.gguf
    └── qwen_image_vae.safetensors
```

## 生圖管線（五步驟）

```
vm-web-server POST /api/generate → vm-ai-worker 回 202 Accepted
  Step 1:   prompt_builder.py 用映射表將 card_config 轉為結構化描述 → 送 Ollama 產出英文 prompt
  Step 1.5: 卸載 Ollama 模型 (keep_alive=0)，釋放 GPU VRAM
  Step 2:   sd_runner.py 自動加 LoRA 觸發詞 + 風格前綴 + seed(-1 隨機) → 呼叫 sd-cli 生圖 (880×1280)
  Step 3:   Pillow 縮圖 (220×320)
  Step 4:   上傳至 vm-db-storage（或 mock 存本機 outputs/）
  Step 5:   POST callback_url 通知 vm-web-server 完成/失敗
```

### GPU VRAM 管理（重要）

Ollama (qwen2.5-14b) 與 sd-cli **不可同時佔用 GPU**，否則會 CUDA OOM。
llm_service.py 在 prompt 生成完成後必須立即呼叫 `keep_alive: 0` 卸載模型，確保 sd-cli 獨佔 GPU。

### sd-cli 呼叫方式

參考 `zimg.py` 中的 default preset，sd_runner.py 應組裝如下指令：

```bash
./build/bin/sd-cli \
  --diffusion-model models/z-image-turbo-Q8_0.gguf \
  --vae models/FLUX_ae.safetensors \
  --llm models/Qwen3-4b-Z-Image-Engineer-V4-Q8_0.gguf \
  --cfg-scale 1.0 \
  --steps 10 \
  --diffusion-fa \
  -H 1280 -W 880 \
  -o <output_path> \
  -s <seed> \
  --lora-model-dir models/lora \
  -p "<final_prompt>"
```

### Prompt 組裝職責分離

- **Ollama**：只產出角色/場景的自然語言描述，不含任何技術標籤
- **sd_runner.py**：自動在 prompt 前加上 `<lora:moode_fantasy_Impressions:0.5> Digital painting, epic fantasy art, painterly texture, majestic and awe-inspiring atmosphere, high detail.`
- **seed**：固定使用 `-1`（隨機），確保每次重新生成都能得到不同結果
- sd-cli 內建的 `--llm`（Qwen3-4b）會再對 prompt 做一層潤飾

## API 端點

| 方法 | 路徑 | 說明 | 回應碼 |
|------|------|------|--------|
| POST | `/api/generate` | 提交生圖任務（非同步，立即回應） | 202 |
| GET | `/api/jobs/{job_id}` | 查詢任務狀態 | 200 |
| GET | `/api/health` | 健康檢查 | 200 |
| GET | `/api/images/{path}` | Mock 模式下提供圖片靜態檔案 | 200 |

### 回調 API（vm-ai-worker → vm-web-server）

任務完成/失敗後 POST `callback_url`，body 格式需與 vm-web-server 的 `GenerationCallbackBody` schema 一致。

### 與 vm-db-storage 的通信

`POST http://192.168.60.112/api/images/upload`（multipart/form-data），目前以 mock 替代。

## 任務佇列

- `asyncio.Queue` 實現 FIFO，GPU 一次只處理一張圖
- FastAPI lifespan 中建立 `JobQueue` + `asyncio.create_task(worker_loop)`
- 佇列上限 50 個任務，超過回 503
- 任務狀態：queued → processing → uploading → completed / failed

## RPG 屬性映射表（prompt_builder.py 核心）

共 12 個屬性，每個代碼對應一段英文 prompt 描述。完整映射表見 `docs/vm-ai-worker-spec.md` 第 5 節。

屬性列表：race (8種)、gender (3種)、class (11種)、body (3種)、equipment (5種)、weapon_quality (5種)、weapon_type (12種)、background (10種)、expression (5種)、pose (4種)、border (3種)、level (1-10, 分4個區間)。

## 錯誤處理

| 操作 | Timeout | 失敗策略 |
|------|---------|---------|
| Ollama prompt 生成 | 60s | 標記 failed，送 callback |
| sd-cli 文生圖 | 300s | 終止 subprocess，標記 failed |
| 上傳 vm-db-storage | 60s | 重試 2 次，fallback 存本機 |
| Callback POST | 15s | 重試 3 次（間隔 2/5/10 秒） |
| 佇列已滿 (>50) | — | 回傳 HTTP 503 |

## 環境設定

### 關鍵環境變數

```env
SD_CLI_PATH=/home/chihuah/stable-diffusion.cpp/build/bin/sd-cli
MODEL_PATH=/home/chihuah/stable-diffusion.cpp/models/z-image-turbo-Q8_0.gguf
VAE_PATH=/home/chihuah/stable-diffusion.cpp/models/FLUX_ae.safetensors
LLM_MODEL_PATH=/home/chihuah/stable-diffusion.cpp/models/Qwen3-4b-Z-Image-Engineer-V4-Q8_0.gguf
LORA_DIR=/home/chihuah/stable-diffusion.cpp/models/lora
DEFAULT_PROMPT_PREFIX=<lora:moode_fantasy_Impressions:0.5> Digital painting, epic fantasy art, painterly texture, majestic and awe-inspiring atmosphere, high detail.
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-14b
USE_MOCK_STORAGE=true
```

### Conda 環境

```bash
conda activate sd-env
# Python: /home/chihuah/miniconda3/envs/sd-env/bin/python
# uvicorn: /home/chihuah/miniconda3/envs/sd-env/bin/uvicorn
```

## 常用指令

```bash
# 開發啟動
conda activate sd-env
cd /home/chihuah/ai-worker
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 測試
pytest tests/ -v

# 健康檢查
curl http://localhost:8000/api/health

# systemd 服務管理
sudo systemctl status ai-worker
sudo systemctl restart ai-worker
sudo journalctl -u ai-worker -f
```
