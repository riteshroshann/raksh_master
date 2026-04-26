import uuid
from datetime import datetime

import httpx
import structlog

from config import settings

logger = structlog.get_logger()


class StorageService:
    def __init__(self):
        self._base_url = f"{settings.supabase_url}/storage/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
        }
        self._bucket = "documents"

    async def store_original(self, contents: bytes, filename: str, member_id: str) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_extension = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
        unique_id = str(uuid.uuid4())[:8]
        storage_path = f"{member_id}/{timestamp}_{unique_id}.{file_extension}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                await client.post(
                    f"{self._base_url}/bucket",
                    headers=self._headers,
                    json={"id": self._bucket, "name": self._bucket, "public": False},
                )
            except Exception:
                pass

            content_type = self._detect_content_type(file_extension)

            upload_headers = {
                **self._headers,
                "Content-Type": content_type,
            }

            response = await client.post(
                f"{self._base_url}/object/{self._bucket}/{storage_path}",
                headers=upload_headers,
                content=contents,
            )

            if response.status_code not in (200, 201):
                logger.error(
                    "storage_upload_failed",
                    status=response.status_code,
                    detail=response.text,
                    path=storage_path,
                )
                raise RuntimeError(f"Storage upload failed: {response.status_code}")

        logger.info(
            "file_stored",
            storage_path=storage_path,
            size_bytes=len(contents),
            member_id=member_id,
        )

        return storage_path

    async def get_signed_url(self, storage_path: str, expires_in: int = 3600) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/object/sign/{self._bucket}/{storage_path}",
                headers=self._headers,
                json={"expiresIn": expires_in},
            )

            if response.status_code != 200:
                logger.error("signed_url_failed", status=response.status_code, path=storage_path)
                raise RuntimeError(f"Signed URL generation failed: {response.status_code}")

            data = response.json()
            return f"{self._base_url}{data['signedURL']}"

    def _detect_content_type(self, extension: str) -> str:
        content_types = {
            "pdf": "application/pdf",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "heic": "image/heic",
            "tiff": "image/tiff",
            "tif": "image/tiff",
            "dcm": "application/dicom",
        }
        return content_types.get(extension.lower(), "application/octet-stream")
