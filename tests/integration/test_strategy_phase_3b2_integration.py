from __future__ import annotations

from pathlib import Path

from porous_designer.agentic.contracts import FieldReviewDecision
from porous_designer.agentic.orchestrator import AgenticRequestOrchestrator
from porous_designer.agentic.strategy import (
    approve_strategy_plan,
    deterministic_strategy_plan,
    mark_plan_stale,
    observation_for_estimate,
    observation_for_run,
    write_strategy_audit,
)
from porous_designer.domain.enums import StructureFamily
from porous_designer.gui.state_store import default_specification


def approve_all(orchestrator: AgenticRequestOrchestrator):
    parsed = orchestrator.last_result
    assert parsed is not None
    return [FieldReviewDecision(field_path=item.field_path, decision="accepted") for item in parsed.extracted_fields]


def approved_spec_from_request(tmp_path: Path, request: str):
    orchestrator = AgenticRequestOrchestrator(audit_root=tmp_path)
    orchestrator.parse_request(request, default_specification())
    approved, _ = orchestrator.approve(default_specification(), approve_all(orchestrator))
    return orchestrator, approved


def test_approved_explicit_hcp_specification_to_strategy_plan(tmp_path):
    orchestrator, approved = approved_spec_from_request(
        tmp_path,
        "Create a 10 x 10 x 5 mm HCP spherical-pore scaffold with 1.2 mm generating sphere diameter and 72% target porosity.",
    )
    plan = deterministic_strategy_plan(approved, specification_revision=1, parsed_request=orchestrator.last_result)
    assert plan.specification_id == approved.request_id
    assert any(step.deterministic_tool == "generate_preview" for step in plan.steps)


def test_federica_request_to_approved_spec_to_strategy_plan(tmp_path):
    orchestrator, approved = approved_spec_from_request(
        tmp_path,
        "Generate an 8 x 14 x 8 mm scaffold with hexagonal packing, 1 mm pore size, 75-80% porosity, interconnected pores, and STL and STP files.",
    )
    plan = deterministic_strategy_plan(approved, specification_revision=1, parsed_request=orchestrator.last_result)
    assert approved.structure.family == StructureFamily.HCP_SPHERICAL_PORES
    # Phase 4.1: STEP is written by generate_final, not by a separate tool.
    assert not any("STEP" in note.feature for note in plan.unsupported_requirements)
    assert not any(step.deterministic_tool == "generate_step" for step in plan.steps)


def test_gyroid_request_to_approved_spec_to_strategy_plan(tmp_path):
    orchestrator, approved = approved_spec_from_request(
        tmp_path,
        "Generate a 12 x 12 x 6 mm gyroid scaffold with a 2 mm unit-cell size and 70% porosity.",
    )
    plan = deterministic_strategy_plan(approved, specification_revision=1, parsed_request=orchestrator.last_result)
    assert approved.structure.family == StructureFamily.GYROID
    # Phase 4.2: TPMS wall and throat sizes are measured, so no unsupported notes remain.
    assert not any("TPMS" in note.explanation for note in plan.unsupported_requirements)


def test_plan_observation_after_estimate(tmp_path):
    _, approved = approved_spec_from_request(
        tmp_path,
        "Create a 4 x 4 x 4 mm HCP scaffold with 1 mm generating sphere diameter and 70% porosity.",
    )
    plan = deterministic_strategy_plan(approved, specification_revision=1)
    obs = observation_for_estimate(plan, {"status": "feasible", "voxel_count": 1000, "runtime_class": "small"})
    assert obs.tool_name == "estimate_resources"
    assert obs.scalar_result_summary["status"] == "feasible"


def test_plan_observation_after_preview(tmp_path):
    _, approved = approved_spec_from_request(
        tmp_path,
        "Create a 4 x 4 x 4 mm HCP scaffold with 1 mm generating sphere diameter and 70% porosity.",
    )
    plan = deterministic_strategy_plan(approved, specification_revision=1)
    obs = observation_for_run(plan, {"profile": "preview", "run_id": "run-1", "stl_path": str(tmp_path / "preview.stl"), "run_dir": str(tmp_path)})
    assert obs.tool_name == "generate_preview"
    assert obs.run_id == "run-1"
    assert obs.artifact_paths


def test_stale_plan_blocks_final_generation_semantics(tmp_path):
    _, approved = approved_spec_from_request(
        tmp_path,
        "Create a 4 x 4 x 4 mm HCP scaffold with 1 mm generating sphere diameter and 70% porosity.",
    )
    plan = deterministic_strategy_plan(approved, specification_revision=1)
    approved_plan, _ = approve_strategy_plan(plan, decision="approved")
    stale = mark_plan_stale(approved_plan)
    assert stale.status == "stale"


def test_approved_plan_permits_user_triggered_preview_semantics(tmp_path):
    _, approved = approved_spec_from_request(
        tmp_path,
        "Create a 4 x 4 x 4 mm HCP scaffold with 1 mm generating sphere diameter and 70% porosity.",
    )
    plan = deterministic_strategy_plan(approved, specification_revision=1)
    approved_plan, record = approve_strategy_plan(plan, decision="approved")
    assert approved_plan.status == "approved"
    assert record.decision == "approved"


def test_strategy_audit_files_are_written(tmp_path):
    _, approved = approved_spec_from_request(
        tmp_path,
        "Create a 4 x 4 x 4 mm HCP scaffold with 1 mm generating sphere diameter and 70% porosity.",
    )
    plan = deterministic_strategy_plan(approved, specification_revision=1)
    approved_plan, record = approve_strategy_plan(plan, decision="approved")
    audit = write_strategy_audit(tmp_path / "session", plan=approved_plan, approval=record, observations=[])
    assert (audit / "strategy_plan.json").exists()
    assert (audit / "strategy_plan_review.json").exists()
    assert (audit / "strategy_plan_approval.json").exists()
    assert (audit / "strategy_plan_observations.json").exists()
    assert (audit / "strategy_plan_provider_metadata.json").exists()
