"""Schema-validated request parsing assistant wrapper."""

from __future__ import annotations

from porous_designer.agentic.cache import ProviderResultCache
from porous_designer.agentic.call_policy import decide_external_call
from porous_designer.agentic.contracts import ExternalCallDecisionCode, ParsedRequestResult
from porous_designer.agentic.deterministic_parser import DeterministicRequestParser
from porous_designer.agentic.disagreement import detect_provider_disagreements
from porous_designer.agentic.payload import build_provider_payload
from porous_designer.agentic.provider import AgentProvider, NoLLMProvider, call_provider_with_timeout
from porous_designer.agentic.provider_config import ProviderSettings
from porous_designer.agentic.provider_errors import classify_provider_exception, redact_secrets


class RequestParserAgent:
    def __init__(
        self,
        provider: AgentProvider | None = None,
        *,
        timeout_s: float = 10.0,
        settings: ProviderSettings | None = None,
        cache: ProviderResultCache | None = None,
    ) -> None:
        self.provider = provider or NoLLMProvider()
        self.settings = settings or ProviderSettings()
        self.timeout_s = timeout_s
        self.deterministic = DeterministicRequestParser()
        self.cache = cache or ProviderResultCache(enabled=self.settings.cache_enabled)

    def parse(self, request: str) -> ParsedRequestResult:
        deterministic = self.deterministic.parse(request)
        decision = decide_external_call(
            deterministic,
            external_access_enabled=self.settings.external_access_enabled,
            external_call_mode=self.settings.external_call_mode,
        )
        deterministic.provider_metadata["external_call_decision"] = decision.model_dump(mode="json")
        deterministic.provider_metadata["external_call_mode"] = self.settings.external_call_mode.value
        deterministic.provider_metadata["selected_provider"] = self.settings.provider_mode.value
        deterministic.provider_metadata["selected_model"] = self.settings.selected_model()
        deterministic.provider_metadata["deterministic_summary"] = {
            "extracted_field_count": len(deterministic.extracted_fields),
            "missing_requirement_count": len(deterministic.missing_requirements),
            "ambiguity_count": len(deterministic.ambiguities),
            "unsupported_request_count": len(deterministic.unsupported_requests),
        }
        if isinstance(self.provider, NoLLMProvider) or decision.decision_code in {
            ExternalCallDecisionCode.NO_EXTERNAL_CALL_REQUIRED,
            ExternalCallDecisionCode.EXTERNAL_ACCESS_DISABLED,
        }:
            deterministic.provider_metadata["external_execution"] = "not_attempted"
            return deterministic
        schema = ParsedRequestResult.model_json_schema()
        payload = build_provider_payload(request, deterministic, schema)
        deterministic.provider_metadata["provider_request_redacted"] = payload
        provider_name = getattr(self.provider, "name", "provider")
        model = getattr(self.provider, "model", self.settings.selected_model())
        cache_key = self.cache.key(
            request=request,
            parser_version=deterministic.parser_version,
            provider=provider_name,
            model=model,
            schema_version=deterministic.schema_version,
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            cached.provider_metadata["cache_status"] = "hit"
            return cached
        try:
            result = call_provider_with_timeout(
                self.provider,
                request,
                payload,
                schema,
                timeout_s=self.timeout_s,
            )
            result.provider_metadata.setdefault("external_call_decision", decision.model_dump(mode="json"))
            result.provider_metadata.setdefault("external_call_mode", self.settings.external_call_mode.value)
            result.provider_metadata["external_execution"] = "completed"
            result.provider_metadata["provider_request_redacted"] = payload
            result.provider_metadata["provider_disagreements"] = [d.model_dump(mode="json") for d in detect_provider_disagreements(deterministic, result)]
            self.cache.set(cache_key, result)
            return result
        except Exception as first_error:
            try:
                feedback = payload
                feedback["schema_error_feedback"] = str(first_error)
                result = call_provider_with_timeout(
                    self.provider,
                    request,
                    feedback,
                    schema,
                    timeout_s=self.timeout_s,
                )
                result.provider_metadata.setdefault("external_call_decision", decision.model_dump(mode="json"))
                result.provider_metadata.setdefault("external_call_mode", self.settings.external_call_mode.value)
                result.provider_metadata["external_execution"] = "completed_after_retry"
                result.provider_metadata["provider_request_redacted"] = payload
                result.provider_metadata["provider_disagreements"] = [d.model_dump(mode="json") for d in detect_provider_disagreements(deterministic, result)]
                self.cache.set(cache_key, result)
                return result
            except Exception as second_error:
                error = classify_provider_exception(provider_name, model, second_error)
                deterministic.provider_failed = True
                deterministic.provider_failure_reason = f"{redact_secrets(first_error)}; fallback after retry: {redact_secrets(second_error)}"
                deterministic.provider_mode = "deterministic_fallback"
                deterministic.provider_metadata["external_execution"] = "failed"
                deterministic.provider_metadata["fallback_reason"] = deterministic.provider_failure_reason
                deterministic.provider_metadata["provider_error"] = error.model_dump(mode="json")
                deterministic.provider_metadata["external_call_decision"] = {
                    **decision.model_dump(mode="json"),
                    "decision_code": ExternalCallDecisionCode.DETERMINISTIC_FALLBACK.value,
                }
                return deterministic
        else:
            # Unreachable because the try returns on success, but kept explicit
            # for future transport branches.
            return deterministic
