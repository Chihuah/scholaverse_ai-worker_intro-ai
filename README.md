# Scholaverse AI Worker

> vm-ai-worker (192.168.50.110) — AI 圖片生成服務

接收 vm-web-server 送來的 RPG 角色配置與學習數據，透過 **Ollama LLM** 產出文生圖 prompt，再由 **sd-cli + Z-Image-Turbo** 生成角色卡牌圖片。

## 架構

```
vm-web-server (192.168.50.111)    vm-ai-worker (192.168.50.110)    vm-db-storage (192.168.50.112)
       │                                │                                │
       │  POST /api/generate            │                                │
       ├───────────────────────────────>│                                │
       │  202 Accepted                  │                                │
       │<───────────────────────────────┤                                │
       │                                │  Step 1: Ollama 生成 prompt     │
       │                                │  Step 1.5: 卸載模型(釋放 VRAM)  │
       │                                │  Step 2: sd-cli 文生圖          │
       │                                │  Step 3: 產生縮圖              │
       │                                │  Step 4: 上傳圖片 ────────────>│
       │  POST callback (完成/失敗)      │                                │
       │<───────────────────────────────┤  Step 5: 回調                   │
```

## 前置需求

- **NVIDIA GPU** + CUDA 驅動（本專案使用 RTX 5080）
- **Conda**（Miniconda / Anaconda）
- **Ollama**（LLM 推理服務）
- **sd-cli**（已編譯，位於 `/home/chihuah/stable-diffusion.cpp/build/bin/sd-cli`）
- **AI 模型檔案**（位於 `/home/chihuah/stable-diffusion.cpp/models/`）

## 安裝

### 1. 安裝 Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

匯入本機 GGUF 模型：

```bash
# 建立 Modelfile
echo "FROM /home/chihuah/stable-diffusion.cpp/models/Qwen2.5-14B-Instruct-GGUF.gguf" \
  > /home/chihuah/stable-diffusion.cpp/models/Modelfile.qwen2.5-14b

# 匯入模型
ollama create qwen2.5-14b -f /home/chihuah/stable-diffusion.cpp/models/Modelfile.qwen2.5-14b

# 驗證
ollama run qwen2.5-14b "Hello" --nowordwrap
```

### 2. 建立 Conda 環境並安裝依賴

```bash
conda activate sd-env
cd /home/chihuah/ai-worker
pip install -r requirements.txt
```

### 3. 設定環境變數

```bash
cp .env.example .env
# 依需求修改 .env 中的路徑與設定
```

主要設定項：

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `SD_CLI_PATH` | sd-cli 執行檔路徑 | `/home/chihuah/stable-diffusion.cpp/build/bin/sd-cli` |
| `MODEL_PATH` | 主擴散模型路徑 | `...models/z-image-turbo-Q8_0.gguf` |
| `VAE_PATH` | VAE 模型路徑 | `...models/FLUX_ae.safetensors` |
| `LLM_MODEL_PATH` | sd-cli 內建 LLM 路徑 | `...models/Qwen3-4b-Z-Image-Engineer-V4-Q8_0.gguf` |
| `LORA_DIR` | LoRA 模型目錄 | `...models/lora` |
| `OLLAMA_MODEL` | Ollama 使用的模型名稱 | `qwen2.5-14b` |
| `USE_MOCK_STORAGE` | 是否使用 Mock 儲存（圖片存本機） | `true` |

## 啟動服務

### 開發模式

```bash
conda activate sd-env
cd /home/chihuah/ai-worker
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 生產模式（systemd）

```bash
# 設為開機自動啟動
sudo systemctl enable ollama
sudo systemctl enable ai-worker

# 啟動
sudo systemctl start ollama
sudo systemctl start ai-worker

# 查看狀態
sudo systemctl status ai-worker

# 查看即時 log
sudo journalctl -u ai-worker -f
```

## API 端點

| 方法 | 路徑 | 說明 | 回應碼 |
|------|------|------|--------|
| `POST` | `/api/generate` | 提交生圖任務 | 202 |
| `GET` | `/api/jobs/{job_id}` | 查詢任務狀態 | 200 |
| `GET` | `/api/health` | 健康檢查 | 200 |
| `GET` | `/api/images/{path}` | Mock 模式下取得圖片 | 200 |
| `GET` | `/docs` | Swagger API 文件 | 200 |

### 提交生圖任務

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
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
      "level": 8
    },
    "learning_data": {
      "unit_scores": {
        "unit_1": {"quiz": 92, "homework": 85, "completion": 95},
        "unit_2": {"quiz": 88, "homework": 78, "completion": 90}
      },
      "overall_completion": 88.4
    },
    "callback_url": "http://192.168.50.111/api/internal/generation-callback"
  }'
```

### 查詢任務狀態

```bash
curl http://localhost:8000/api/jobs/550e8400-e29b-41d4-a716-446655440000
```

任務狀態流轉：`queued` → `processing` → `uploading` → `completed` / `failed`

### 健康檢查

```bash
curl http://localhost:8000/api/health
```

回應範例：

```json
{
  "status": "ok",
  "gpu_available": true,
  "ollama_available": true,
  "sd_cli_available": true,
  "queue_size": 0,
  "current_job": null
}
```

## 測試

```bash
conda activate sd-env
cd /home/chihuah/ai-worker

# 執行所有單元測試
pytest tests/ -v

# 手動端對端測試（需先啟動服務）
python scripts/test_generate.py
```

## 專案結構

```
ai-worker/
├── main.py                      # FastAPI 入口 + lifespan
├── requirements.txt
├── .env / .env.example
├── app/
│   ├── config.py                # 設定管理（讀取 .env）
│   ├── schemas.py               # Pydantic request/response 模型
│   ├── queue.py                 # JobQueue + GenerationJob
│   ├── worker.py                # worker_loop（五步驟處理流程）
│   ├── prompt_builder.py        # RPG 屬性映射表 → 結構化描述
│   ├── llm_service.py           # Ollama API 封裝（含 VRAM 卸載）
│   ├── sd_runner.py             # sd-cli subprocess 封裝 + 縮圖
│   ├── storage_uploader.py      # 圖片上傳（Mock / Real）
│   ├── callback.py              # vm-web-server 回調（含重試）
│   └── routers/
│       ├── generate.py          # POST /api/generate
│       ├── jobs.py              # GET /api/jobs/{job_id}
│       └── health.py            # GET /api/health + 靜態圖片
├── outputs/                     # 生成圖片暫存目錄
├── tests/                       # pytest 單元測試
├── scripts/
│   └── test_generate.py         # 手動測試腳本
└── docs/
    └── vm-ai-worker-spec.md     # 完整開發規格書
```

## GPU VRAM 管理

Ollama (qwen2.5-14b, ~70% VRAM) 與 sd-cli **不可同時佔用 GPU**，否則 CUDA OOM。

Worker 的處理順序確保兩者不衝突：

1. **Step 1** — Ollama 載入 GPU，生成 prompt
2. **Step 1.5** — 呼叫 `keep_alive=0` 卸載 Ollama 模型，釋放 VRAM
3. **Step 2** — sd-cli 獨佔 GPU 進行文生圖

## 錯誤處理

| 情境 | Timeout | 處理策略 |
|------|---------|---------|
| Ollama prompt 生成 | 60s | 標記 failed，送 callback |
| sd-cli 文生圖 | 300s | 終止 subprocess，標記 failed |
| 上傳 vm-db-storage | 60s | 重試 2 次，fallback 存本機 |
| Callback POST | 15s | 重試 3 次（間隔 2/5/10 秒） |
| 佇列已滿 (>50) | — | 回傳 HTTP 503 |
