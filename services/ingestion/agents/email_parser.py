import email
import os
import time
from email.header import decode_header

import httpx
import structlog
from imapclient import IMAPClient

logger = structlog.get_logger()

SUPPORTED_ATTACHMENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
}

SKIP_ATTACHMENT_TYPES = {
    "image/gif",
    "application/pkcs7-signature",
}


class EmailParserAgent:
    def __init__(
        self,
        imap_host: str,
        imap_port: int,
        email_address: str,
        email_password: str,
        api_url: str,
        api_key: str,
        member_id: str | None = None,
    ):
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._email_address = email_address
        self._email_password = email_password
        self._api_url = api_url
        self._api_key = api_key
        self._member_id = member_id or "00000000-0000-0000-0000-000000000001"

    def poll(self):
        try:
            with IMAPClient(self._imap_host, port=self._imap_port, ssl=True) as client:
                client.login(self._email_address, self._email_password)
                client.select_folder("INBOX")

                messages = client.search(["UNSEEN"])

                logger.info("email_poll_completed", unseen_count=len(messages))

                for uid in messages:
                    self._process_message(client, uid)

        except Exception as exc:
            logger.error("email_poll_failed", error=str(exc))

    def _process_message(self, client: IMAPClient, uid: int):
        try:
            raw_messages = client.fetch([uid], ["RFC822"])
            raw_email = raw_messages[uid][b"RFC822"]
            msg = email.message_from_bytes(raw_email)

            subject = self._decode_header(msg.get("Subject", ""))
            sender = self._decode_header(msg.get("From", ""))

            logger.info("email_processing", uid=uid, subject=subject, sender=sender)

            body_context = self._extract_body_context(msg)

            attachments_processed = 0
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" not in content_disposition:
                    continue

                if content_type in SKIP_ATTACHMENT_TYPES:
                    continue

                if content_type not in SUPPORTED_ATTACHMENT_TYPES:
                    logger.info("attachment_skipped", content_type=content_type, uid=uid)
                    continue

                filename = part.get_filename()
                if filename:
                    filename = self._decode_header(filename)
                else:
                    filename = f"email_attachment_{uid}.pdf"

                payload = part.get_payload(decode=True)
                if not payload:
                    continue

                self._ingest_attachment(filename, payload)
                attachments_processed += 1

            if attachments_processed > 0:
                client.set_flags([uid], [b"\\Seen"])
                logger.info(
                    "email_processed",
                    uid=uid,
                    attachments=attachments_processed,
                    subject=subject,
                )

        except Exception as exc:
            logger.error("email_message_processing_failed", uid=uid, error=str(exc))

    def _decode_header(self, header_value: str) -> str:
        decoded_parts = decode_header(header_value)
        result_parts = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result_parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                result_parts.append(part)
        return " ".join(result_parts)

    def _extract_body_context(self, msg: email.message.Message) -> str:
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")[:1000]
        return ""

    def _ingest_attachment(self, filename: str, contents: bytes):
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{self._api_url}/ingest/upload",
                files={"file": (filename, contents)},
                data={"member_id": self._member_id},
                headers={"x-api-key": self._api_key},
            )

            if response.status_code == 200:
                logger.info(
                    "email_attachment_ingested",
                    filename=filename,
                    doc_type=response.json().get("doc_type"),
                )
            elif response.status_code == 409:
                logger.info("email_attachment_duplicate", filename=filename)
            else:
                logger.error(
                    "email_attachment_ingest_failed",
                    filename=filename,
                    status=response.status_code,
                )


def start_email_parser():
    agent = EmailParserAgent(
        imap_host=os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com"),
        imap_port=int(os.getenv("EMAIL_IMAP_PORT", "993")),
        email_address=os.getenv("EMAIL_ADDRESS", ""),
        email_password=os.getenv("EMAIL_PASSWORD", ""),
        api_url=os.getenv("INGESTION_API_URL", "http://localhost:8001"),
        api_key=os.getenv("INGESTION_API_KEY", "local-dev-key-change-in-prod"),
        member_id=os.getenv("EMAIL_MEMBER_ID"),
    )

    poll_interval = int(os.getenv("EMAIL_POLL_INTERVAL_SECONDS", "60"))

    logger.info("email_parser_started", host=os.getenv("EMAIL_IMAP_HOST"))

    while True:
        agent.poll()
        time.sleep(poll_interval)


if __name__ == "__main__":
    start_email_parser()
