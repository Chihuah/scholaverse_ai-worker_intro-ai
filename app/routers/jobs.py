"""GET /api/jobs/{job_id} — 查詢任務狀態"""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.schemas import JobStatusResponse, QueueItem, QueueResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, request: Request):
    """查詢指定任務的處理狀態。"""
    job_queue = request.app.state.job_queue
    job = job_queue.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    position = job_queue.get_queue_position(job_id)

    return JobStatusResponse(
        job_id=job.job_id,
        card_id=job.card_id,
        status=job.status,
        position=position,
        image_path=job.image_path,
        thumbnail_path=job.thumbnail_path,
        prompt=job.prompt,
        final_prompt=job.final_prompt,
        llm_model=job.llm_model,
        lora_used=job.lora_used,
        seed=job.seed,
        generated_at=job.generated_at.isoformat() if job.generated_at else None,
        error=job.error,
    )


@router.get("/queue", response_model=QueueResponse)
async def get_queue_status(request: Request):
    """回傳完整佇列狀態（current + waiting）。"""
    job_queue = request.app.state.job_queue

    # 目前處理中的 job
    current_item: QueueItem | None = None
    if job_queue.current_job_id:
        job = job_queue.get_job(job_queue.current_job_id)
        if job:
            current_item = QueueItem(
                job_id=job.job_id,
                card_id=job.card_id,
                student_id=job.student_id,
                status=job.status,
                position=0,
                created_at=job.created_at.isoformat(),
            )

    # 等待中的 jobs（從 deque 取出）
    queue_deque = job_queue._queue._queue  # type: ignore[attr-defined]
    queued_items: list[QueueItem] = []
    for index, queued_job_id in enumerate(queue_deque):
        job = job_queue.get_job(queued_job_id)
        if job:
            queued_items.append(QueueItem(
                job_id=job.job_id,
                card_id=job.card_id,
                student_id=job.student_id,
                status=job.status,
                position=index + 1,
                created_at=job.created_at.isoformat(),
            ))

    return QueueResponse(
        current_job=current_item,
        queued_jobs=queued_items,
        queue_size=job_queue.queue_size,
    )
