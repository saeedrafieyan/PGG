"""Deterministic-first external-call decision policy."""

from __future__ import annotations

from porous_designer.agentic.contracts import ExternalCallDecision, ExternalCallDecisionCode, ParsedRequestResult


def decide_external_call(parsed: ParsedRequestResult, *, external_access_enabled: bool) -> ExternalCallDecision:
    unresolved_fields = [m.field_path for m in parsed.missing_requirements if m.severity == "blocking"]
    unresolved_ambiguities = [a.identifier for a in parsed.ambiguities if a.mandatory and not a.resolved_choice]
    unsupported = [u.feature for u in parsed.unsupported_requests]
    conflicts: list[str] = []
    if not external_access_enabled:
        return ExternalCallDecision(
            decision_code=ExternalCallDecisionCode.EXTERNAL_ACCESS_DISABLED,
            explanation="External access disabled; continuing with deterministic extraction and human review.",
            unresolved_fields=unresolved_fields,
            unresolved_ambiguities=unresolved_ambiguities,
            unsupported_requests=unsupported,
            human_review_required=True,
        )
    if not unresolved_fields and not unresolved_ambiguities and not unsupported:
        return ExternalCallDecision(
            decision_code=ExternalCallDecisionCode.NO_EXTERNAL_CALL_REQUIRED,
            explanation="External model not required: all required fields were extracted explicitly and no material ambiguity remains.",
            human_review_required=True,
        )
    if unresolved_fields:
        code = ExternalCallDecisionCode.EXTERNAL_CALL_REQUIRED_FOR_INTERPRETATION
        explanation = "External model may help interpret missing required fields."
    else:
        code = ExternalCallDecisionCode.EXTERNAL_CALL_RECOMMENDED
        explanation = "External model recommended because ambiguities or unsupported requirements need interpretation."
    return ExternalCallDecision(
        decision_code=code,
        explanation=explanation,
        unresolved_fields=unresolved_fields,
        unresolved_ambiguities=unresolved_ambiguities,
        detected_conflicts=conflicts,
        unsupported_requests=unsupported,
        human_review_required=True,
    )
