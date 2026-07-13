"""Schema-validated request parsing assistant wrapper."""

from __future__ import annotations

from porous_designer.agentic.contracts import ParsedRequestResult
from porous_designer.agentic.deterministic_parser import DeterministicRequestParser
from porous_designer.agentic.provider import AgentProvider, NoLLMProvider, call_provider_with_timeout


class RequestParserAgent:
    def __init__(self, provider: AgentProvider | None = None, *, timeout_s: float = 10.0) -> None:
        self.provider = provider or NoLLMProvider()
        self.timeout_s = timeout_s
        self.deterministic = DeterministicRequestParser()

    def parse(self, request: str) -> ParsedRequestResult:
        deterministic = self.deterministic.parse(request)
        if isinstance(self.provider, NoLLMProvider) or not getattr(self.provider, "enabled", False):
            return deterministic
        schema = ParsedRequestResult.model_json_schema()
        try:
            return call_provider_with_timeout(
                self.provider,
                request,
                deterministic.model_dump(mode="json"),
                schema,
                timeout_s=self.timeout_s,
            )
        except Exception as first_error:
            try:
                feedback = deterministic.model_dump(mode="json")
                feedback["schema_error_feedback"] = str(first_error)
                return call_provider_with_timeout(
                    self.provider,
                    request,
                    feedback,
                    schema,
                    timeout_s=self.timeout_s,
                )
            except Exception as second_error:
                deterministic.provider_failed = True
                deterministic.provider_failure_reason = f"{first_error}; fallback after retry: {second_error}"
                deterministic.provider_mode = "deterministic_fallback"
                return deterministic
