"""Secure API-key lookup for optional providers."""

from __future__ import annotations

import os
from dataclasses import dataclass

from porous_designer.agentic.provider_config import CredentialMode
from porous_designer.agentic.provider_errors import redact_secrets


SERVICE_NAME = "PGG Agent Providers"
SESSION_KEYS: dict[str, str] = {}


class CredentialError(RuntimeError):
    category = "CREDENTIAL_BACKEND_UNAVAILABLE"


@dataclass
class CredentialLookupResult:
    available: bool
    source: str = "unavailable"
    redacted_display: str = ""
    key: str | None = None
    backend: str = ""
    message: str = ""


def lookup_api_key(provider: str, mode: CredentialMode = CredentialMode.KEYRING) -> CredentialLookupResult:
    env_name = "OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"
    if mode == CredentialMode.ENVIRONMENT:
        value = os.environ.get(env_name)
        return CredentialLookupResult(bool(value), "environment", redact_for_display(value) if value else "", value, message=f"Environment variable: {env_name}" if value else f"Environment variable not found: {env_name}")
    if mode == CredentialMode.SESSION:
        value = SESSION_KEYS.get(provider)
        return CredentialLookupResult(bool(value), "session", redact_for_display(value) if value else "", value, message="Session-only key active" if value else "Session-only key not set")
    try:
        import keyring

        backend = keyring.get_keyring()
        stored = keyring.get_password(SERVICE_NAME, provider)
        if stored:
            return CredentialLookupResult(True, "keyring", redact_for_display(stored), stored, backend=backend.__class__.__name__, message="Stored key: Available")
        return CredentialLookupResult(False, "keyring", backend=backend.__class__.__name__, message="Stored key: Not found")
    except Exception as exc:
        return CredentialLookupResult(False, "keyring", message=f"CREDENTIAL_BACKEND_UNAVAILABLE: {redact_secrets(exc)}")


def store_api_key(provider: str, key: str) -> None:
    import keyring

    keyring.set_password(SERVICE_NAME, provider, key)
    stored = keyring.get_password(SERVICE_NAME, provider)
    if stored != key:
        raise CredentialError("CREDENTIAL_READ_FAILED: stored credential could not be verified")


def store_session_key(provider: str, key: str) -> None:
    SESSION_KEYS[provider] = key


def clear_session_key(provider: str) -> None:
    SESSION_KEYS.pop(provider, None)


def delete_api_key(provider: str) -> None:
    try:
        import keyring

        keyring.delete_password(SERVICE_NAME, provider)
    except Exception as exc:
        text = redact_secrets(exc)
        if "not found" in text.lower() or "no password" in text.lower():
            SESSION_KEYS.pop(provider, None)
            raise CredentialError(f"CREDENTIAL_NOT_FOUND: {text}") from exc
        raise CredentialError(f"CREDENTIAL_DELETE_FAILED: {text}") from exc
    SESSION_KEYS.pop(provider, None)


def redact_for_display(key: str) -> str:
    if len(key) <= 8:
        return "[REDACTED]"
    return f"{key[:4]}...{key[-4:]}"


def safe_exception_text(exc: Exception) -> str:
    return redact_secrets(exc)
