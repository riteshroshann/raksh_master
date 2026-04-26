import os
import time

import httpx
import structlog

logger = structlog.get_logger()


class FaxReceiver:
    def __init__(self):
        self._account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self._auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self._fax_number = os.getenv("TWILIO_FAX_NUMBER", "")
        self._api_url = os.getenv("INGESTION_API_URL", "http://localhost:8001")
        self._api_key = os.getenv("INGESTION_API_KEY", "local-dev-key-change-in-prod")
        self._member_id = os.getenv("FAX_MEMBER_ID", "00000000-0000-0000-0000-000000000001")
        self._processed_sids: set[str] = set()

    def poll(self):
        if not self._account_sid or not self._auth_token:
            logger.warning("twilio_not_configured")
            return

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"https://fax.twilio.com/v1/Faxes",
                    auth=(self._account_sid, self._auth_token),
                    params={"To": self._fax_number, "Status": "received", "PageSize": 20},
                )

                if response.status_code != 200:
                    logger.error("twilio_fax_poll_failed", status=response.status_code)
                    return

                data = response.json()
                faxes = data.get("faxes", [])

                for fax in faxes:
                    sid = fax.get("sid", "")
                    if sid in self._processed_sids:
                        continue

                    media_url = fax.get("media_url")
                    if not media_url:
                        continue

                    self._download_and_ingest(sid, media_url, fax)
                    self._processed_sids.add(sid)

        except Exception as exc:
            logger.error("fax_poll_error", error=str(exc))

    def _download_and_ingest(self, sid: str, media_url: str, fax_metadata: dict):
        with httpx.Client(timeout=120.0) as client:
            media_response = client.get(media_url, auth=(self._account_sid, self._auth_token))

            if media_response.status_code != 200:
                logger.error("fax_media_download_failed", sid=sid, status=media_response.status_code)
                return

            fax_data = media_response.content
            filename = f"fax_{sid}.pdf"

            ingest_response = client.post(
                f"{self._api_url}/ingest/upload",
                files={"file": (filename, fax_data, "application/pdf")},
                data={"member_id": self._member_id},
                headers={"x-api-key": self._api_key},
            )

            if ingest_response.status_code == 200:
                logger.info("fax_ingested", sid=sid, from_number=fax_metadata.get("from"), pages=fax_metadata.get("num_pages"))
            elif ingest_response.status_code == 409:
                logger.info("fax_duplicate", sid=sid)
            else:
                logger.error("fax_ingest_failed", sid=sid, status=ingest_response.status_code)

    def handle_webhook(self, fax_sid: str, media_url: str, from_number: str, num_pages: int) -> dict:
        if fax_sid in self._processed_sids:
            return {"status": "duplicate", "sid": fax_sid}

        self._download_and_ingest(fax_sid, media_url, {"from": from_number, "num_pages": num_pages})
        self._processed_sids.add(fax_sid)

        return {"status": "processed", "sid": fax_sid}


class ScannerAgent:
    def __init__(self):
        self._api_url = os.getenv("INGESTION_API_URL", "http://localhost:8001")
        self._api_key = os.getenv("INGESTION_API_KEY", "local-dev-key-change-in-prod")
        self._member_id = os.getenv("SCANNER_MEMBER_ID", "00000000-0000-0000-0000-000000000001")
        self._scanner_port = os.getenv("SCANNER_PORT", "/dev/scanner0")
        self._scan_resolution = int(os.getenv("SCANNER_DPI", "300"))

    def scan_and_ingest(self, filename: str, scan_data: bytes) -> dict:
        if len(scan_data) == 0:
            logger.warning("empty_scan_data", filename=filename)
            return {"status": "error", "detail": "Empty scan data"}

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{self._api_url}/ingest/upload",
                files={"file": (filename, scan_data, "image/tiff")},
                data={"member_id": self._member_id},
                headers={"x-api-key": self._api_key},
            )

            if response.status_code == 200:
                result = response.json()
                logger.info("scan_ingested", filename=filename, doc_type=result.get("doc_type"))
                return {"status": "ingested", "doc_type": result.get("doc_type"), "ingest_id": result.get("ingest_id")}
            elif response.status_code == 409:
                logger.info("scan_duplicate", filename=filename)
                return {"status": "duplicate"}
            else:
                logger.error("scan_ingest_failed", filename=filename, status=response.status_code)
                return {"status": "error", "detail": response.text}

    def batch_scan(self, scans: list[tuple[str, bytes]]) -> list[dict]:
        results = []
        for filename, scan_data in scans:
            result = self.scan_and_ingest(filename, scan_data)
            results.append({"filename": filename, **result})
        return results


class EMRAgent:
    def __init__(self):
        self._api_url = os.getenv("INGESTION_API_URL", "http://localhost:8001")
        self._api_key = os.getenv("INGESTION_API_KEY", "local-dev-key-change-in-prod")
        self._emr_base_url = os.getenv("EMR_BASE_URL", "")
        self._emr_api_key = os.getenv("EMR_API_KEY", "")
        self._emr_system = os.getenv("EMR_SYSTEM", "generic")

    async def fetch_patient_documents(self, patient_id: str) -> list[dict]:
        if not self._emr_base_url:
            logger.warning("emr_not_configured")
            return []

        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {"Authorization": f"Bearer {self._emr_api_key}", "Content-Type": "application/json"}

            response = await client.get(
                f"{self._emr_base_url}/api/patients/{patient_id}/documents",
                headers=headers,
            )

            if response.status_code != 200:
                logger.error("emr_fetch_failed", patient_id=patient_id, status=response.status_code)
                return []

            return response.json().get("documents", [])

    async def fetch_and_ingest_document(self, patient_id: str, document_id: str, member_id: str) -> dict:
        if not self._emr_base_url:
            return {"status": "not_configured"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            headers = {"Authorization": f"Bearer {self._emr_api_key}"}

            doc_response = await client.get(
                f"{self._emr_base_url}/api/patients/{patient_id}/documents/{document_id}/content",
                headers=headers,
            )

            if doc_response.status_code != 200:
                logger.error("emr_document_fetch_failed", document_id=document_id, status=doc_response.status_code)
                return {"status": "fetch_failed"}

            content_type = doc_response.headers.get("content-type", "application/pdf")
            filename = f"emr_{self._emr_system}_{document_id}.pdf"
            file_data = doc_response.content

            ingest_response = await client.post(
                f"{self._api_url}/ingest/upload",
                files={"file": (filename, file_data, content_type)},
                data={"member_id": member_id},
                headers={"x-api-key": self._api_key},
            )

            if ingest_response.status_code == 200:
                result = ingest_response.json()
                logger.info("emr_document_ingested", document_id=document_id, doc_type=result.get("doc_type"))
                return {"status": "ingested", **result}
            elif ingest_response.status_code == 409:
                return {"status": "duplicate"}
            else:
                return {"status": "ingest_failed", "detail": ingest_response.text}

    async def sync_patient(self, patient_id: str, member_id: str) -> dict:
        documents = await self.fetch_patient_documents(patient_id)

        results = []
        for doc in documents:
            doc_id = doc.get("id", doc.get("document_id", ""))
            if doc_id:
                result = await self.fetch_and_ingest_document(patient_id, doc_id, member_id)
                results.append({"document_id": doc_id, **result})

        ingested = sum(1 for r in results if r.get("status") == "ingested")
        duplicates = sum(1 for r in results if r.get("status") == "duplicate")
        failed = sum(1 for r in results if r.get("status") not in ("ingested", "duplicate"))

        logger.info(
            "emr_patient_sync_completed",
            patient_id=patient_id,
            total=len(results),
            ingested=ingested,
            duplicates=duplicates,
            failed=failed,
        )

        return {"patient_id": patient_id, "total": len(results), "ingested": ingested, "duplicates": duplicates, "failed": failed, "results": results}


class HL7Listener:
    def __init__(self):
        self._api_url = os.getenv("INGESTION_API_URL", "http://localhost:8001")
        self._api_key = os.getenv("INGESTION_API_KEY", "local-dev-key-change-in-prod")
        self._member_id = os.getenv("HL7_DEFAULT_MEMBER_ID", "00000000-0000-0000-0000-000000000001")
        self._listen_port = int(os.getenv("HL7_LISTEN_PORT", "2575"))

    def process_message(self, raw_message: str) -> dict:
        from services.fhir_mapper import hl7v2_parser

        segments = raw_message.strip().split("\r")
        if not segments:
            return {"status": "empty_message"}

        msh = segments[0]
        fields = msh.split("|")
        message_type = fields[8] if len(fields) > 8 else ""

        if "ORU" in message_type:
            parsed = hl7v2_parser.parse_oru(raw_message)
            extractions = hl7v2_parser.oru_to_extractions(parsed)

            logger.info(
                "hl7_oru_processed",
                patient_id=parsed.get("patient", {}).get("id"),
                observation_count=len(extractions),
                sending_facility=parsed.get("sending_facility"),
            )

            return {
                "status": "processed",
                "message_type": "ORU",
                "patient": parsed.get("patient"),
                "extractions": extractions,
                "observation_count": len(extractions),
            }

        elif "ADT" in message_type:
            parsed = hl7v2_parser.parse_adt(raw_message)

            logger.info(
                "hl7_adt_processed",
                patient_id=parsed.get("patient", {}).get("id"),
            )

            return {"status": "processed", "message_type": "ADT", "patient": parsed.get("patient"), "visit": parsed.get("visit")}

        else:
            logger.warning("hl7_unsupported_message_type", message_type=message_type)
            return {"status": "unsupported", "message_type": message_type}

    def build_ack(self, raw_message: str, ack_code: str = "AA") -> str:
        segments = raw_message.strip().split("\r")
        msh = segments[0] if segments else ""
        fields = msh.split("|")

        sending_app = fields[2] if len(fields) > 2 else ""
        sending_facility = fields[3] if len(fields) > 3 else ""
        receiving_app = fields[4] if len(fields) > 4 else ""
        receiving_facility = fields[5] if len(fields) > 5 else ""
        message_control_id = fields[9] if len(fields) > 9 else ""

        ack_msh = f"MSH|^~\\&|{receiving_app}|{receiving_facility}|{sending_app}|{sending_facility}|||ACK|{message_control_id}|P|2.5"
        msa = f"MSA|{ack_code}|{message_control_id}"

        return f"{ack_msh}\r{msa}"


def start_fax_receiver():
    receiver = FaxReceiver()
    poll_interval = int(os.getenv("FAX_POLL_INTERVAL_SECONDS", "300"))

    logger.info("fax_receiver_started")

    while True:
        receiver.poll()
        time.sleep(poll_interval)


fax_receiver = FaxReceiver()
scanner_agent = ScannerAgent()
emr_agent = EMRAgent()
hl7_listener = HL7Listener()


if __name__ == "__main__":
    start_fax_receiver()
