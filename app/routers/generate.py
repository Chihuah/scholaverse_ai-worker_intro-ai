"""POST /api/generate — 提交卡牌生成請求"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.queue import GenerationJob
from app.schemas import GenerateRequest, GenerateResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generate"])


@router.post("/generate", response_model=GenerateResponse, status_code=202)
async def create_generation_job(body: GenerateRequest, request: Request):
    """接收生圖任務，加入佇列後立即回應 202。"""
    job_queue = request.app.state.job_queue

    # 檢查佇列是否已滿
    if job_queue.queue_size >= settings.max_queue_size:
        logger.warning("Queue full (%d/%d), rejecting job %s", job_queue.queue_size, settings.max_queue_size, body.job_id)
        return JSONResponse(
            status_code=503,
            content={"detail": "Service busy. Queue is full, please try again later."},
        )

    # 驗證 backend 值
    backend = (body.backend or "local").lower()
    if backend not in ("local", "cloud"):
        return JSONResponse(
            status_code=400,
            content={"detail": f"Invalid backend '{body.backend}'. Use 'local' or 'cloud'."},
        )

    # 建立 GenerationJob
    job = GenerationJob(
        job_id=body.job_id,
        card_id=body.card_id,
        student_id=body.student_id,
        student_nickname=body.student_nickname,
        requested_seed=body.seed,
        ollama_model_override=body.ollama_model_override,
        card_config=body.card_config.model_dump(by_alias=True),
        learning_data=body.learning_data.model_dump(),
        style_hint=body.style_hint,
        callback_url=body.callback_url,
        backend=backend,
        backend_used=backend,
        cloud_model=body.cloud_model if backend == "cloud" else None,
        reference_card_id=body.reference_card_id,
    )

    # 加入佇列
    position = await job_queue.enqueue(job)
    logger.info("Job %s queued at position %d", body.job_id, position)

    return GenerateResponse(
        job_id=body.job_id,
        status="queued",
        position=position,
        message="Job accepted and queued for processing.",
    )
