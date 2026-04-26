from datetime import datetime
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger()


UHI_GATEWAY_SANDBOX = "https://uhigateway.abdm.gov.in/api/v1"


class UHIServiceType:
    TELECONSULTATION = "teleconsultation"
    PHYSICAL_CONSULTATION = "physical_consultation"
    LAB_BOOKING = "lab_booking"
    AMBULANCE = "ambulance"
    BLOOD_BANK = "blood_bank"


class UHIMessageIntent:
    SEARCH = "search"
    SELECT = "select"
    INIT = "init"
    CONFIRM = "confirm"
    STATUS = "status"
    CANCEL = "cancel"


class UHIClient:
    def __init__(self, gateway_url: str = UHI_GATEWAY_SANDBOX, subscriber_id: str = "", subscriber_url: str = ""):
        self._gateway = gateway_url
        self._subscriber_id = subscriber_id
        self._subscriber_url = subscriber_url
        self._domain = "nic2004:85111"

    def _build_context(self, action: str, transaction_id: str) -> dict:
        return {
            "domain": self._domain,
            "country": "IND",
            "city": "std:080",
            "action": action,
            "core_version": "0.7.1",
            "consumer_id": self._subscriber_id,
            "consumer_uri": self._subscriber_url,
            "transaction_id": transaction_id,
            "message_id": str(__import__("uuid").uuid4()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    async def search_providers(
        self,
        specialty: str,
        city: str = "std:080",
        fulfillment_type: str = UHIServiceType.TELECONSULTATION,
        transaction_id: Optional[str] = None,
    ) -> dict:
        txn_id = transaction_id or str(__import__("uuid").uuid4())

        payload = {
            "context": self._build_context("search", txn_id),
            "message": {
                "intent": {
                    "fulfillment": {
                        "type": fulfillment_type,
                        "agent": {
                            "tags": {
                                "@abdm/gov/in/specialty": specialty,
                            }
                        },
                    },
                    "provider": {
                        "locations": [{"city": {"code": city}}],
                    },
                },
            },
        }

        return await self._post("/search", payload)

    async def select_provider(self, provider_id: str, item_id: str, transaction_id: str) -> dict:
        payload = {
            "context": self._build_context("select", transaction_id),
            "message": {
                "order": {
                    "provider": {"id": provider_id},
                    "items": [{"id": item_id}],
                },
            },
        }

        return await self._post("/select", payload)

    async def init_booking(
        self,
        provider_id: str,
        item_id: str,
        patient_name: str,
        patient_gender: str,
        patient_abha: str,
        transaction_id: str,
    ) -> dict:
        payload = {
            "context": self._build_context("init", transaction_id),
            "message": {
                "order": {
                    "provider": {"id": provider_id},
                    "items": [{"id": item_id}],
                    "fulfillment": {
                        "customer": {
                            "person": {
                                "name": patient_name,
                                "gender": patient_gender,
                                "creds": [
                                    {"type": "ABHA", "id": patient_abha},
                                ],
                            },
                        },
                    },
                    "billing": {
                        "name": patient_name,
                    },
                },
            },
        }

        return await self._post("/init", payload)

    async def confirm_booking(self, order_id: str, payment_id: str, transaction_id: str) -> dict:
        payload = {
            "context": self._build_context("confirm", transaction_id),
            "message": {
                "order": {
                    "id": order_id,
                    "payment": {
                        "params": {"transaction_id": payment_id},
                        "status": "PAID",
                    },
                },
            },
        }

        return await self._post("/confirm", payload)

    async def check_status(self, order_id: str, transaction_id: str) -> dict:
        payload = {
            "context": self._build_context("status", transaction_id),
            "message": {
                "order": {"id": order_id},
            },
        }

        return await self._post("/status", payload)

    async def cancel_booking(self, order_id: str, reason: str, transaction_id: str) -> dict:
        payload = {
            "context": self._build_context("cancel", transaction_id),
            "message": {
                "order": {
                    "id": order_id,
                    "tags": {"@abdm/gov/in/cancelReason": reason},
                },
            },
        }

        return await self._post("/cancel", payload)

    async def _post(self, path: str, payload: dict) -> dict:
        url = f"{self._gateway}{path}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)

                result = {
                    "status_code": response.status_code,
                    "transaction_id": payload.get("context", {}).get("transaction_id"),
                    "action": payload.get("context", {}).get("action"),
                }

                if response.status_code in (200, 202):
                    result["success"] = True
                    try:
                        result["data"] = response.json()
                    except Exception:
                        result["data"] = response.text
                else:
                    result["success"] = False
                    result["error"] = response.text

                logger.info(
                    "uhi_api_call",
                    action=result["action"],
                    status=response.status_code,
                    success=result["success"],
                )

                return result

        except Exception as exc:
            logger.error("uhi_api_error", path=path, error=str(exc))
            return {"success": False, "error": str(exc), "status_code": 0}


class ClinicalSummarizationAgent:
    def __init__(self):
        self._anthropic_key = getattr(settings, "anthropic_api_key", "")
        self._model = "claude-sonnet-4-20250514"

    async def generate_pre_visit_summary(self, patient_record: dict) -> dict:
        member = patient_record.get("member", {})
        documents = patient_record.get("recent_documents", [])
        parameters = patient_record.get("latest_parameters", [])
        medications = patient_record.get("active_medications", [])
        conditions = member.get("chronic_conditions", [])

        prompt = self._build_summary_prompt(member, documents, parameters, medications, conditions)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self._anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "max_tokens": 2000,
                        "system": self._system_prompt(),
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    summary_text = result["content"][0]["text"]

                    return {
                        "summary": summary_text,
                        "generated_at": datetime.utcnow().isoformat(),
                        "model": self._model,
                        "member_name": member.get("name"),
                        "parameters_reviewed": len(parameters),
                        "documents_reviewed": len(documents),
                    }

                logger.error("summarization_failed", status=response.status_code)
                return {"summary": None, "error": response.text}

        except Exception as exc:
            logger.error("summarization_error", error=str(exc))
            return {"summary": None, "error": str(exc)}

    def generate_offline_summary(self, patient_record: dict) -> dict:
        member = patient_record.get("member", {})
        parameters = patient_record.get("latest_parameters", [])
        medications = patient_record.get("active_medications", [])
        conditions = member.get("chronic_conditions", [])

        sections = []

        sections.append(f"Patient: {member.get('name', 'Unknown')}")
        sections.append(f"Age: {member.get('age', 'N/A')} | Sex: {member.get('sex', 'N/A')} | Blood Group: {member.get('blood_group', 'N/A')}")

        if conditions:
            sections.append(f"Chronic Conditions: {', '.join(conditions)}")

        if parameters:
            abnormal = [p for p in parameters if p.get("flag") in ("above_range", "below_range", "critical_high", "critical_low")]
            if abnormal:
                sections.append("Abnormal Parameters:")
                for p in abnormal:
                    sections.append(f"  - {p['parameter_name']}: {p.get('value_numeric', 'N/A')} {p.get('unit', '')} [{p.get('flag', '')}]")

            normal_count = len(parameters) - len(abnormal)
            sections.append(f"Normal Parameters: {normal_count} within reference range")

        if medications:
            sections.append("Active Medications:")
            for med in medications:
                sections.append(f"  - {med.get('name', 'Unknown')} {med.get('dosage', '')} {med.get('frequency', '')}")

        return {
            "summary": "\n".join(sections),
            "generated_at": datetime.utcnow().isoformat(),
            "model": "offline-template",
            "member_name": member.get("name"),
        }

    def _system_prompt(self) -> str:
        return (
            "You are a clinical summarization assistant. Generate concise, structured pre-visit summaries for physicians. "
            "NEVER make diagnostic conclusions or treatment recommendations. "
            "ONLY present factual data from the patient's record. "
            "Flag abnormal values and trends. "
            "Use structured headings: Demographics, Active Conditions, Recent Lab Results (Abnormal), Medications, Recent Documents. "
            "Keep the summary under 500 words."
        )

    def _build_summary_prompt(self, member: dict, documents: list, parameters: list, medications: list, conditions: list) -> str:
        parts = [
            f"Generate a pre-visit clinical summary for the following patient record.",
            f"Patient: {member.get('name', 'Unknown')}, Age: {member.get('age', 'N/A')}, Sex: {member.get('sex', 'N/A')}",
            f"Blood Group: {member.get('blood_group', 'N/A')}",
        ]

        if conditions:
            parts.append(f"Known Conditions: {', '.join(conditions)}")

        if parameters:
            parts.append("Latest Lab Parameters:")
            for p in parameters[:30]:
                parts.append(f"  {p.get('parameter_name')}: {p.get('value_numeric', 'N/A')} {p.get('unit', '')} "
                           f"(Range: {p.get('indian_range_low', '?')}-{p.get('indian_range_high', '?')}) "
                           f"Flag: {p.get('flag', 'unconfirmed')} "
                           f"Date: {p.get('test_date', 'N/A')}")

        if medications:
            parts.append("Current Medications:")
            for med in medications[:15]:
                parts.append(f"  {med.get('name', 'Unknown')} {med.get('dosage', '')} {med.get('frequency', '')}")

        if documents:
            parts.append(f"Recent Documents ({len(documents)}):")
            for doc in documents[:10]:
                parts.append(f"  {doc.get('doc_type', 'unknown')} from {doc.get('lab_name', 'unknown')} on {doc.get('doc_date', 'N/A')}")

        return "\n".join(parts)


uhi_client = UHIClient()
summarization_agent = ClinicalSummarizationAgent()
