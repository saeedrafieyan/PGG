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


def merge_with_deterministic(deterministic: ParsedRequestResult, provider: ParsedRequestResult) -> ParsedRequestResult:
    """Combine an independent provider extraction with the deterministic one.

    Deterministic fields stay primary. A provider field fills a gap only when
    the deterministic parser found nothing for that path; when both found a
    value and they differ, the deterministic field is kept, marked for
    confirmation, and the conflict is recorded as a blocking disagreement.
    """
    merged = deterministic.model_copy(deep=True)
    merged.provider_mode = f"{provider.provider_mode}+deterministic"
    merged.parser_version = provider.parser_version or merged.parser_version
    disagreements = detect_provider_disagreements(deterministic, provider)
    conflicting = {d.field_path for d in disagreements}
    existing = {f.field_path for f in merged.extracted_fields}
    for field in merged.extracted_fields:
        if field.field_path in conflicting:
            field.requires_confirmation = True
    for field in provider.extracted_fields:
        if field.field_path not in existing:
            merged.extracted_fields.append(field.model_copy(deep=True))
            existing.add(field.field_path)
    filled = {f.field_path for f in provider.extracted_fields}
    merged.missing_requirements = [m for m in merged.missing_requirements if m.field_path not in filled]
    missing_paths = {m.field_path for m in merged.missing_requirements}
    for missing in provider.missing_requirements:
        if missing.field_path not in existing and missing.field_path not in missing_paths:
            merged.missing_requirements.append(missing.model_copy(deep=True))
            missing_paths.add(missing.field_path)
    known_ambiguities = {a.source_phrase for a in merged.ambiguities}
    merged.ambiguities.extend(a.model_copy(deep=True) for a in provider.ambiguities if a.source_phrase not in known_ambiguities)
    known_unsupported = {u.feature.lower() for u in merged.unsupported_requests}
    merged.unsupported_requests.extend(u.model_copy(deep=True) for u in provider.unsupported_requests if u.feature.lower() not in known_unsupported)
    known_assumptions = {a.field_path for a in merged.assumptions}
    merged.assumptions.extend(a.model_copy(deep=True) for a in provider.assumptions if a.field_path not in known_assumptions)
    merged.provider_metadata.update(provider.provider_metadata)
    merged.provider_metadata["provider_disagreements"] = [d.model_dump(mode="json") for d in disagreements]
    return merged


class RequestParserAgent:
    def __init__(
        self,
        provider: AgentProvider | None = None,
        *,
        timeout_s: float | None = None,
        settings: ProviderSettings | None = None,
        cache: ProviderResultCache | None = None,
    ) -> None:
        self.provider = provider or NoLLMProvider()
        self.settings = settings or ProviderSettings()
        # The provider bounds each HTTP request and its own retries; this is
        # the outer wall-clock limit for the whole call.
        self.timeout_s = timeout_s if timeout_s is not None else self.settings.total_deadline_s + 5.0
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
        if deterministic.provider_failure_reason == "prompt_injection_rejected":
            # A request rejected as unsafe is not forwarded to an external model.
            deterministic.provider_metadata["external_execution"] = "not_attempted"
            return deterministic
        schema = ParsedRequestResult.model_json_schema()
        payload = build_provider_payload(request, deterministic, schema)
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
            provider_result = call_provider_with_timeout(
                self.provider,
                request,
                payload,
                schema,
                timeout_s=self.timeout_s,
            )
        except Exception as error:
            error_record = classify_provider_exception(provider_name, model, error)
            deterministic.provider_failed = True
            deterministic.provider_failure_reason = redact_secrets(error)
            deterministic.provider_mode = "deterministic_fallback"
            deterministic.provider_metadata["external_execution"] = "failed"
            deterministic.provider_metadata["fallback_reason"] = deterministic.provider_failure_reason
            deterministic.provider_metadata["provider_error"] = error_record.model_dump(mode="json")
            attempts = getattr(self.provider, "last_attempts", None)
            if attempts:
                deterministic.provider_metadata["attempts"] = list(attempts)
            deterministic.provider_metadata["external_call_decision"] = {
                **decision.model_dump(mode="json"),
                "decision_code": ExternalCallDecisionCode.DETERMINISTIC_FALLBACK.value,
            }
            return deterministic
        result = merge_with_deterministic(deterministic, provider_result)
        result.provider_metadata.setdefault("external_call_decision", decision.model_dump(mode="json"))
        result.provider_metadata.setdefault("external_call_mode", self.settings.external_call_mode.value)
        result.provider_metadata["external_execution"] = "completed"
        result.provider_metadata["provider_request_redacted"] = {
            "request": request,
            "note": "Independent extraction: the deterministic result is not sent to the provider.",
        }
        self.cache.set(cache_key, result)
        return result
