"""vm-web-server 回調邏輯"""

import logging

import httpx

logger = logging.getLogger(__name__)

# 重試間隔（秒）：第 1 次失敗後等 2 秒，第 2 次等 5 秒，第 3 次等 10 秒
RETRY_DELAYS = [2, 5, 10]


async def send_callback(callback_url: str, payload: dict) -> None:
    """POST callback_url 通知 vm-web-server 任務結果。

    失敗時依序重試 3 次（間隔 2, 5, 10 秒）。
    全部失敗僅記錄 log，不 raise 例外，確保 callback 失敗不影響任務狀態。
    """
    import asyncio

    last_error: Exception | None = None

    # 初次嘗試 + 3 次重試 = 共 4 次
    for attempt in range(1, len(RETRY_DELAYS) + 2):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(callback_url, json=payload)
                resp.raise_for_status()
            logger.info(
                "Callback sent successfully to %s (attempt %d)", callback_url, attempt
            )
            return
        except Exception as e:
            last_error = e
            logger.warning(
                "Callback attempt %d failed for %s: %s", attempt, callback_url, e
            )
            # 如果還有重試機會，等待對應的間隔
            retry_index = attempt - 1
            if retry_index < len(RETRY_DELAYS):
                await asyncio.sleep(RETRY_DELAYS[retry_index])

    # 全部重試都失敗
    logger.error(
        "All callback attempts failed for %s. Last error: %s",
        callback_url,
        last_error,
    )
