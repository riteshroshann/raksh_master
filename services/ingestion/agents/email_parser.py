import email
import imaplib
import os
import time
from email.header import decode_header
from typing import Optional

import structlog

logger = structlog.get_logger()


SUPPORTED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/heic",
    "application/dicom",
    "application/octet-stream",
}

SUPPORTED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif",
    ".dcm", ".dicom", ".heic",
}


class EmailParserAgent:
    def __init__(self):
        self._imap_host = os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com")
        self._imap_port = int(os.getenv("EMAIL_IMAP_PORT", "993"))
        self._email_address = os.getenv("EMAIL_ADDRESS", "")
        self._email_password = os.getenv("EMAIL_PASSWORD", "")
        self._api_url = os.getenv("INGESTION_API_URL", "http://localhost:8001")
        self._api_key = os.getenv("INGESTION_API_KEY", "local-dev-key-change-in-prod")
        self._member_id = os.getenv("EMAIL_DEFAULT_MEMBER_ID", "00000000-0000-0000-0000-000000000001")
        self._poll_interval = int(os.getenv("EMAIL_POLL_INTERVAL", "300"))
        self._processed_uids: set[str] = set()
        self._allowed_senders: Optional[set[str]] = None

        allowed = os.getenv("EMAIL_ALLOWED_SENDERS", "")
        if allowed:
            self._allowed_senders = {s.strip().lower() for s in allowed.split(",")}

    def _connect(self) -> imaplib.IMAP4_SSL:
        connection = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
        connection.login(self._email_address, self._email_password)
        return connection

    def _decode_header_value(self, header_value: str) -> str:
        decoded_parts = decode_header(header_value)
        parts = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                parts.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                parts.append(part)
        return " ".join(parts)

    def _is_allowed_sender(self, from_address: str) -> bool:
        if self._allowed_senders is None:
            return True

        email_addr = from_address.lower()
        if "<" in email_addr:
            email_addr = email_addr.split("<")[1].rstrip(">")

        return email_addr in self._allowed_senders

    def _is_supported_attachment(self, filename: str, content_type: str) -> bool:
        ext = os.path.splitext(filename.lower())[1] if filename else ""

        if content_type in SUPPORTED_CONTENT_TYPES:
            return True

        if ext in SUPPORTED_EXTENSIONS:
            return True

        return False

    def poll_inbox(self) -> dict:
        if not self._email_address or not self._email_password:
            logger.warning("email_not_configured")
            return {"status": "not_configured", "processed": 0}

        results = {"processed": 0, "ingested": 0, "skipped": 0, "errors": 0}

        try:
            connection = self._connect()
            connection.select("INBOX")

            status, data = connection.search(None, "UNSEEN")
            if status != "OK":
                logger.error("imap_search_failed", status=status)
                return results

            message_ids = data[0].split()

            for msg_id in message_ids:
                uid = msg_id.decode()

                if uid in self._processed_uids:
                    continue

                try:
                    result = self._process_message(connection, msg_id)
                    results["processed"] += 1

                    if result.get("attachments_ingested", 0) > 0:
                        results["ingested"] += result["attachments_ingested"]
                    else:
                        results["skipped"] += 1

                    self._processed_uids.add(uid)

                except Exception as exc:
                    logger.error("email_processing_failed", uid=uid, error=str(exc))
                    results["errors"] += 1

            connection.logout()

        except Exception as exc:
            logger.error("imap_connection_failed", error=str(exc))
            results["errors"] += 1

        logger.info("email_poll_complete", **results)
        return results

    def _process_message(self, connection: imaplib.IMAP4_SSL, msg_id: bytes) -> dict:
        status, msg_data = connection.fetch(msg_id, "(RFC822)")

        if status != "OK":
            return {"attachments_ingested": 0}

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        from_address = msg.get("From", "")
        subject = self._decode_header_value(msg.get("Subject", ""))
        date_str = msg.get("Date", "")

        if not self._is_allowed_sender(from_address):
            logger.info("email_sender_not_allowed", from_address=from_address, subject=subject)
            return {"attachments_ingested": 0}

        attachments = self._extract_attachments(msg)

        ingested_count = 0
        for attachment in attachments:
            result = self._ingest_attachment(attachment["filename"], attachment["data"], attachment["content_type"])

            if result.get("status") == "ingested":
                ingested_count += 1
                logger.info(
                    "email_attachment_ingested",
                    filename=attachment["filename"],
                    from_address=from_address,
                    subject=subject,
                )

        connection.store(msg_id, "+FLAGS", "\\Seen")

        return {"attachments_ingested": ingested_count, "total_attachments": len(attachments)}

    def _extract_attachments(self, msg: email.message.Message) -> list[dict]:
        attachments = []

        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))

            if "attachment" not in content_disposition and "inline" not in content_disposition:
                continue

            filename = part.get_filename()
            if filename:
                filename = self._decode_header_value(filename)

            content_type = part.get_content_type()

            if not filename and content_type in SUPPORTED_CONTENT_TYPES:
                ext_map = {
                    "application/pdf": ".pdf",
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/tiff": ".tiff",
                }
                ext = ext_map.get(content_type, ".bin")
                filename = f"email_attachment{ext}"

            if filename and self._is_supported_attachment(filename, content_type):
                data = part.get_payload(decode=True)
                if data and len(data) > 0:
                    attachments.append({
                        "filename": filename,
                        "data": data,
                        "content_type": content_type,
                        "size": len(data),
                    })

        return attachments

    def _ingest_attachment(self, filename: str, data: bytes, content_type: str) -> dict:
        import httpx

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self._api_url}/ingest/upload",
                    files={"file": (filename, data, content_type)},
                    data={"member_id": self._member_id},
                    headers={"x-api-key": self._api_key},
                )

                if response.status_code == 200:
                    return {"status": "ingested", **response.json()}
                elif response.status_code == 409:
                    return {"status": "duplicate"}
                else:
                    return {"status": "error", "detail": response.text}

        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    def get_stats(self) -> dict:
        return {
            "processed_uids": len(self._processed_uids),
            "imap_host": self._imap_host,
            "email_address": self._email_address[:3] + "***" if self._email_address else "",
            "allowed_senders": list(self._allowed_senders) if self._allowed_senders else "all",
        }


def start_email_parser():
    agent = EmailParserAgent()

    logger.info("email_parser_started")

    while True:
        agent.poll_inbox()
        time.sleep(agent._poll_interval)


if __name__ == "__main__":
    start_email_parser()
