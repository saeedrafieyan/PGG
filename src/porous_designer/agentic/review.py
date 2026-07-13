"""Proposal building and human-approval records."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from porous_designer.agentic.contracts import ApprovalRecord, FieldReviewDecision, ParsedRequestResult, validate_field_value
from porous_designer.domain.enums import StructureFamily
from porous_designer.domain.specification import DesignSpecification


def build_proposed_specification(current: DesignSpecification, parsed: ParsedRequestResult) -> DesignSpecification:
    data = current.model_dump(mode="json")
    for field in parsed.extracted_fields:
        if field.requires_confirmation or field.status == "unsupported":
            continue
        _set_path(data, field.field_path, validate_field_value(field.field_path, field.value))
    _repair_structure_parameters(data)
    return DesignSpecification.model_validate(data)


def apply_review_decisions(current: DesignSpecification, parsed: ParsedRequestResult, decisions: list[FieldReviewDecision]) -> DesignSpecification:
    data = current.model_dump(mode="json")
    field_map = {field.field_path: field for field in parsed.extracted_fields}
    for decision in decisions:
        if decision.decision == "rejected":
            continue
        value = decision.edited_value if decision.decision == "edited" else field_map[decision.field_path].value
        _set_path(data, decision.field_path, validate_field_value(decision.field_path, value))
    _repair_structure_parameters(data)
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


def _repair_structure_parameters(data: dict[str, Any]) -> None:
    family = StructureFamily(data["structure"]["family"])
    if family.is_sphere_lattice:
        data["structure"]["unit_cell_size_mm"] = None
        data["structure"]["tpms_level_set"] = None
        if data["structure"].get("pore_diameter_mm") is None:
            data["structure"]["pore_diameter_mm"] = 1.0
    if family.is_tpms:
        data["structure"]["pore_diameter_mm"] = None
        data["structure"]["lattice_spacing_mm"] = None
        if data["structure"].get("unit_cell_size_mm") is None:
            data["structure"]["unit_cell_size_mm"] = 1.5
