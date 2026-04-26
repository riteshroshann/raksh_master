from datetime import date
from typing import Optional

import httpx
import structlog

from config import settings

logger = structlog.get_logger()


class ReferenceRangeService:
    def __init__(self):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "application/json",
        }
        self._cache: dict[str, list[dict]] = {}

    async def lookup(
        self,
        parameter_name: str,
        sex: str,
        age: Optional[int] = None,
        population: str = "indian",
    ) -> Optional[dict]:
        cache_key = f"{parameter_name}:{sex}:{age}:{population}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if cached:
                return cached[0]
            return None

        ranges = await self._fetch_ranges(parameter_name, sex, population)

        if age is not None:
            ranges = [
                r for r in ranges
                if (r.get("age_min") is None or r["age_min"] <= age)
                and (r.get("age_max") is None or r["age_max"] >= age)
            ]

        if not ranges and sex != "any":
            ranges = await self._fetch_ranges(parameter_name, "any", population)
            if age is not None:
                ranges = [
                    r for r in ranges
                    if (r.get("age_min") is None or r["age_min"] <= age)
                    and (r.get("age_max") is None or r["age_max"] >= age)
                ]

        if not ranges and population != "western":
            western_ranges = await self._fetch_ranges(parameter_name, sex, "western")
            if age is not None:
                western_ranges = [
                    r for r in western_ranges
                    if (r.get("age_min") is None or r["age_min"] <= age)
                    and (r.get("age_max") is None or r["age_max"] >= age)
                ]
            if western_ranges:
                logger.warning(
                    "using_western_range",
                    parameter=parameter_name,
                    sex=sex,
                    age=age,
                    detail="No Indian range available; western range used as fallback",
                )
                ranges = western_ranges

        self._cache[cache_key] = ranges

        if ranges:
            return ranges[0]
        return None

    async def _fetch_ranges(
        self, parameter_name: str, sex: str, population: str
    ) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "parameter_name": f"eq.{parameter_name.lower()}",
                "sex": f"eq.{sex}",
                "population": f"eq.{population}",
                "order": "version.desc",
            }

            response = await client.get(
                f"{self._base_url}/reference_ranges",
                headers=self._headers,
                params=params,
            )

            if response.status_code == 200:
                return response.json()

            logger.error(
                "reference_range_fetch_failed",
                status=response.status_code,
                parameter=parameter_name,
            )
            return []

    async def flag_parameter(
        self,
        parameter_name: str,
        value: float,
        sex: str,
        age: Optional[int] = None,
        population: str = "indian",
    ) -> str:
        ref_range = await self.lookup(parameter_name, sex, age, population)

        if not ref_range:
            return "unconfirmed"

        range_low = ref_range.get("range_low")
        range_high = ref_range.get("range_high")

        if range_low is not None and value < float(range_low):
            return "below_range"
        if range_high is not None and value > float(range_high):
            return "above_range"

        return "normal"

    async def get_indian_range(
        self,
        parameter_name: str,
        sex: str,
        age: Optional[int] = None,
    ) -> Optional[dict]:
        return await self.lookup(parameter_name, sex, age, "indian")

    async def get_all_for_parameter(self, parameter_name: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/reference_ranges",
                headers=self._headers,
                params={
                    "parameter_name": f"eq.{parameter_name.lower()}",
                    "order": "sex,age_min",
                },
            )

            if response.status_code == 200:
                return response.json()
            return []

    def clear_cache(self):
        self._cache.clear()


class ReferenceRangeEnrichmentService:
    def __init__(self):
        self._range_service = ReferenceRangeService()

    async def enrich_parameters(
        self,
        parameters: list[dict],
        sex: str,
        dob: Optional[date] = None,
    ) -> list[dict]:
        age = None
        if dob:
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

        enriched = []
        for param in parameters:
            param_name = param.get("parameter_name", param.get("name", "")).lower()
            value_numeric = param.get("value_numeric")

            indian_range = await self._range_service.get_indian_range(param_name, sex, age)

            if indian_range:
                param["indian_range_low"] = indian_range.get("range_low")
                param["indian_range_high"] = indian_range.get("range_high")

                if value_numeric is not None:
                    param["flag"] = await self._range_service.flag_parameter(
                        param_name, float(value_numeric), sex, age
                    )

            enriched.append(param)

        return enriched
