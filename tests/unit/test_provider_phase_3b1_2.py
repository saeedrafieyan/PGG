from __future__ import annotations

import sys
import types

import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from porous_designer.agentic.contracts import ProviderMode
from porous_designer.agentic.cache import ProviderResultCache
from porous_designer.agentic.credentials import (
    CredentialMode,
    SESSION_KEYS,
    SERVICE_NAME,
    delete_api_key,
    lookup_api_key,
    store_api_key,
    store_session_key,
)
from porous_designer.agentic.provider import MockAgentProvider
from porous_designer.agentic.provider_config import ExternalCallMode, ProviderSettings, load_provider_settings, save_provider_settings
from porous_designer.agentic.request_parser_agent import RequestParserAgent


class FakeKeyringBackend:
    priority = 1


class FakeKeyringModule(types.SimpleNamespace):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__()
        self.fail = fail
        self.store = {}
        self.backend = FakeKeyringBackend()

    def get_keyring(self):
        if self.fail:
            raise RuntimeError("backend unavailable sk-secretSECRET")
        return self.backend

    def set_password(self, service, username, password):
        if self.fail:
            raise RuntimeError("save failed")
        self.store[(service, username)] = password

    def get_password(self, service, username):
        if self.fail:
            raise RuntimeError("read failed")
        return self.store.get((service, username))

    def delete_password(self, service, username):
        if self.fail:
            raise RuntimeError("delete failed")
        try:
            del self.store[(service, username)]
        except KeyError as exc:
            raise RuntimeError("password not found") from exc


@pytest.fixture()
def isolated_qsettings(tmp_path):
    app = QCoreApplication.instance()
    if app is not None:
        app.setOrganizationName("PGGTests")
        app.setApplicationName("Phase3B12")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    q = QSettings()
    q.clear()
    yield q
    q.clear()


def test_provider_settings_persist_without_secret(isolated_qsettings):
    secret = "sk-test-PERSISTENCE-SECRET"
    settings = ProviderSettings(
        external_access_enabled=True,
        provider_mode=ProviderMode.OPENROUTER,
        openrouter_model="qwen/qwen3.8-27b:free",
        openrouter_fallback_models=["a/b:free", "c/d:free"],
        timeout_s=22.0,
        max_retries=2,
        credential_mode=CredentialMode.KEYRING,
        external_call_mode=ExternalCallMode.WHEN_RECOMMENDED,
        configuration_version=7,
    )
    save_provider_settings(settings)
    loaded = load_provider_settings()
    assert loaded.external_access_enabled is True
    assert loaded.provider_mode == ProviderMode.OPENROUTER
    assert loaded.openrouter_model == "qwen/qwen3.8-27b:free"
    assert loaded.openrouter_fallback_models == ["a/b:free", "c/d:free"]
    assert loaded.temperature == 0.0
    assert loaded.timeout_s == 22.0
    assert loaded.max_retries == 2
    assert loaded.external_call_mode == ExternalCallMode.WHEN_RECOMMENDED
    assert loaded.credential_mode == CredentialMode.KEYRING
    values = "\n".join(str(isolated_qsettings.value(key)) for key in isolated_qsettings.allKeys())
    assert secret not in values
    assert "API_KEY" not in values


def test_fake_keyring_save_readback_delete(monkeypatch):
    fake = FakeKeyringModule()
    monkeypatch.setitem(sys.modules, "keyring", fake)
    store_api_key("openai", "sk-test-123456789")
    assert fake.store[(SERVICE_NAME, "openai")] == "sk-test-123456789"
    found = lookup_api_key("openai", CredentialMode.KEYRING)
    assert found.available
    assert found.backend == "FakeKeyringBackend"
    assert "123456789" not in found.redacted_display
    delete_api_key("openai")
    assert (SERVICE_NAME, "openai") not in fake.store


def test_keyring_unavailable_is_reported_without_secret(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", FakeKeyringModule(fail=True))
    found = lookup_api_key("openai", CredentialMode.KEYRING)
    assert not found.available
    assert "CREDENTIAL_BACKEND_UNAVAILABLE" in found.message
    assert "sk-secretSECRET" not in found.message


def test_environment_and_session_credential_modes(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-123456789")
    env = lookup_api_key("openai", CredentialMode.ENVIRONMENT)
    assert env.available
    assert env.source == "environment"
    store_session_key("gemini", "AIzaSESSION123456")
    session = lookup_api_key("gemini", CredentialMode.SESSION)
    assert session.available
    assert session.source == "session"
    SESSION_KEYS.clear()
    assert not lookup_api_key("gemini", CredentialMode.SESSION).available


def test_external_call_modes_control_provider_invocation():
    calls = {"count": 0}

    class CountingProvider(MockAgentProvider):
        def parse_request(self, request, deterministic_evidence, schema):
            calls["count"] += 1
            return {
                "schema_version": "1.0",
                "provider_mode": "openai",
                "parser_version": "3B.1",
                "extracted_fields": [],
                "ambiguities": [],
                "missing_requirements": [],
                "unsupported_requests": [],
                "assumptions": [],
                "evidence": [],
            }

    ambiguous = "Create a scaffold with hexagonal packing and pore size 1 mm."
    explicit = "Create a 4 x 4 x 4 mm HCP scaffold with 70% porosity."
    settings = ProviderSettings(external_access_enabled=True, provider_mode=ProviderMode.OPENROUTER, external_call_mode=ExternalCallMode.WHEN_RECOMMENDED)
    RequestParserAgent(CountingProvider(), settings=settings, cache=ProviderResultCache(enabled=False)).parse(ambiguous)
    assert calls["count"] == 1
    RequestParserAgent(CountingProvider(), settings=settings, cache=ProviderResultCache(enabled=False)).parse(explicit)
    assert calls["count"] == 1
    settings.external_call_mode = ExternalCallMode.ALWAYS
    RequestParserAgent(CountingProvider(), settings=settings, cache=ProviderResultCache(enabled=False)).parse(explicit)
    assert calls["count"] == 2
    settings.external_call_mode = ExternalCallMode.DETERMINISTIC_ONLY
    RequestParserAgent(CountingProvider(), settings=settings, cache=ProviderResultCache(enabled=False)).parse(ambiguous)
    assert calls["count"] == 2


def test_pre_openrouter_settings_fall_back_to_deterministic(isolated_qsettings):
    isolated_qsettings.setValue("agent_provider/settings_schema_version", 2)
    isolated_qsettings.setValue("agent_provider/provider_mode", "openai")
    isolated_qsettings.setValue("agent_provider/external_access_enabled", True)
    isolated_qsettings.sync()
    loaded = load_provider_settings()
    assert loaded.provider_mode == ProviderMode.DETERMINISTIC_ONLY
    assert loaded.external_access_enabled is False
