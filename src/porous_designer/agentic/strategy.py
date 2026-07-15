"""Bounded engineering strategy planning for approved specifications."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator

from porous_designer.agentic.contracts import ParsedRequestResult, StrictModel
from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily
from porous_designer.domain.specification import DesignSpecification


STRATEGY_SCHEMA_VERSION = "3B.2"
DETERMINISTIC_BACKEND_VERSION = "phase_3b2_deterministic_tools_v1"
ALLOWED_DETERMINISTIC_TOOLS = {
    "estimate_resources",
    "generate_preview",
    "validate_preview",
    "generate_final",
    "validate_final",
    "export_html_report",
    "run_sensitivity_analysis",
}
FORBIDDEN_TOOL_TOKENS = {"step", "stp", "fea", "repair", "inverse", "optimize_material", "code", "python", "shell"}


class ToolCallProposal(StrictModel):
    tool_name: str
    purpose: str
    required_inputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    user_triggered_only: bool = True

    @field_validator("tool_name")
    @classmethod
    def allowed_tool(cls, value: str) -> str:
        if value not in ALLOWED_DETERMINISTIC_TOOLS:
            raise ValueError(f"Tool is not allowed in Phase 3B.2: {value}")
        return value


class ValidationGate(StrictModel):
    gate_id: str
    title: str
    checks: list[str]
    required_before: str
    failure_action: str


class UserCheckpoint(StrictModel):
    checkpoint_id: str
    title: str
    required_before: str
    decision_options: list[str]


class UnsupportedRequirementNote(StrictModel):
    feature: str
    source_text: str = ""
    explanation: str
    retained_as_future_requirement: bool = True


class RiskItem(StrictModel):
    risk_id: str
    severity: Literal["info", "warning", "blocking"] = "warning"
    description: str
    mitigation: str


class PlanAssumption(StrictModel):
    assumption_id: str
    description: str
    requires_user_confirmation: bool = False


class StrategyStep(StrictModel):
    step_id: str
    title: str
    purpose: str
    deterministic_tool: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    failure_handling: str
    requires_user_approval: bool = False
    execution_status: Literal["not_started", "ready", "running", "completed", "failed", "skipped"] = "not_started"

    @field_validator("deterministic_tool")
    @classmethod
    def allowed_tool(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_DETERMINISTIC_TOOLS:
            raise ValueError(f"Tool is not allowed in Phase 3B.2: {value}")
        return value


class PlanApprovalRecord(StrictModel):
    approval_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str
    specification_id: str
    specification_revision: int
    decision: Literal["approved", "rejected"]
    reviewer: str = "local_user"
    reviewed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""


class PlanObservation(StrictModel):
    plan_id: str
    step_id: str
    tool_name: str
    run_id: str | None = None
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: Literal["completed", "failed", "skipped"] = "completed"
    scalar_result_summary: dict[str, Any] = Field(default_factory=dict)
    validation_status: str = "not_measured"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    next_recommended_action: str = ""


class StrategyPlan(StrictModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: Literal["3B.2"] = STRATEGY_SCHEMA_VERSION
    specification_id: str
    specification_revision: int
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    planner_source: Literal["deterministic", "external_provider", "mock_provider"] = "deterministic"
    provider: str = "deterministic"
    model: str = "none"
    summary: str
    steps: list[StrategyStep]
    tool_proposals: list[ToolCallProposal] = Field(default_factory=list)
    validation_gates: list[ValidationGate] = Field(default_factory=list)
    user_checkpoints: list[UserCheckpoint] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    unsupported_requirements: list[UnsupportedRequirementNote] = Field(default_factory=list)
    assumptions: list[PlanAssumption] = Field(default_factory=list)
    estimated_resource_notes: list[str] = Field(default_factory=list)
    deterministic_backend_version: str = DETERMINISTIC_BACKEND_VERSION
    status: Literal["draft", "needs_review", "approved", "rejected", "stale"] = "needs_review"
    provider_explanation: str = ""


def deterministic_strategy_plan(
    specification: DesignSpecification,
    *,
    specification_revision: int,
    parsed_request: ParsedRequestResult | None = None,
) -> StrategyPlan:
    family = specification.structure.family
    is_tpms = family.is_tpms
    family_label = family.value.replace("_", " ")
    dimension_label = " x ".join(f"{value:g}" for value in specification.domain.dimensions_mm)
    summary = (
        f"Plan deterministic estimate, preview, validation, final STL generation, final validation, "
        f"and report export for revision {specification_revision} {family_label} structure in a "
        f"{specification.domain.shape.value} domain ({dimension_label} mm)."
    )
    steps = [
        _step("step_1", "Estimate resources", "Estimate voxel count, memory, and runtime class before geometry generation.", "estimate_resources", ["approved DesignSpecification"], ["resource estimate"], ["approved specification"], ["estimate status is not infeasible"], "Revise resolution or dimensions before generation if infeasible.", False, "ready"),
        _step("step_2", "Generate preview", "Generate a lower-resolution STL preview using the preview profile.", "generate_preview", ["approved DesignSpecification", "preview resolution"], ["preview STL", "preview validation report"], ["resource estimate reviewed"], ["preview artifact exists"], "Stop and report deterministic generation error.", True),
        _step("step_3", "Validate preview", "Review approximate porosity, connectivity, topology, and visual structure.", "validate_preview", ["preview STL", "preview validation report"], ["preview validation status"], ["preview generated"], ["preview validation is reviewed"], "Adjust specification through human review if validation is unacceptable.", False),
        _step("step_4", "User checkpoint before final", "Ask the user whether the preview is acceptable before final generation.", None, ["preview validation status"], ["proceed or revise decision"], ["preview reviewed"], ["user explicitly chooses the next action"], "Keep plan waiting for user decision.", True),
        _step("step_5", "Generate final STL", "Generate final STL using the final profile and deterministic seed.", "generate_final", ["approved DesignSpecification", "final resolution"], ["final STL", "final validation report"], ["user approved final generation"], ["final artifact exists"], "Stop and keep error details in the observation record.", True),
        _step("step_6", "Validate final STL", "Validate watertightness, nonmanifold edges, positive volume, mesh porosity, components, and pore percolation.", "validate_final", ["final STL", "final validation report"], ["accepted/warning/failed validation status"], ["final STL generated"], ["final validation is reviewed"], "Do not claim acceptance if validation fails.", False),
        _step("step_7", "Export HTML report", "Export a deterministic report summarizing inputs, artifacts, validation, and limitations.", "export_html_report", ["run directory"], ["HTML report"], ["final or preview run exists"], ["report path exists"], "Keep structured run data available if report export fails.", False),
        _step("step_8", "Archive or duplicate decision", "Ask the user whether to archive the run or duplicate the specification for another iteration.", None, ["completed run"], ["archive/duplicate/no-op decision"], ["report reviewed"], ["user chooses a follow-up"], "Leave run unchanged until user chooses.", True),
    ]
    unsupported = _unsupported_notes(specification, parsed_request, is_tpms)
    risks = [
        RiskItem(risk_id="risk_preview_resolution", severity="warning", description="Preview geometry is approximate and must not be treated as final validation.", mitigation="Use preview only for early review, then run final validation."),
        RiskItem(risk_id="risk_resource_limits", severity="warning", description="Fine final resolution may exceed local memory or runtime limits.", mitigation="Run estimate_resources before final generation."),
    ]
    assumptions = [
        PlanAssumption(assumption_id="assumption_stl", description="STL is the executable export format for this phase.", requires_user_confirmation=False),
        PlanAssumption(assumption_id="assumption_user_triggered", description="Every deterministic execution step requires an explicit user action.", requires_user_confirmation=False),
    ]
    if is_tpms:
        risks.append(RiskItem(risk_id="risk_tpms_metrics", severity="info", description="TPMS pore diameter and throat metrics are unavailable in Phase 3B.2.", mitigation="Report these as unsupported rather than measured."))
    if specification.domain.shape == DomainShape.CYLINDER:
        risks.append(RiskItem(risk_id="risk_cylinder_resolution", severity="warning", description="Cylinder boundaries are voxelized; dimensional accuracy depends on resolution.", mitigation="Review final validation and dimensional tolerance notes."))
        assumptions.append(PlanAssumption(assumption_id="assumption_cylinder_accuracy", description="Cylinder dimensional accuracy is bounded by selected voxel resolution.", requires_user_confirmation=False))
    gates = [
        ValidationGate(gate_id="gate_preview", title="Preview validation gate", checks=["approximate porosity", "pore connectivity", "visual structure"], required_before="generate_final", failure_action="Ask user to revise specification before final generation."),
        ValidationGate(gate_id="gate_final", title="Final validation gate", checks=["watertightness", "nonmanifold edges", "positive volume", "mesh porosity", "solid components", "pore components", "X/Y/Z pore percolation"], required_before="export_html_report", failure_action="Report failed checks and keep artifacts for review."),
    ]
    checkpoints = [
        UserCheckpoint(checkpoint_id="checkpoint_plan", title="Approve engineering strategy plan", required_before="generate_preview", decision_options=["approve", "reject", "regenerate"]),
        UserCheckpoint(checkpoint_id="checkpoint_final", title="Proceed to final generation", required_before="generate_final", decision_options=["proceed", "revise specification", "stop"]),
    ]
    tools = [
        ToolCallProposal(tool_name=tool, purpose=f"User-triggered deterministic tool: {tool}.")
        for tool in ["estimate_resources", "generate_preview", "validate_preview", "generate_final", "validate_final", "export_html_report"]
    ]
    return StrategyPlan(
        specification_id=specification.request_id,
        specification_revision=specification_revision,
        summary=summary,
        steps=steps,
        tool_proposals=tools,
        validation_gates=gates,
        user_checkpoints=checkpoints,
        risks=risks,
        unsupported_requirements=unsupported,
        assumptions=assumptions,
        estimated_resource_notes=["Run estimate_resources before preview/final decisions; no geometry is generated during planning."],
    )


def apply_provider_strategy_wording(base_plan: StrategyPlan, provider_payload: dict[str, Any], *, provider: str, model: str) -> StrategyPlan:
    """Accept only non-executable wording additions from an optional provider."""
    candidate = base_plan.model_copy(deep=True)
    text_fields = {
        "summary": provider_payload.get("summary"),
        "provider_explanation": provider_payload.get("provider_explanation") or provider_payload.get("explanation"),
    }
    additional_risks = provider_payload.get("risks", [])
    additional_notes = provider_payload.get("caution_notes", [])
    raw = json.dumps(provider_payload, default=str).lower()
    if any(token in raw for token in FORBIDDEN_TOOL_TOKENS):
        return base_plan
    if "steps" in provider_payload or "tool_proposals" in provider_payload or "validation_gates" in provider_payload:
        return base_plan
    if text_fields["summary"]:
        candidate.summary = str(text_fields["summary"])[:600]
    if text_fields["provider_explanation"]:
        candidate.provider_explanation = str(text_fields["provider_explanation"])[:1000]
    for index, risk in enumerate(additional_risks[:3], start=1):
        candidate.risks.append(RiskItem(risk_id=f"provider_risk_{index}", severity="info", description=str(risk)[:400], mitigation="Review during human plan approval."))
    for index, note in enumerate(additional_notes[:3], start=1):
        candidate.assumptions.append(PlanAssumption(assumption_id=f"provider_caution_{index}", description=str(note)[:400]))
    candidate.planner_source = "mock_provider" if provider == "mock" else "external_provider"
    candidate.provider = provider
    candidate.model = model
    return candidate


def approve_strategy_plan(plan: StrategyPlan, *, decision: Literal["approved", "rejected"], notes: str = "") -> tuple[StrategyPlan, PlanApprovalRecord]:
    updated = plan.model_copy(deep=True)
    updated.status = decision
    record = PlanApprovalRecord(
        plan_id=plan.plan_id,
        specification_id=plan.specification_id,
        specification_revision=plan.specification_revision,
        decision=decision,
        notes=notes,
    )
    return updated, record


def mark_plan_stale(plan: StrategyPlan) -> StrategyPlan:
    updated = plan.model_copy(deep=True)
    updated.status = "stale"
    return updated


def write_strategy_audit(
    session_dir: str | Path,
    *,
    plan: StrategyPlan,
    approval: PlanApprovalRecord | None = None,
    observations: list[PlanObservation] | None = None,
    provider_metadata: dict[str, Any] | None = None,
) -> Path:
    target = Path(session_dir) / "agentic"
    target.mkdir(parents=True, exist_ok=True)
    (target / "strategy_plan.json").write_text(json.dumps(plan.model_dump(mode="json"), indent=2), encoding="utf-8")
    review = {"plan_id": plan.plan_id, "status": plan.status, "review_required": plan.status in {"needs_review", "draft"}}
    (target / "strategy_plan_review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
    (target / "strategy_plan_approval.json").write_text(json.dumps(approval.model_dump(mode="json") if approval else {}, indent=2), encoding="utf-8")
    (target / "strategy_plan_observations.json").write_text(json.dumps([o.model_dump(mode="json") for o in observations or []], indent=2), encoding="utf-8")
    (target / "strategy_plan_provider_metadata.json").write_text(json.dumps(provider_metadata or {"provider": plan.provider, "model": plan.model}, indent=2), encoding="utf-8")
    return target


def observation_for_estimate(plan: StrategyPlan, estimate: dict[str, Any]) -> PlanObservation:
    return PlanObservation(
        plan_id=plan.plan_id,
        step_id=_step_for_tool(plan, "estimate_resources"),
        tool_name="estimate_resources",
        status="completed",
        scalar_result_summary={k: estimate.get(k) for k in ("status", "voxel_count", "memory_gb", "runtime_class") if k in estimate},
        validation_status=str(estimate.get("status", "unknown")),
        warnings=[str(estimate.get("message"))] if estimate.get("message") else [],
        next_recommended_action="Review preview generation step." if estimate.get("status") != "infeasible" else "Revise specification before generation.",
    )


def observation_for_run(plan: StrategyPlan, payload: dict[str, Any]) -> PlanObservation:
    profile = payload.get("profile")
    tool = "generate_preview" if profile == "preview" else "generate_final"
    return PlanObservation(
        plan_id=plan.plan_id,
        step_id=_step_for_tool(plan, tool),
        tool_name=tool,
        run_id=payload.get("run_id"),
        status="completed",
        scalar_result_summary={"profile": profile, "triangle_count": payload.get("triangle_count"), "porosity": payload.get("porosity")},
        validation_status=str(payload.get("validation_status", "not_measured")),
        artifact_paths=[str(value) for key, value in payload.items() if key.endswith("_path") or key in {"stl_path", "run_dir"}],
        next_recommended_action="Review preview validation before final generation." if profile == "preview" else "Review final validation and export report.",
    )


def _step(step_id: str, title: str, purpose: str, tool: str | None, inputs: list[str], outputs: list[str], preconditions: list[str], success: list[str], failure: str, approval: bool, status: str = "not_started") -> StrategyStep:
    return StrategyStep(step_id=step_id, title=title, purpose=purpose, deterministic_tool=tool, required_inputs=inputs, expected_outputs=outputs, preconditions=preconditions, success_criteria=success, failure_handling=failure, requires_user_approval=approval, execution_status=status)


def _unsupported_notes(specification: DesignSpecification, parsed_request: ParsedRequestResult | None, is_tpms: bool) -> list[UnsupportedRequirementNote]:
    notes = []
    if parsed_request is not None:
        for item in parsed_request.unsupported_requests:
            notes.append(UnsupportedRequirementNote(feature=item.feature, source_text=item.source_text, explanation=item.explanation, retained_as_future_requirement=item.retained_as_future_requirement))
    if ExportFormat.STEP in specification.export.formats or (parsed_request and any("step" in item.feature.lower() or "stp" in item.source_text.lower() for item in parsed_request.unsupported_requests)):
        notes.append(UnsupportedRequirementNote(feature="STEP/STP export", explanation="STEP/STP generation is unsupported in Phase 3B.2; executable export remains STL."))
    if is_tpms:
        notes.append(UnsupportedRequirementNote(feature="TPMS pore diameter and throat metrics", explanation="Pore diameter and throat-size metrics are not measured for TPMS structures in this phase."))
    if specification.targets.wall_target_mm is not None or specification.constraints.minimum_wall_thickness_mm is not None:
        notes.append(UnsupportedRequirementNote(feature="wall thickness measurement", explanation="Wall thickness is retained as a requirement but is not measured by Phase 3B.2 validation."))
    if specification.targets.throat_target_mm is not None or specification.constraints.minimum_throat_size_mm is not None:
        notes.append(UnsupportedRequirementNote(feature="throat size measurement", explanation="Throat size is retained as a requirement but is not measured by Phase 3B.2 validation."))
    return notes


def _step_for_tool(plan: StrategyPlan, tool_name: str) -> str:
    for step in plan.steps:
        if step.deterministic_tool == tool_name:
            return step.step_id
    return "unknown_step"
