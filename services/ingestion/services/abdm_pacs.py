from datetime import datetime
from typing import Optional

import httpx
import structlog

from config import settings

logger = structlog.get_logger()


class ABDMClient:
    def __init__(self):
        self._wrapper_url = settings.abdm_wrapper_url
        self._client_id = settings.abdm_client_id
        self._client_secret = settings.abdm_client_secret
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    async def _ensure_token(self) -> str:
        if self._access_token and self._token_expires_at and datetime.utcnow() < self._token_expires_at:
            return self._access_token

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._wrapper_url}/v1/auth/token",
                json={"clientId": self._client_id, "clientSecret": self._client_secret},
            )

            if response.status_code != 200:
                logger.error("abdm_auth_failed", status=response.status_code)
                raise RuntimeError(f"ABDM authentication failed: {response.status_code}")

            data = response.json()
            self._access_token = data.get("accessToken", "")
            return self._access_token

    async def create_abha_id(self, aadhaar_number: str, name: str, dob: str, gender: str) -> dict:
        token = await self._ensure_token()

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._wrapper_url}/v1/registration/aadhaar/createHealthIdWithPreVerified",
                headers={"Authorization": f"Bearer {token}"},
                json={"aadhaar": aadhaar_number, "name": name, "dateOfBirth": dob, "gender": gender},
            )

            if response.status_code not in (200, 201):
                logger.error("abha_creation_failed", status=response.status_code)
                raise RuntimeError(f"ABHA creation failed: {response.status_code}")

            result = response.json()
            logger.info("abha_id_created", health_id=result.get("healthId"))
            return result

    async def verify_abha_id(self, abha_id: str) -> dict:
        token = await self._ensure_token()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._wrapper_url}/v1/account/profile",
                headers={"Authorization": f"Bearer {token}", "X-Health-Id": abha_id},
            )

            if response.status_code != 200:
                logger.error("abha_verification_failed", status=response.status_code, abha_id=abha_id)
                return {"verified": False, "abha_id": abha_id}

            return {"verified": True, "abha_id": abha_id, "profile": response.json()}

    async def search_hpr(self, doctor_name: str) -> list[dict]:
        token = await self._ensure_token()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._wrapper_url}/v1/hpr/search",
                headers={"Authorization": f"Bearer {token}"},
                params={"name": doctor_name},
            )

            if response.status_code == 200:
                return response.json().get("results", [])
            return []

    async def create_consent_request(
        self,
        patient_abha_id: str,
        purpose: str,
        requester_name: str,
        date_from: str,
        date_to: str,
        health_info_types: list[str],
    ) -> dict:
        token = await self._ensure_token()

        consent_request = {
            "purpose": {"text": purpose, "code": "CAREMGT"},
            "patient": {"id": patient_abha_id},
            "requester": {"name": requester_name, "identifier": {"type": "REGNO", "value": "", "system": ""}},
            "hiTypes": health_info_types,
            "permission": {
                "accessMode": "VIEW",
                "dateRange": {"from": date_from, "to": date_to},
                "dataEraseAt": "",
                "frequency": {"unit": "HOUR", "value": 1, "repeats": 0},
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._wrapper_url}/v1/consent-requests/init",
                headers={"Authorization": f"Bearer {token}"},
                json=consent_request,
            )

            if response.status_code not in (200, 201, 202):
                logger.error("abdm_consent_request_failed", status=response.status_code)
                raise RuntimeError(f"ABDM consent request failed: {response.status_code}")

            result = response.json()
            logger.info("abdm_consent_request_created", request_id=result.get("consentRequestId"))
            return result

    async def push_fhir_bundle(self, bundle: dict, consent_id: str) -> dict:
        token = await self._ensure_token()

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._wrapper_url}/v1/health-information/hip/on-request",
                headers={"Authorization": f"Bearer {token}"},
                json={"transactionId": consent_id, "entries": [{"content": bundle}]},
            )

            if response.status_code not in (200, 202):
                logger.error("abdm_push_failed", status=response.status_code)
                raise RuntimeError(f"ABDM bundle push failed: {response.status_code}")

            return response.json()

    async def fetch_patient_records(self, consent_id: str) -> list[dict]:
        token = await self._ensure_token()

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{self._wrapper_url}/v1/health-information/fetch",
                headers={"Authorization": f"Bearer {token}"},
                params={"consentId": consent_id},
            )

            if response.status_code == 200:
                return response.json().get("entries", [])
            return []


class PACSClient:
    def __init__(self):
        self._pacs_url = settings.pacs_server_url
        self._orthanc_url = settings.orthanc_url
        self._aet = settings.pacs_aet

    async def retrieve_study_wado_rs(self, study_instance_uid: str) -> Optional[bytes]:
        if not self._pacs_url:
            logger.warning("pacs_not_configured")
            return None

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(
                f"{self._pacs_url}/studies/{study_instance_uid}",
                headers={"Accept": "multipart/related; type=application/dicom"},
            )

            if response.status_code == 200:
                logger.info("wado_rs_retrieved", study_uid=study_instance_uid, size=len(response.content))
                return response.content

            logger.error("wado_rs_failed", status=response.status_code, study_uid=study_instance_uid)
            return None

    async def store_study_stow_rs(self, dicom_data: bytes) -> dict:
        if not self._pacs_url:
            logger.warning("pacs_not_configured")
            return {"status": "not_configured"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._pacs_url}/studies",
                headers={"Content-Type": "application/dicom"},
                content=dicom_data,
            )

            if response.status_code in (200, 201):
                logger.info("stow_rs_stored", size=len(dicom_data))
                return {"status": "stored"}

            logger.error("stow_rs_failed", status=response.status_code)
            return {"status": "failed", "code": response.status_code}

    async def cache_in_orthanc(self, dicom_data: bytes) -> Optional[str]:
        if not self._orthanc_url:
            return None

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._orthanc_url}/instances",
                content=dicom_data,
                headers={"Content-Type": "application/dicom"},
            )

            if response.status_code == 200:
                result = response.json()
                orthanc_id = result.get("ID", "")
                logger.info("orthanc_cached", orthanc_id=orthanc_id)
                return orthanc_id

            logger.error("orthanc_cache_failed", status=response.status_code)
            return None

    async def search_studies(self, patient_id: Optional[str] = None, modality: Optional[str] = None) -> list[dict]:
        if not self._pacs_url:
            return []

        params = {}
        if patient_id:
            params["PatientID"] = patient_id
        if modality:
            params["ModalitiesInStudy"] = modality

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._pacs_url}/studies",
                params=params,
                headers={"Accept": "application/dicom+json"},
            )

            if response.status_code == 200:
                return response.json()
            return []


abdm_client = ABDMClient()
pacs_client = PACSClient()
