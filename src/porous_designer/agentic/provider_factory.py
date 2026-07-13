"""Factory for configured agent providers."""

from __future__ import annotations

from porous_designer.agentic.contracts import ProviderMode
from porous_designer.agentic.provider import AgentProvider, GeminiProvider, NoLLMProvider, OpenAIProvider
from porous_designer.agentic.provider_config import ProviderSettings


def provider_from_settings(settings: ProviderSettings, *, client=None) -> AgentProvider:
    if settings.provider_mode == ProviderMode.OPENAI:
        return OpenAIProvider(settings, client=client)
    if settings.provider_mode == ProviderMode.GEMINI:
        return GeminiProvider(settings, client=client)
    return NoLLMProvider()
