"""Provider error classification and secret redaction."""

from __future__ import annotations

import re
from typing import Any

from porous_designer.agentic.contracts import ProviderError, ProviderErrorCategory


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*['\"]?[^'\"\s]+"),
]


def redact_secrets(value: Any) -> str:
    text = str(value)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def classify_provider_exception(provider: str, model: str, exc: Exception) -> ProviderError:
    raw = redact_secrets(exc)
    lowered = raw.lower()
    category = ProviderErrorCategory.PROVIDER_INTERNAL_ERROR
    retryable = False
    if isinstance(exc, TimeoutError) or "timeout" in lowered:
        category = ProviderErrorCategory.PROVIDER_TIMEOUT
        retryable = True
    elif "auth" in lowered or "api key" in lowered or "unauthorized" in lowered:
        category = ProviderErrorCategory.PROVIDER_AUTHENTICATION_FAILED
    elif "rate" in lowered and "limit" in lowered:
        category = ProviderErrorCategory.PROVIDER_RATE_LIMITED
        retryable = True
    elif "quota" in lowered:
        category = ProviderErrorCategory.PROVIDER_QUOTA_EXCEEDED
    elif "model" in lowered and ("unavailable" in lowered or "not found" in lowered):
        category = ProviderErrorCategory.PROVIDER_MODEL_UNAVAILABLE
    elif "network" in lowered or "connection" in lowered:
        category = ProviderErrorCategory.PROVIDER_NETWORK_ERROR
        retryable = True
    elif "schema" in lowered or "validation" in lowered:
        category = ProviderErrorCategory.PROVIDER_SCHEMA_INVALID
    elif "refusal" in lowered:
        category = ProviderErrorCategory.PROVIDER_REFUSAL
    return ProviderError(
        provider=provider,
        model=model,
        category=category,
        safe_user_message=category.value.replace("_", " ").title(),
        retryable=retryable,
        technical_details=raw,
        redacted_raw_details=raw,
    )
