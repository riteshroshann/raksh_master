import hashlib
import uuid
from typing import Optional

import structlog

from config import settings

logger = structlog.get_logger()


class ChunkedUploadManager:
    def __init__(self):
        self._active_uploads: dict[str, dict] = {}

    def init_upload(
        self,
        filename: str,
        total_size_bytes: int,
        total_chunks: int,
        member_id: str,
        content_type: str,
    ) -> dict:
        upload_id = str(uuid.uuid4())

        self._active_uploads[upload_id] = {
            "upload_id": upload_id,
            "filename": filename,
            "total_size_bytes": total_size_bytes,
            "total_chunks": total_chunks,
            "member_id": member_id,
            "content_type": content_type,
            "received_chunks": {},
            "completed": False,
        }

        logger.info(
            "chunked_upload_initialized",
            upload_id=upload_id,
            filename=filename,
            total_size=total_size_bytes,
            total_chunks=total_chunks,
        )

        return {
            "upload_id": upload_id,
            "chunk_size_bytes": settings.chunk_size_bytes,
            "total_chunks": total_chunks,
        }

    def add_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes) -> dict:
        upload = self._active_uploads.get(upload_id)
        if not upload:
            raise ValueError(f"Upload {upload_id} not found")

        if upload["completed"]:
            raise ValueError(f"Upload {upload_id} already completed")

        if chunk_index >= upload["total_chunks"]:
            raise ValueError(f"Chunk index {chunk_index} exceeds total chunks {upload['total_chunks']}")

        if chunk_index in upload["received_chunks"]:
            raise ValueError(f"Chunk {chunk_index} already received")

        upload["received_chunks"][chunk_index] = chunk_data

        received = len(upload["received_chunks"])
        total = upload["total_chunks"]

        logger.info(
            "chunk_received",
            upload_id=upload_id,
            chunk_index=chunk_index,
            chunk_size=len(chunk_data),
            progress=f"{received}/{total}",
        )

        return {
            "upload_id": upload_id,
            "chunk_index": chunk_index,
            "received_chunks": received,
            "total_chunks": total,
            "complete": received == total,
        }

    def is_complete(self, upload_id: str) -> bool:
        upload = self._active_uploads.get(upload_id)
        if not upload:
            return False
        return len(upload["received_chunks"]) == upload["total_chunks"]

    def assemble(self, upload_id: str) -> tuple[bytes, dict]:
        upload = self._active_uploads.get(upload_id)
        if not upload:
            raise ValueError(f"Upload {upload_id} not found")

        if not self.is_complete(upload_id):
            missing = []
            for i in range(upload["total_chunks"]):
                if i not in upload["received_chunks"]:
                    missing.append(i)
            raise ValueError(f"Upload incomplete. Missing chunks: {missing}")

        assembled = b""
        for i in range(upload["total_chunks"]):
            assembled += upload["received_chunks"][i]

        content_hash = hashlib.sha256(assembled).hexdigest()
        upload["completed"] = True

        logger.info(
            "chunked_upload_assembled",
            upload_id=upload_id,
            total_size=len(assembled),
            content_hash=content_hash[:16],
        )

        metadata = {
            "filename": upload["filename"],
            "member_id": upload["member_id"],
            "content_type": upload["content_type"],
            "content_hash": content_hash,
            "total_size": len(assembled),
        }

        return assembled, metadata

    def get_upload_status(self, upload_id: str) -> Optional[dict]:
        upload = self._active_uploads.get(upload_id)
        if not upload:
            return None

        received = len(upload["received_chunks"])
        total = upload["total_chunks"]

        return {
            "upload_id": upload_id,
            "filename": upload["filename"],
            "total_chunks": total,
            "received_chunks": received,
            "complete": received == total,
            "assembled": upload["completed"],
        }

    def cleanup(self, upload_id: str) -> None:
        if upload_id in self._active_uploads:
            del self._active_uploads[upload_id]
            logger.info("chunked_upload_cleaned_up", upload_id=upload_id)

    def cleanup_stale(self, max_age_seconds: int = 3600) -> int:
        cleaned = 0
        stale_ids = []
        for uid, upload in self._active_uploads.items():
            if not upload["completed"] and len(upload["received_chunks"]) == 0:
                stale_ids.append(uid)

        for uid in stale_ids:
            self.cleanup(uid)
            cleaned += 1

        return cleaned


chunked_upload_manager = ChunkedUploadManager()
