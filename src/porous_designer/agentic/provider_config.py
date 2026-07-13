"""Provider settings and model defaults for Phase 3B.1.1."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

from porous_designer.agentic.contracts import ProviderMode

OPENAI_LOW_COST_MODEL = "gpt-5.6-luna"
OPENAI_ESCALATION_MODEL = "gpt-5.6-terra"
GEMINI_LOW_COST_MODEL = "gemini-3.1-flash-lite"


class CredentialMode(str, Enum):
    ENVIRONMENT = "environment"
    KEYRING = "keyring"
    SESSION = "session"


class ExternalCallMode(str, Enum):
    DETERMINISTIC_ONLY = "deterministic_only"
    WHEN_RECOMMENDED = "external_when_recommended"
    ALWAYS = "always_external"


@dataclass
class ModelChoice:
    provider: ProviderMode
    model_id: str
    category: str
    description: str


@dataclass
class ProviderSettings:
    settings_schema_version: int = 2
    external_access_enabled: bool = False
    provider_mode: ProviderMode = ProviderMode.DETERMINISTIC_ONLY
    openai_model: str = OPENAI_LOW_COST_MODEL
    openai_escalation_model: str = OPENAI_ESCALATION_MODEL
    gemini_model: str = GEMINI_LOW_COST_MODEL
    custom_model_id: str = ""
    timeout_s: float = 10.0
    max_retries: int = 1
    reasoning_level: str = "low"
    confidence_threshold: float = 0.70
    require_escalation_confirmation: bool = True
    cache_enabled: bool = True
    credential_mode: CredentialMode = CredentialMode.KEYRING
    external_call_mode: ExternalCallMode = ExternalCallMode.DETERMINISTIC_ONLY
    configuration_version: int = 0

    def selected_model(self) -> str:
        if self.custom_model_id:
            return self.custom_model_id
        if self.provider_mode == ProviderMode.OPENAI:
            return self.openai_model
        if self.provider_mode == ProviderMode.GEMINI:
            return self.gemini_model
        return "deterministic"

    def selected_category(self) -> str:
        model = self.selected_model()
        if model in {OPENAI_LOW_COST_MODEL, GEMINI_LOW_COST_MODEL}:
            return "Low cost"
        if model == OPENAI_ESCALATION_MODEL:
            return "Balanced"
        if model == "deterministic":
            return "None"
        return "Custom"

    def bump_version(self) -> None:
        self.configuration_version += 1


MODEL_CHOICES = [
    ModelChoice(ProviderMode.OPENAI, OPENAI_LOW_COST_MODEL, "Low cost", "Recommended parsing default"),
    ModelChoice(ProviderMode.OPENAI, OPENAI_ESCALATION_MODEL, "Balanced", "Optional escalation"),
    ModelChoice(ProviderMode.GEMINI, GEMINI_LOW_COST_MODEL, "Low cost", "Recommended parsing default"),
]


def load_provider_settings() -> ProviderSettings:
    try:
        from PySide6.QtCore import QSettings
    except Exception:
        return ProviderSettings()
    q = QSettings()
    data = ProviderSettings()
    prefix = "agent_provider"
    try:
        schema = int(q.value(f"{prefix}/settings_schema_version", data.settings_schema_version))
        if schema > data.settings_schema_version:
            return data
        data.external_access_enabled = str(q.value(f"{prefix}/external_access_enabled", data.external_access_enabled)).lower() in {"1", "true", "yes"}
        data.provider_mode = ProviderMode(str(q.value(f"{prefix}/provider_mode", data.provider_mode.value)))
        data.openai_model = str(q.value(f"{prefix}/openai_model", data.openai_model))
        data.openai_escalation_model = str(q.value(f"{prefix}/openai_escalation_model", data.openai_escalation_model))
        data.gemini_model = str(q.value(f"{prefix}/gemini_model", data.gemini_model))
        data.custom_model_id = str(q.value(f"{prefix}/custom_model_id", data.custom_model_id))
        data.timeout_s = float(q.value(f"{prefix}/timeout_s", data.timeout_s))
        data.max_retries = int(q.value(f"{prefix}/max_retries", data.max_retries))
        data.reasoning_level = str(q.value(f"{prefix}/reasoning_level", data.reasoning_level))
        data.confidence_threshold = float(q.value(f"{prefix}/confidence_threshold", data.confidence_threshold))
        data.require_escalation_confirmation = str(q.value(f"{prefix}/require_escalation_confirmation", data.require_escalation_confirmation)).lower() in {"1", "true", "yes"}
        data.cache_enabled = str(q.value(f"{prefix}/cache_enabled", data.cache_enabled)).lower() in {"1", "true", "yes"}
        data.credential_mode = CredentialMode(str(q.value(f"{prefix}/credential_mode", data.credential_mode.value)))
        data.external_call_mode = ExternalCallMode(str(q.value(f"{prefix}/external_call_mode", data.external_call_mode.value)))
        data.configuration_version = int(q.value(f"{prefix}/configuration_version", data.configuration_version))
    except Exception:
        return ProviderSettings()
    return data


def save_provider_settings(settings: ProviderSettings) -> None:
    from PySide6.QtCore import QSettings

    q = QSettings()
    prefix = "agent_provider"
    for key, value in asdict(settings).items():
        if isinstance(value, Enum):
            value = value.value
        q.setValue(f"{prefix}/{key}", value)
    q.sync()
