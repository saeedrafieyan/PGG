from __future__ import annotations

import pytest

from porous_designer.agentic.strategy import (
    ALLOWED_DETERMINISTIC_TOOLS,
    StrategyStep,
    apply_provider_strategy_wording,
    approve_strategy_plan,
    deterministic_strategy_plan,
    mark_plan_stale,
)
from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily
from porous_designer.domain.specification import (
    ConstraintsSpec,
    DesignSpecification,
    DomainSpec,
    ExportSpec,
    GenerationSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
)


def spec_for(family: StructureFamily, *, cylinder: bool = False, wall: bool = False, throat: bool = False, step: bool = False) -> DesignSpecification:
    is_tpms = family.is_tpms
    return DesignSpecification(
        domain=DomainSpec(shape=DomainShape.CYLINDER, dimensions_mm=[8.0, 12.0]) if cylinder else DomainSpec(shape=DomainShape.BOX, dimensions_mm=[8.0, 14.0, 8.0]),
        structure=StructureSpec(
            family=family,
            pore_diameter_mm=None if is_tpms else 1.0,
            unit_cell_size_mm=2.0 if is_tpms else None,
        ),
        targets=TargetsSpec(
            porosity_target=PorosityTarget(target=0.75, tolerance=0.05),
            wall_target_mm=0.4 if wall else None,
            throat_target_mm=0.3 if throat else None,
        ),
        constraints=ConstraintsSpec(
            minimum_wall_thickness_mm=0.4 if wall else None,
            minimum_throat_size_mm=0.3 if throat else None,
        ),
        generation=GenerationSpec(preview_resolution_mm=0.4, final_resolution_mm=0.2),
        export=ExportSpec(formats=[ExportFormat.STL, ExportFormat.STEP] if step else [ExportFormat.STL]),
    )


def tool_names(plan):
    return {step.deterministic_tool for step in plan.steps if step.deterministic_tool}


def test_deterministic_plan_generation_for_sc():
    plan = deterministic_strategy_plan(spec_for(StructureFamily.SC_SPHERICAL_PORES), specification_revision=1)
    assert plan.status == "needs_review"
    assert {"estimate_resources", "generate_preview", "validate_preview", "generate_final", "validate_final", "export_html_report"} <= tool_names(plan)
    assert tool_names(plan) <= ALLOWED_DETERMINISTIC_TOOLS
    assert plan.user_checkpoints
    assert plan.validation_gates


def test_deterministic_plan_generation_for_hcp():
    plan = deterministic_strategy_plan(spec_for(StructureFamily.HCP_SPHERICAL_PORES), specification_revision=2)
    assert "hcp spherical pores" in plan.summary
    assert plan.specification_revision == 2


def test_deterministic_plan_generation_for_gyroid():
    plan = deterministic_strategy_plan(spec_for(StructureFamily.GYROID), specification_revision=1)
    text = " ".join(note.explanation for note in plan.unsupported_requirements)
    assert "TPMS" in text
    assert "throat" in text


def test_deterministic_plan_generation_for_cylinder():
    plan = deterministic_strategy_plan(spec_for(StructureFamily.DIAMOND, cylinder=True), specification_revision=1)
    assert any("Cylinder" in risk.description for risk in plan.risks)
    assert any("dimensional accuracy" in item.description for item in plan.assumptions)


def test_step_is_planned_and_wall_throat_notes_remain():
    # Phase 4.1: STEP is exported by generate_final; wall/throat stay unmeasured.
    plan = deterministic_strategy_plan(
        spec_for(StructureFamily.HCP_SPHERICAL_PORES, step=True, wall=True, throat=True),
        specification_revision=1,
    )
    features = {note.feature for note in plan.unsupported_requirements}
    assert "STEP/STP export" not in features
    assert any("STEP" in step.purpose for step in plan.steps if step.deterministic_tool == "generate_final")
    assert "wall thickness measurement" in features
    assert "throat size measurement" in features
    assert "generate_step" not in tool_names(plan)


def test_plan_schema_rejects_forbidden_tool():
    with pytest.raises(ValueError):
        StrategyStep(
            step_id="bad",
            title="Bad",
            purpose="Bad",
            deterministic_tool="generate_step",
            failure_handling="stop",
        )


def test_plan_stale_when_specification_revision_changes():
    plan = deterministic_strategy_plan(spec_for(StructureFamily.SC_SPHERICAL_PORES), specification_revision=1)
    stale = mark_plan_stale(plan)
    assert stale.status == "stale"
    assert plan.status == "needs_review"


def test_plan_approval_record():
    plan = deterministic_strategy_plan(spec_for(StructureFamily.SC_SPHERICAL_PORES), specification_revision=1)
    approved, record = approve_strategy_plan(plan, decision="approved")
    assert approved.status == "approved"
    assert record.plan_id == plan.plan_id
    assert record.decision == "approved"


def test_provider_wording_rejected_when_it_adds_forbidden_tools():
    plan = deterministic_strategy_plan(spec_for(StructureFamily.SC_SPHERICAL_PORES), specification_revision=1)
    enhanced = apply_provider_strategy_wording(
        plan,
        {"summary": "Run FEA and generate STEP before final.", "tool_proposals": [{"tool_name": "fea"}]},
        provider="mock",
        model="mock",
    )
    assert enhanced == plan


def test_provider_wording_can_only_add_non_executable_explanation():
    plan = deterministic_strategy_plan(spec_for(StructureFamily.SC_SPHERICAL_PORES), specification_revision=1)
    enhanced = apply_provider_strategy_wording(
        plan,
        {"summary": "Use a cautious preview-first engineering plan.", "provider_explanation": "Review porosity before final generation."},
        provider="mock",
        model="mock",
    )
    assert enhanced.summary.startswith("Use a cautious")
    assert enhanced.provider_explanation
    assert tool_names(enhanced) == tool_names(plan)


def test_no_automatic_execution_and_no_geometry_generation_during_planning(monkeypatch):
    called = {"generation": 0}

    def fail_generation(*args, **kwargs):
        called["generation"] += 1
        raise AssertionError("planning must not generate geometry")

    monkeypatch.setattr("porous_designer.services.generation_service.generate_porous_stl", fail_generation)
    plan = deterministic_strategy_plan(spec_for(StructureFamily.SC_SPHERICAL_PORES), specification_revision=1)
    assert called["generation"] == 0
    assert all(step.execution_status in {"not_started", "ready"} for step in plan.steps)
