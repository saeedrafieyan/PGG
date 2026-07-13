"""Provider-neutral agent interface for optional request interpretation."""

from __future__ import annotations

import concurrent.futures
import json
from typing import Any, Protocol

from porous_designer.agentic.contracts import ParsedRequestResult


class AgentProvider(Protocol):
    name: str
    enabled: bool

    def parse_request(self, request: str, deterministic_evidence: dict, schema: dict) -> dict:
        ...

    def explain_ambiguities(self, request: str, parsed_result: dict, ambiguity_rules: list[dict]) -> dict:
        ...

    def explain_feasibility(self, deterministic_result: dict, approved_specification: dict) -> dict:
        ...


class NoLLMProvider:
    name = "NoLLMProvider"
    enabled = True

    def parse_request(self, request: str, deterministic_evidence: dict, schema: dict) -> dict:
        return deterministic_evidence

    def explain_ambiguities(self, request: str, parsed_result: dict, ambiguity_rules: list[dict]) -> dict:
        return {"mode": "deterministic", "ambiguities": ambiguity_rules}

    def explain_feasibility(self, deterministic_result: dict, approved_specification: dict) -> dict:
        status = deterministic_result.get("status", "unknown")
        return {"summary": f"Deterministic feasibility status: {status}.", "status": status}


class MockAgentProvider:
    name = "MockAgentProvider"
    enabled = True

    def __init__(self, response: dict | None = None, *, invalid_json: bool = False, timeout: bool = False) -> None:
        self.response = response
        self.invalid_json = invalid_json
        self.timeout = timeout

    def parse_request(self, request: str, deterministic_evidence: dict, schema: dict) -> dict:
        if self.timeout:
            raise TimeoutError("Mock provider timed out.")
        if self.invalid_json:
            return {"unexpected": "field"}
        return self.response or deterministic_evidence

    def explain_ambiguities(self, request: str, parsed_result: dict, ambiguity_rules: list[dict]) -> dict:
        return {"mode": "mock", "ambiguities": ambiguity_rules}

    def explain_feasibility(self, deterministic_result: dict, approved_specification: dict) -> dict:
        return {"summary": "Mock explanation follows deterministic status.", "status": deterministic_result.get("status")}


class ExternalAgentProviderAdapter:
    """Disabled-by-default adapter boundary for future external providers."""

    def __init__(self, *, enabled: bool = False, timeout_s: float = 10.0, provider_name: str = "external_json_provider") -> None:
        self.enabled = enabled
        self.timeout_s = timeout_s
        self.name = provider_name

    def parse_request(self, request: str, deterministic_evidence: dict, schema: dict) -> dict:
        if not self.enabled:
            raise RuntimeError("External agent access is disabled by default.")
        raise NotImplementedError("External provider transport is intentionally not configured in Phase 3B.1.")

    def explain_ambiguities(self, request: str, parsed_result: dict, ambiguity_rules: list[dict]) -> dict:
        if not self.enabled:
            raise RuntimeError("External agent access is disabled by default.")
        return {}

    def explain_feasibility(self, deterministic_result: dict, approved_specification: dict) -> dict:
        if not self.enabled:
            raise RuntimeError("External agent access is disabled by default.")
        return {}


def call_provider_with_timeout(provider: AgentProvider, request: str, deterministic_evidence: dict, schema: dict, *, timeout_s: float = 10.0) -> ParsedRequestResult:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(provider.parse_request, request, deterministic_evidence, schema)
        raw = future.result(timeout=timeout_s)
    if isinstance(raw, str):
        raw = json.loads(raw)
    return ParsedRequestResult.model_validate(raw)
