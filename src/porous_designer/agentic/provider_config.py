"""Provider settings and model defaults.

AGE talks to hosted language models only through OpenRouter. Every sampling
parameter below is chosen for faithful extraction rather than creativity:
temperature 0, a fixed seed where the endpoint supports one, low reasoning
effort, and structured output routed only to endpoints that honour it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum

from porous_designer.agentic.contracts import ProviderMode

# Free OpenRouter models that advertised strict structured outputs when this
# default list was chosen (Sept 2026). The live catalog is checked at runtime,
# so a model that disappears or loses the capability is skipped, not trusted.
# Order follows the Phase 4.0 live benchmark: qwen answered in 6-34 s with the
# default data_collection="deny"; nex answered correctly but took 3-6 min;
# nemotron's free endpoints all require allowing prompt training, so it is only
# reached when the user enables data collection.
OPENROUTER_DEFAULT_MODEL = "qwen/qwen3.8-27b:free"
OPENROUTER_DEFAULT_FALLBACK_MODELS = (
    "nex-agi/nex-n2.5-pro:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
)

SETTINGS_SCHEMA_VERSION = 3


class CredentialMode(str, Enum):
    ENVIRONMENT = "environment"
    KEYRING = "keyring"
    SESSION = "session"


class ExternalCallMode(str, Enum):
    DETERMINISTIC_ONLY = "deterministic_only"
    WHEN_RECOMMENDED = "external_when_recommended"
    ALWAYS = "always_external"


@dataclass
class ProviderSettings:
    settings_schema_version: int = SETTINGS_SCHEMA_VERSION
    external_access_enabled: bool = False
    provider_mode: ProviderMode = ProviderMode.DETERMINISTIC_ONLY
    openrouter_model: str = OPENROUTER_DEFAULT_MODEL
    openrouter_fallback_models: list[str] = field(default_factory=lambda: list(OPENROUTER_DEFAULT_FALLBACK_MODELS))
    # Per-HTTP-request timeout. Free endpoints are often slow to start, so the
    # default is generous; the whole call (including retries and fallbacks) is
    # additionally bounded by ``total_deadline_s``.
    timeout_s: float = 60.0
    total_deadline_s: float = 180.0
    max_retries: int = 2
    temperature: float = 0.0
    seed: int = 7
    max_output_tokens: int = 3000
    reasoning_level: str = "low"
    # OpenRouter ``provider.data_collection``. "deny" excludes endpoints that
    # may store or train on prompts; some free models have no such endpoint.
    allow_provider_data_collection: bool = False
    cache_enabled: bool = True
    credential_mode: CredentialMode = CredentialMode.KEYRING
    external_call_mode: ExternalCallMode = ExternalCallMode.DETERMINISTIC_ONLY
    configuration_version: int = 0

    def selected_model(self) -> str:
        if self.provider_mode == ProviderMode.OPENROUTER:
            return self.openrouter_model
        return "deterministic"

    def model_chain(self) -> list[str]:
        chain: list[str] = []
        for model in [self.openrouter_model, *self.openrouter_fallback_models]:
            model = model.strip()
            if model and model not in chain:
                chain.append(model)
        return chain

    def selected_category(self) -> str:
        model = self.selected_model()
        if model == "deterministic":
            return "None"
        return "Free" if model.endswith(":free") else "Paid"

    def copy(self) -> "ProviderSettings":
        data = asdict(self)
        data["openrouter_fallback_models"] = list(self.openrouter_fallback_models)
        return ProviderSettings(**data)

    def bump_version(self) -> None:
        self.configuration_version += 1


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes"}


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(",") if v.strip()]


def load_provider_settings() -> ProviderSettings:
    try:
        from PySide6.QtCore import QSettings
    except Exception:
        return ProviderSettings()
    q = QSettings()
    data = ProviderSettings()
    prefix = "agent_provider"
    try:
        schema = int(q.value(f"{prefix}/settings_schema_version", 0) or 0)
        if schema > SETTINGS_SCHEMA_VERSION:
            return data
        if schema < SETTINGS_SCHEMA_VERSION:
            # Settings from the OpenAI/Gemini era cannot be carried over: the
            # provider, models, and credentials all differ. Keep only neutral
            # preferences and fall back to deterministic-only mode.
            data.cache_enabled = _as_bool(q.value(f"{prefix}/cache_enabled"), data.cache_enabled)
            return data
        data.external_access_enabled = _as_bool(q.value(f"{prefix}/external_access_enabled"), data.external_access_enabled)
        data.provider_mode = ProviderMode(str(q.value(f"{prefix}/provider_mode", data.provider_mode.value)))
        data.openrouter_model = str(q.value(f"{prefix}/openrouter_model", data.openrouter_model))
        stored_fallbacks = q.value(f"{prefix}/openrouter_fallback_models")
        if stored_fallbacks is not None:
            data.openrouter_fallback_models = _as_list(stored_fallbacks)
        data.timeout_s = float(q.value(f"{prefix}/timeout_s", data.timeout_s))
        data.total_deadline_s = float(q.value(f"{prefix}/total_deadline_s", data.total_deadline_s))
        data.max_retries = int(q.value(f"{prefix}/max_retries", data.max_retries))
        data.temperature = float(q.value(f"{prefix}/temperature", data.temperature))
        data.seed = int(q.value(f"{prefix}/seed", data.seed))
        data.max_output_tokens = int(q.value(f"{prefix}/max_output_tokens", data.max_output_tokens))
        data.reasoning_level = str(q.value(f"{prefix}/reasoning_level", data.reasoning_level))
        data.allow_provider_data_collection = _as_bool(q.value(f"{prefix}/allow_provider_data_collection"), data.allow_provider_data_collection)
        data.cache_enabled = _as_bool(q.value(f"{prefix}/cache_enabled"), data.cache_enabled)
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
        if isinstance(value, list):
            value = ",".join(value)
        q.setValue(f"{prefix}/{key}", value)
    q.sync()
