"""Provider settings and model defaults for Phase 3B.1.1."""

from __future__ import annotations

from dataclasses import dataclass

from porous_designer.agentic.contracts import ProviderMode

OPENAI_LOW_COST_MODEL = "gpt-5.6-luna"
OPENAI_ESCALATION_MODEL = "gpt-5.6-terra"
GEMINI_LOW_COST_MODEL = "gemini-3.1-flash-lite"


@dataclass
class ModelChoice:
    provider: ProviderMode
    model_id: str
    category: str
    description: str


@dataclass
class ProviderSettings:
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


MODEL_CHOICES = [
    ModelChoice(ProviderMode.OPENAI, OPENAI_LOW_COST_MODEL, "Low cost", "Recommended parsing default"),
    ModelChoice(ProviderMode.OPENAI, OPENAI_ESCALATION_MODEL, "Balanced", "Optional escalation"),
    ModelChoice(ProviderMode.GEMINI, GEMINI_LOW_COST_MODEL, "Low cost", "Recommended parsing default"),
]
