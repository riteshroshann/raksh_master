"""
Output-layer constitutional filter.

Scans all outgoing API responses for prohibited diagnostic terms before
they reach the client. This is the architectural safeguard — the system
must be incapable of producing diagnostic strings in patient-facing context.

This middleware runs AFTER route handlers, BEFORE response serialisation.
"""

import json
import re
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()

PROHIBITED_TERMS = [
    "diabetic",
    "prediabetic",
    "hypothyroid",
    "hyperthyroid",
    "anaemic",
    "anemic",
    "nephrotic",
    "nephropathy",
    "cirrhotic",
    "hepatitis",
    "cardiomyopathy",
    "heart failure",
    "myocardial infarction",
    "bone marrow suppression",
    "you may have",
    "you might have",
    "you could have",
    "this suggests",
    "this indicates",
    "this means you",
    "diagnosis",
    "diagnosed with",
    "consistent with",
    "suggestive of",
    "likely indicates",
    "possibly indicates",
    "probable cause",
    "consult a doctor",
    "consult your doctor",
    "consult a physician",
    "see your doctor",
    "seek medical attention",
    "levothyroxine dose",
    "statin efficacy",
    "glycemic control worsening",
    "dose may need adjustment",
    "investigate active blood loss",
]

_PATTERN = re.compile(
    "|".join(re.escape(term) for term in PROHIBITED_TERMS),
    re.IGNORECASE,
)


def _scan_value(value: Any, path: str = "") -> list[dict]:
    """Recursively scan a value for prohibited terms. Returns violations found."""
    violations = []

    if isinstance(value, str):
        matches = _PATTERN.findall(value)
        if matches:
            for match in matches:
                violations.append({"path": path, "term": match.lower(), "value_snippet": value[:200]})

    elif isinstance(value, dict):
        for key, val in value.items():
            violations.extend(_scan_value(val, f"{path}.{key}" if path else key))

    elif isinstance(value, list):
        for i, item in enumerate(value):
            violations.extend(_scan_value(item, f"{path}[{i}]"))

    return violations


def _redact_value(value: Any) -> Any:
    """Recursively redact prohibited terms from a value."""
    if isinstance(value, str):
        return _PATTERN.sub("[REDACTED]", value)

    elif isinstance(value, dict):
        return {key: _redact_value(val) for key, val in value.items()}

    elif isinstance(value, list):
        return [_redact_value(item) for item in value]

    return value


class ConstitutionalFilterMiddleware(BaseHTTPMiddleware):
    """
    Scans all JSON responses for prohibited diagnostic terms.
    Redacts any found and logs a constitutional_violation event.
    """

    EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if request.url.path in self.EXEMPT_PATHS:
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        body_bytes = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body_bytes += chunk.encode("utf-8")
            else:
                body_bytes += chunk

        try:
            body = json.loads(body_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        violations = _scan_value(body)

        if violations:
            logger.error(
                "constitutional_violation",
                path=str(request.url.path),
                method=request.method,
                violations=[
                    {"term": v["term"], "field": v["path"]}
                    for v in violations
                ],
                total_violations=len(violations),
            )

            redacted_body = _redact_value(body)
            redacted_bytes = json.dumps(redacted_body).encode("utf-8")

            return Response(
                content=redacted_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="application/json",
            )

        return Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
