"""FastAPI app 入口 — Scholaverse AI Worker"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.queue import JobQueue
from app.routers import generate, health, jobs
from app.worker import worker_loop

# --- Logging 設定 ---
logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan：啟動時建立 JobQueue + worker_loop，關閉時等待任務完成。"""
    # --- Startup ---
    logger.info("Starting AI Worker service...")

    # 建立任務佇列
    job_queue = JobQueue()
    app.state.job_queue = job_queue
    logger.info("JobQueue created (max_size=%d)", settings.max_queue_size)

    # 啟動 worker loop
    worker_task = asyncio.create_task(worker_loop(job_queue))
    logger.info("Worker loop started")

    logger.info(
        "AI Worker ready — listening on %s:%d (env=%s)",
        settings.app_host,
        settings.app_port,
        settings.app_env,
    )

    yield

    # --- Shutdown ---
    logger.info("Shutting down AI Worker...")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("AI Worker shutdown complete")


# --- FastAPI App ---
app = FastAPI(
    title="Scholaverse AI Worker",
    description="AI 圖片生成服務 — 接收 RPG 角色配置，產出卡牌圖片",
    version="0.1.0",
    lifespan=lifespan,
)

# --- 註冊 Routers ---
app.include_router(generate.router)
app.include_router(jobs.router)
app.include_router(health.router)


@app.get("/")
async def root():
    """根路徑，簡單的服務資訊。"""
    return {
        "service": "Scholaverse AI Worker",
        "version": "0.1.0",
        "docs": "/docs",
    }
