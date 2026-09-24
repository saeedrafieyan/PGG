"""Proposal building and human-approval records."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from porous_designer.agentic.contracts import (
    ApprovalRecord,
    Assumption,
    ExtractedField,
    FieldReviewDecision,
    FieldSource,
    ParsedRequestResult,
    validate_field_value,
)
from porous_designer.domain.enums import StructureFamily
from porous_designer.domain.specification import DesignSpecification


# Values used only when neither the request nor the current specification
# provides the parameter the chosen family needs. They are always shown to the
# user as confirmation-required rows, never applied silently.
STRUCTURE_PARAMETER_DEFAULTS_MM = {
    "structure.pore_diameter_mm": 1.0,
    "structure.unit_cell_size_mm": 1.5,
}


def build_proposed_specification(current: DesignSpecification, parsed: ParsedRequestResult) -> DesignSpecification:
    """Preview specification from the auto-applicable fields of ``parsed``.

    If the chosen family needs a parameter the request did not state, a
    DEFAULT-source field is appended to ``parsed.extracted_fields`` (and an
    assumption recorded) so the review step shows where the value came from.
    """
    data = current.model_dump(mode="json")
    for field in parsed.extracted_fields:
        if field.requires_confirmation or field.status == "unsupported":
            continue
        _set_path(data, field.field_path, validate_field_value(field.field_path, field.value))
    required = _clear_irrelevant_structure_parameters(data)
    if required is not None:
        _propose_required_parameter(data, parsed, required)
    return DesignSpecification.model_validate(data)


def apply_review_decisions(current: DesignSpecification, parsed: ParsedRequestResult, decisions: list[FieldReviewDecision]) -> DesignSpecification:
    data = current.model_dump(mode="json")
    field_map = {field.field_path: field for field in parsed.extracted_fields}
    for decision in decisions:
        if decision.decision == "rejected":
            continue
        value = decision.edited_value if decision.decision == "edited" else field_map[decision.field_path].value
        _set_path(data, decision.field_path, validate_field_value(decision.field_path, value))
    required = _clear_irrelevant_structure_parameters(data)
    if required is not None and _get_path(data, required) is None:
        family = data["structure"]["family"]
        raise ValueError(
            f"{required} is required for {family} but was not approved. Accept the proposed value or enter one before approval."
        )
    return DesignSpecification.model_validate(data)


def create_approval_record(
    *,
    original_request: str,
    parsed: ParsedRequestResult,
    approved_specification: DesignSpecification,
    decisions: list[FieldReviewDecision],
    ambiguity_resolutions: dict[str, str] | None = None,
    reviewer: str = "local_user",
) -> ApprovalRecord:
    accepted = {}
    for decision in decisions:
        if decision.decision != "rejected":
            accepted[decision.field_path] = decision.edited_value if decision.decision == "edited" else "accepted"
    return ApprovalRecord(
        original_request=original_request,
        deterministic_extraction=parsed.model_dump(mode="json"),
        provider_result=None if parsed.provider_mode.startswith("deterministic") else parsed.model_dump(mode="json"),
        ambiguity_resolutions=ambiguity_resolutions or {},
        field_decisions=decisions,
        final_approved_fields=accepted,
        approved_specification=approved_specification.model_dump(mode="json"),
        reviewer=reviewer,
        provider_mode=parsed.provider_mode,
        parser_version=parsed.parser_version,
    )


def mark_stale(record: ApprovalRecord) -> ApprovalRecord:
    stale = record.model_copy(deep=True)
    stale.status = "stale"
    return stale


def _set_path(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    target = data
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _get_path(data: dict[str, Any], dotted: str) -> Any:
    target: Any = data
    for part in dotted.split("."):
        if not isinstance(target, dict):
            return None
        target = target.get(part)
    return target


def _clear_irrelevant_structure_parameters(data: dict[str, Any]) -> str | None:
    """Null the parameters the family does not use; return the one it needs."""
    family = StructureFamily(data["structure"]["family"])
    if family.is_sphere_lattice:
        data["structure"]["unit_cell_size_mm"] = None
        data["structure"]["tpms_level_set"] = None
        return "structure.pore_diameter_mm"
    if family.uses_unit_cell:
        data["structure"]["pore_diameter_mm"] = None
        data["structure"]["lattice_spacing_mm"] = None
        return "structure.unit_cell_size_mm"
    return None


def _propose_required_parameter(data: dict[str, Any], parsed: ParsedRequestResult, path: str) -> None:
    stated = next((f for f in parsed.extracted_fields if f.field_path == path and f.status != "unsupported"), None)
    if stated is not None:
        # The request states it but it still needs confirmation; preview it.
        if _get_path(data, path) is None:
            _set_path(data, path, validate_field_value(path, stated.value))
        return
    current = _get_path(data, path)
    if current is not None:
        value, rationale = current, "Not stated in the request; kept from the current specification."
    else:
        value, rationale = STRUCTURE_PARAMETER_DEFAULTS_MM[path], "Not stated in the request; generic default proposed for review."
        _set_path(data, path, value)
    parsed.extracted_fields.append(
        ExtractedField(
            field_path=path,
            value=value,
            unit="mm",
            confidence=0.5,
            source_text="",
            source=FieldSource.DEFAULT,
            requires_confirmation=True,
        )
    )
    if not any(a.field_path == path for a in parsed.assumptions):
        parsed.assumptions.append(Assumption(field_path=path, value=value, rationale=rationale, requires_confirmation=True))
