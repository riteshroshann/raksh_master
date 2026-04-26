import asyncio
import hashlib
import os
import time
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()


class FolderWatchAgent:
    def __init__(self):
        self._watch_path = os.getenv("FOLDER_WATCH_PATH", "/watch")
        self._api_url = os.getenv("INGESTION_API_URL", "http://localhost:8001")
        self._api_key = os.getenv("INGESTION_API_KEY", "local-dev-key-change-in-prod")
        self._member_id = os.getenv("FOLDER_WATCH_MEMBER_ID", "00000000-0000-0000-0000-000000000001")
        self._poll_interval = int(os.getenv("FOLDER_WATCH_POLL_INTERVAL", "10"))
        self._processed_hashes: set[str] = set()
        self._processed_files: set[str] = set()
        self._supported_extensions = {
            ".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif",
            ".dcm", ".dicom", ".heic",
        }
        self._quarantine_path = os.path.join(self._watch_path, ".quarantine")
        self._archive_path = os.path.join(self._watch_path, ".archive")

    def _compute_file_hash(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _is_supported_file(self, filename: str) -> bool:
        ext = Path(filename).suffix.lower()
        return ext in self._supported_extensions

    def _get_content_type(self, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        content_types = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
            ".dcm": "application/dicom",
            ".dicom": "application/dicom",
            ".heic": "image/heic",
        }
        return content_types.get(ext, "application/octet-stream")

    def scan_directory(self) -> list[str]:
        if not os.path.exists(self._watch_path):
            logger.warning("watch_directory_not_found", path=self._watch_path)
            return []

        new_files = []

        for root, dirs, files in os.walk(self._watch_path):
            dirs[:] = [d for d in dirs if d not in (".quarantine", ".archive", ".processed")]

            for filename in files:
                file_path = os.path.join(root, filename)

                if not self._is_supported_file(filename):
                    continue

                if file_path in self._processed_files:
                    continue

                try:
                    file_hash = self._compute_file_hash(file_path)
                    if file_hash in self._processed_hashes:
                        logger.info("duplicate_file_skipped", path=file_path, hash=file_hash[:16])
                        self._processed_files.add(file_path)
                        continue
                except Exception as exc:
                    logger.error("hash_computation_failed", path=file_path, error=str(exc))
                    continue

                new_files.append(file_path)

        return new_files

    def ingest_file(self, file_path: str) -> dict:
        import httpx

        filename = os.path.basename(file_path)
        content_type = self._get_content_type(filename)

        try:
            file_hash = self._compute_file_hash(file_path)
        except Exception as exc:
            return {"status": "error", "detail": f"Hash failed: {exc}"}

        if file_hash in self._processed_hashes:
            return {"status": "duplicate"}

        with open(file_path, "rb") as f:
            file_data = f.read()

        if len(file_data) == 0:
            self._quarantine_file(file_path, "empty_file")
            return {"status": "quarantined", "reason": "empty_file"}

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self._api_url}/ingest/upload",
                    files={"file": (filename, file_data, content_type)},
                    data={"member_id": self._member_id},
                    headers={"x-api-key": self._api_key},
                )

                if response.status_code == 200:
                    result = response.json()
                    self._processed_hashes.add(file_hash)
                    self._processed_files.add(file_path)
                    self._archive_file(file_path)

                    logger.info(
                        "folder_watch_ingested",
                        filename=filename,
                        doc_type=result.get("doc_type"),
                        ingest_id=result.get("ingest_id"),
                    )

                    return {"status": "ingested", **result}

                elif response.status_code == 409:
                    self._processed_hashes.add(file_hash)
                    self._processed_files.add(file_path)
                    logger.info("folder_watch_duplicate", filename=filename)
                    return {"status": "duplicate"}

                elif response.status_code == 415:
                    self._quarantine_file(file_path, "unsupported_type")
                    return {"status": "quarantined", "reason": "unsupported_type"}

                elif response.status_code == 422:
                    self._quarantine_file(file_path, "classification_failed")
                    return {"status": "quarantined", "reason": "classification_failed"}

                else:
                    logger.error("folder_watch_ingest_failed", filename=filename, status=response.status_code)
                    return {"status": "error", "detail": response.text}

        except Exception as exc:
            logger.error("folder_watch_error", filename=filename, error=str(exc))
            return {"status": "error", "detail": str(exc)}

    def _quarantine_file(self, file_path: str, reason: str):
        os.makedirs(self._quarantine_path, exist_ok=True)
        filename = os.path.basename(file_path)
        dest = os.path.join(self._quarantine_path, f"{reason}_{filename}")

        try:
            os.rename(file_path, dest)
            logger.warning("file_quarantined", original=file_path, destination=dest, reason=reason)
        except Exception as exc:
            logger.error("quarantine_failed", file=file_path, error=str(exc))

    def _archive_file(self, file_path: str):
        os.makedirs(self._archive_path, exist_ok=True)
        filename = os.path.basename(file_path)
        dest = os.path.join(self._archive_path, filename)

        try:
            os.rename(file_path, dest)
            logger.info("file_archived", original=file_path, destination=dest)
        except Exception as exc:
            logger.error("archive_failed", file=file_path, error=str(exc))

    def run_scan_cycle(self) -> dict:
        new_files = self.scan_directory()

        results = {
            "scanned": len(new_files),
            "ingested": 0,
            "duplicates": 0,
            "quarantined": 0,
            "errors": 0,
        }

        for file_path in new_files:
            result = self.ingest_file(file_path)
            status = result.get("status", "error")

            if status == "ingested":
                results["ingested"] += 1
            elif status == "duplicate":
                results["duplicates"] += 1
            elif status == "quarantined":
                results["quarantined"] += 1
            else:
                results["errors"] += 1

        logger.info("folder_watch_cycle_complete", **results)
        return results

    def get_stats(self) -> dict:
        return {
            "watch_path": self._watch_path,
            "processed_files": len(self._processed_files),
            "unique_hashes": len(self._processed_hashes),
            "supported_extensions": list(self._supported_extensions),
        }


def start_folder_watch():
    agent = FolderWatchAgent()

    logger.info("folder_watch_started", path=agent._watch_path, interval=agent._poll_interval)

    while True:
        agent.run_scan_cycle()
        time.sleep(agent._poll_interval)


if __name__ == "__main__":
    start_folder_watch()
