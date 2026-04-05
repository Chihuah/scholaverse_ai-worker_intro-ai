from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class GenerationJob:
    job_id: str
    card_id: int
    student_id: str
    card_config: dict
    learning_data: dict
    style_hint: str
    callback_url: str
    student_nickname: str = "Student"
    requested_seed: int | None = None
    ollama_model_override: str | None = None
    status: str = "queued"
    prompt: str | None = None
    final_prompt: str | None = None
    llm_model: str | None = None
    lora_used: str | None = None       # 實際使用的 LoRA tag（"none" 代表未使用）
    seed: int | None = None
    image_path: str | None = None
    thumbnail_path: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    generated_at: datetime | None = None


class JobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=50)
        self._jobs: dict[str, GenerationJob] = {}
        self._current_job: str | None = None

    async def enqueue(self, job: GenerationJob) -> int:
        await self._queue.put(job.job_id)
        self._jobs[job.job_id] = job
        return self._queue.qsize()

    def get_job(self, job_id: str) -> GenerationJob | None:
        return self._jobs.get(job_id)

    def get_queue_position(self, job_id: str) -> int | None:
        """回傳 job 在佇列中的位置。
        - 0：目前正在處理
        - 1+：在等待佇列中的位置（1 為第一個等待）
        - None：job 不存在於佇列或 _current_job 中
        """
        if self._current_job == job_id:
            return 0
        queue_deque = self._queue._queue  # type: ignore[attr-defined]
        for index, queued_job_id in enumerate(queue_deque):
            if queued_job_id == job_id:
                return index + 1
        return None

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def current_job_id(self) -> str | None:
        return self._current_job