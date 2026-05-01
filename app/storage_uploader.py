"""vm-db-storage 上傳模組（含 Mock 實作）"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class MockStorageUploader:
    """Mock: 圖片存在 vm-ai-worker 本機 outputs/ 目錄"""

    async def upload(
        self, file_path: str, student_id: str, card_id: int, image_type: str,
        metadata: dict | None = None,
    ) -> dict:
        # 組裝目標相對路徑（與 image_path 一致）
        if image_type == "thumbnail":
            dst_relative = f"students/{student_id}/cards/card_{card_id:03d}_thumb.png"
        else:
            dst_relative = f"students/{student_id}/cards/card_{card_id:03d}.png"

        # 確保目標子目錄存在
        dst = Path(settings.output_dir) / dst_relative
        dst.parent.mkdir(parents=True, exist_ok=True)

        # 複製檔案
        src = Path(file_path)
        shutil.copy2(str(src), str(dst))
        logger.info("Mock upload: copied %s → %s", src, dst)

        # 組裝 image_path
        if image_type == "thumbnail":
            image_path = f"/students/{student_id}/cards/card_{card_id:03d}_thumb.png"
        else:
            image_path = f"/students/{student_id}/cards/card_{card_id:03d}.png"

        return {
            "image_path": image_path,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }


class RealStorageUploader:
    """真實上傳到 vm-db-storage"""

    MAX_RETRIES = 2
    RETRY_DELAY = 2  # 秒

    async def upload(
        self, file_path: str, student_id: str, card_id: int, image_type: str,
        metadata: dict | None = None,
    ) -> dict:
        url = f"{settings.db_storage_base_url}/api/images/upload"
        last_error: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 2):  # 初次 + 2 次重試 = 共 3 次
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    with open(file_path, "rb") as f:
                        form_data: dict[str, str] = {
                            "student_id": student_id,
                            "card_id": str(card_id),
                            "image_type": image_type,
                        }
                        # db-storage 只在 image_type='full' 時寫入 generation_metadata，
                        # 因此縮圖不需要附帶 metadata
                        if metadata is not None and image_type == "full":
                            form_data["metadata"] = json.dumps(
                                metadata, ensure_ascii=False, default=str
                            )
                        resp = await client.post(
                            url,
                            files={"file": (Path(file_path).name, f, "image/png")},
                            data=form_data,
                        )
                        resp.raise_for_status()
                        return resp.json()
            except Exception as e:
                last_error = e
                logger.warning(
                    "Upload attempt %d/%d failed for %s: %s",
                    attempt,
                    self.MAX_RETRIES + 1,
                    file_path,
                    e,
                )
                if attempt <= self.MAX_RETRIES:
                    import asyncio

                    await asyncio.sleep(self.RETRY_DELAY)

        # 全部重試失敗，fallback 到 MockStorageUploader
        logger.error(
            "All upload attempts failed for %s, falling back to mock storage: %s",
            file_path,
            last_error,
        )
        fallback = MockStorageUploader()
        return await fallback.upload(
            file_path, student_id, card_id, image_type, metadata=metadata
        )


def get_uploader() -> MockStorageUploader | RealStorageUploader:
    """根據 settings.use_mock_storage 回傳對應的 uploader"""
    if settings.use_mock_storage:
        return MockStorageUploader()
    return RealStorageUploader()


async def upload_images(
    full_image_path: str, thumbnail_path: str, student_id: str, card_id: int,
    metadata: dict | None = None,
) -> dict:
    """上傳完整圖片與縮圖，回傳 {"full": ..., "thumbnail": ...}"""
    uploader = get_uploader()

    full_result = await uploader.upload(
        full_image_path, student_id, card_id,
        image_type="full", metadata=metadata,
    )
    thumb_result = await uploader.upload(
        thumbnail_path, student_id, card_id, image_type="thumbnail"
    )

    return {
        "full": full_result["image_path"],
        "thumbnail": thumb_result["image_path"],
    }
