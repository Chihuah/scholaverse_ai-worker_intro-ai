"""GET /api/health — 健康檢查 + GET /api/images/{path} — 靜態圖片（Mock 模式）"""

import logging
import shutil
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.config import settings
from app.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    """回傳服務健康狀態，包含 GPU、Ollama、sd-cli 可用性。"""
    job_queue = request.app.state.job_queue

    # 檢查 GPU（nvidia-smi 是否存在）
    gpu_available = shutil.which("nvidia-smi") is not None

    # 檢查 Ollama
    ollama_available = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            ollama_available = resp.status_code == 200
    except Exception:
        pass

    # 檢查 sd-cli
    sd_cli_available = Path(settings.sd_cli_path).exists()

    return HealthResponse(
        status="ok",
        gpu_available=gpu_available,
        ollama_available=ollama_available,
        sd_cli_available=sd_cli_available,
        queue_size=job_queue.queue_size,
        current_job=job_queue.current_job_id,
    )


@router.get("/images/{file_path:path}")
async def serve_image(file_path: str):
    """Mock 模式下提供圖片靜態檔案。"""
    full_path = Path(settings.output_dir) / file_path

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(str(full_path), media_type="image/png")
