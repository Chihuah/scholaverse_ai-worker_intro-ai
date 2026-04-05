"""設定管理 — 讀取 .env 環境變數"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """應用程式設定，自動從 .env 載入"""

    # --- 應用設定 ---
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # --- 路徑設定（指向 stable-diffusion.cpp 目錄下的檔案）---
    sd_cli_path: str = "/home/chihuah/stable-diffusion.cpp/build/bin/sd-cli"
    model_path: str = "/home/chihuah/stable-diffusion.cpp/models/z-image-turbo-Q8_0.gguf"
    vae_path: str = "/home/chihuah/stable-diffusion.cpp/models/FLUX_ae.safetensors"
    llm_model_path: str = "/home/chihuah/stable-diffusion.cpp/models/Qwen3-4b-Z-Image-Engineer-V4-Q8_0.gguf"
    lora_dir: str = "/home/chihuah/stable-diffusion.cpp/models/lora"
    output_dir: str = "./outputs"

    # --- sd-cli 預設參數 ---
    default_height: int = 1280
    default_width: int = 880
    default_steps: int = 10
    default_cfg: float = 1.0
    default_prompt_prefix: str = (
        "<lora:moode_fantasy_Impressions:0.5> "
        "Digital painting, epic fantasy art, painterly texture, "
        "majestic and awe-inspiring atmosphere, high detail."
    )

    # --- Ollama 設定 ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-14b"

    # --- 外部 VM 服務 ---
    web_server_base_url: str = "http://192.168.60.111"
    db_storage_base_url: str = "http://192.168.60.112"
    use_mock_storage: bool = True

    # --- 佇列設定 ---
    max_queue_size: int = 50
    job_timeout: int = 300
    overall_job_timeout: int = 600  # 整體 job timeout（秒），涵蓋 Steps 1-5

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


# 全域單例
settings = Settings()
