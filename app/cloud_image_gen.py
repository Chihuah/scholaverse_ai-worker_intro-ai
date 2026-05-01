"""Cloud image generation via OpenAI's gpt-image-2 (Phase 1a).

Phase 1a covers `images.generate` only (text → image).
Image-edit (multi-image reference for character consistency) is Phase 1b.

The module is opt-in: if `settings.enable_cloud_image_gen` is False, callers
should not invoke `generate_cloud_image()` — it will raise immediately.

The OpenAI Python SDK (`openai>=1.50`) is used. Auth is via the
`OPENAI_API_KEY` environment variable (read by the SDK by default), so we
do NOT pass the key in code. We also explicitly hand it through here so
that misconfiguration fails fast with a clear error.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from pathlib import Path

import httpx
from openai import APIError, AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class CloudImageGenError(Exception):
    """Raised when cloud image generation fails. Worker should fallback to local."""


def is_enabled() -> bool:
    """Return True iff feature flag is on AND API key is present."""
    return bool(settings.enable_cloud_image_gen and settings.openai_api_key)


def _client() -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise CloudImageGenError(
            "OPENAI_API_KEY 未設定（vm-ai-worker .env 缺少 openai_api_key）"
        )
    # 分開設定 connect / read timeout：connect 短（網路斷線快速失敗），
    # read 長（gpt-image-2 實際生成時間可達數分鐘）。
    timeout = httpx.Timeout(
        connect=float(settings.cloud_image_connect_timeout),
        read=float(settings.cloud_image_timeout),
        write=30.0,
        pool=10.0,
    )
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=timeout,
        # 我們自己有 fallback 到本地，不需要 SDK 內建重試（每次重試都會
        # 再花一個 read timeout 的時間，會把總耗時推到 fallback 之前無
        # 必要地拖長）
        max_retries=settings.cloud_image_max_retries,
    )


async def generate_cloud_image(
    prompt: str,
    output_path: str,
    *,
    model: str | None = None,
    size: str | None = None,
    quality: str | None = None,
) -> dict:
    """Call OpenAI gpt-image-2 to generate an image, write PNG to `output_path`.

    Returns metadata dict::

        {
            "model": "gpt-image-2",
            "size": "880x1280",
            "quality": "medium",
            "generation_time_ms": int,
            "width": 880,
            "height": 1280,
        }

    Raises CloudImageGenError on any failure (auth, network, API).
    Caller is responsible for catching and falling back to local.
    """
    if not is_enabled():
        raise CloudImageGenError(
            "雲端生圖未啟用（enable_cloud_image_gen=False 或未設 OPENAI_API_KEY）"
        )

    model_id = model or settings.cloud_image_model
    size_str = size or settings.cloud_image_size
    quality_str = quality or settings.cloud_image_quality

    started = time.monotonic()
    logger.info(
        "[cloud] images.generate starting model=%s size=%s quality=%s prompt_len=%d",
        model_id, size_str, quality_str, len(prompt),
    )

    try:
        client = _client()
        result = await client.images.generate(
            model=model_id,
            prompt=prompt,
            size=size_str,
            quality=quality_str,
        )
    except APIError as exc:
        logger.error("[cloud] OpenAI APIError: %s", exc)
        raise CloudImageGenError(f"OpenAI API 錯誤：{exc}") from exc
    except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
        logger.error(
            "[cloud] OpenAI request timed out (read=%ds, connect=%ds)",
            settings.cloud_image_timeout,
            settings.cloud_image_connect_timeout,
        )
        raise CloudImageGenError(
            f"OpenAI 回應逾時（read {settings.cloud_image_timeout}s）"
        ) from exc
    except Exception as exc:
        logger.exception("[cloud] images.generate unexpected error")
        raise CloudImageGenError(f"雲端生圖失敗：{exc}") from exc

    if not result.data:
        raise CloudImageGenError("OpenAI 回應未包含 image data")

    b64 = getattr(result.data[0], "b64_json", None)
    if not b64:
        raise CloudImageGenError("OpenAI 回應 data[0].b64_json 為空")

    try:
        png_bytes = base64.b64decode(b64)
    except (ValueError, TypeError) as exc:
        raise CloudImageGenError(f"無法解碼回應 base64：{exc}") from exc

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png_bytes)

    elapsed_ms = int((time.monotonic() - started) * 1000)

    width, height = _parse_size(size_str)
    logger.info(
        "[cloud] images.generate done model=%s size=%s quality=%s elapsed=%dms file=%s",
        model_id, size_str, quality_str, elapsed_ms, out,
    )

    return {
        "model": model_id,
        "size": size_str,
        "quality": quality_str,
        "width": width,
        "height": height,
        "generation_time_ms": elapsed_ms,
    }


def _parse_size(size_str: str) -> tuple[int, int]:
    try:
        w, h = size_str.lower().split("x", 1)
        return int(w), int(h)
    except (ValueError, AttributeError):
        return 0, 0
