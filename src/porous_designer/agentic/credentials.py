"""Secure API-key lookup for optional providers."""

from __future__ import annotations

import os
from dataclasses import dataclass

from porous_designer.agentic.provider_errors import redact_secrets


SERVICE_NAMES = {
    "openai": "PGG OpenAI API Key",
    "gemini": "PGG Gemini API Key",
}


@dataclass
class CredentialLookupResult:
    available: bool
    source: str = "unavailable"
    redacted_display: str = ""
    key: str | None = None


def lookup_api_key(provider: str) -> CredentialLookupResult:
    env_name = "OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"
    value = os.environ.get(env_name)
    if value:
        return CredentialLookupResult(True, "environment", redact_for_display(value), value)
    try:
        import keyring

        stored = keyring.get_password(SERVICE_NAMES[provider], "default")
        if stored:
            return CredentialLookupResult(True, "keyring", redact_for_display(stored), stored)
    except Exception:
        pass
    return CredentialLookupResult(False)


def store_api_key(provider: str, key: str) -> None:
    import keyring

    keyring.set_password(SERVICE_NAMES[provider], "default", key)


def delete_api_key(provider: str) -> None:
    try:
        import keyring

        keyring.delete_password(SERVICE_NAMES[provider], "default")
    except Exception:
        pass


def redact_for_display(key: str) -> str:
    if len(key) <= 8:
        return "[REDACTED]"
    return f"{key[:4]}...{key[-4:]}"


def safe_exception_text(exc: Exception) -> str:
    return redact_secrets(exc)
