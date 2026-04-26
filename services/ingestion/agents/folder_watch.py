import hashlib
import os
import time

import httpx
import structlog
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = structlog.get_logger()

PROCESSED_HASHES: set[str] = set()

SUPPORTED_EXTENSIONS = {".pdf", ".tiff", ".tif", ".dcm", ".jpg", ".jpeg", ".png"}


class FolderWatchHandler(FileSystemEventHandler):
    def __init__(self, api_url: str, api_key: str, member_id: str | None = None):
        self._api_url = api_url
        self._api_key = api_key
        self._member_id = member_id or "00000000-0000-0000-0000-000000000001"

    def on_created(self, event):
        if event.is_directory:
            return

        file_ext = os.path.splitext(event.src_path)[1].lower()
        if file_ext not in SUPPORTED_EXTENSIONS:
            logger.info("file_skipped", path=event.src_path, reason="unsupported_extension")
            return

        try:
            time.sleep(1)

            with open(event.src_path, "rb") as f:
                contents = f.read()

            if len(contents) == 0:
                logger.warning("empty_file_skipped", path=event.src_path)
                return

            content_hash = hashlib.sha256(contents).hexdigest()

            if content_hash in PROCESSED_HASHES:
                logger.info("duplicate_skipped", path=event.src_path, hash=content_hash[:16])
                return

            PROCESSED_HASHES.add(content_hash)

            self._ingest_file(event.src_path, contents)

        except Exception as exc:
            logger.error("folder_watch_error", path=event.src_path, error=str(exc))

    def _ingest_file(self, path: str, contents: bytes):
        filename = os.path.basename(path)

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{self._api_url}/ingest/upload",
                files={"file": (filename, contents)},
                data={"member_id": self._member_id},
                headers={"x-api-key": self._api_key},
            )

            if response.status_code == 200:
                logger.info(
                    "folder_watch_ingested",
                    filename=filename,
                    doc_type=response.json().get("doc_type"),
                )
            elif response.status_code == 409:
                logger.info("folder_watch_duplicate", filename=filename)
            else:
                logger.error(
                    "folder_watch_ingest_failed",
                    filename=filename,
                    status=response.status_code,
                    detail=response.text,
                )


def start_folder_watch():
    watch_path = os.getenv("FOLDER_WATCH_PATH", "/watch")
    api_url = os.getenv("INGESTION_API_URL", "http://localhost:8001")
    api_key = os.getenv("INGESTION_API_KEY", "local-dev-key-change-in-prod")
    member_id = os.getenv("FOLDER_WATCH_MEMBER_ID")

    os.makedirs(watch_path, exist_ok=True)

    handler = FolderWatchHandler(api_url=api_url, api_key=api_key, member_id=member_id)
    observer = Observer()
    observer.schedule(handler, watch_path, recursive=False)
    observer.start()

    logger.info("folder_watch_started", path=watch_path)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("folder_watch_stopped")

    observer.join()


if __name__ == "__main__":
    start_folder_watch()
