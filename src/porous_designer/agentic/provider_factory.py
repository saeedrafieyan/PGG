"""Factory for configured agent providers."""

from __future__ import annotations

from porous_designer.agentic.contracts import ProviderMode
from porous_designer.agentic.provider import AgentProvider, NoLLMProvider, OpenRouterProvider
from porous_designer.agentic.provider_config import ProviderSettings


def provider_from_settings(settings: ProviderSettings, *, client=None, catalog=None) -> AgentProvider:
    if settings.provider_mode == ProviderMode.OPENROUTER:
        return OpenRouterProvider(settings, client=client, catalog=catalog)
    return NoLLMProvider()
