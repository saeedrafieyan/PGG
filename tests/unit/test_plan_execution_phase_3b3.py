from __future__ import annotations

from pathlib import Path

from porous_designer.agentic.strategy import (
    PlanExecutionSession,
    PlanStepExecution,
    apply_provider_next_action_wording,
    approve_strategy_plan,
    blocked_observation,
    cancelled_observation,
    create_execution_session,
    deterministic_strategy_plan,
    next_action_for_estimate,
    observation_for_estimate,
    observation_for_report,
    observation_for_run,
    recommendation_from_observation,
    skipped_observation,
    validation_gates_from_estimate,
    validation_gates_from_report,
)
from porous_designer.domain.enums import DomainShape, StructureFamily
from porous_designer.domain.specification import DesignSpecification, DomainSpec, ExportSpec, GenerationSpec, PorosityTarget, StructureSpec, TargetsSpec


def small_spec(tmp_path: Path | None = None) -> DesignSpecification:
    return DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[4.0, 4.0, 4.0]),
        structure=StructureSpec(family=StructureFamily.HCP_SPHERICAL_PORES, pore_diameter_mm=1.0),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.7, tolerance=0.1)),
        generation=GenerationSpec(preview_resolution_mm=0.5, final_resolution_mm=0.5),
        export=ExportSpec(output_directory=str(tmp_path or Path("runs")), output_name="phase_3b3_small"),
    )


def plan(tmp_path: Path | None = None):
    return deterministic_strategy_plan(small_spec(tmp_path), specification_revision=1)


def test_plan_execution_session_schema(tmp_path):
    p, _ = approve_strategy_plan(plan(tmp_path), decision="approved")
    session = create_execution_session(p)
    assert isinstance(session, PlanExecutionSession)
    assert session.plan_id == p.plan_id
    assert session.status == "ready"


def test_plan_step_execution_schema():
    execution = PlanStepExecution(step_id="step_1", deterministic_tool="estimate_resources", status="ready")
    assert execution.precondition_status == "not_checked"
    assert execution.user_authorized is False


def test_blocked_step_observation(tmp_path):
    p = plan(tmp_path)
    obs = blocked_observation(p, "step_2", "generate_preview", "Complete previous step first.")
    assert obs.status == "blocked"
    assert "previous" in obs.errors[0]


def test_estimate_observation_and_recommendation(tmp_path):
    p = plan(tmp_path)
    estimate = {"status": "feasible", "grid_shape": [8, 8, 8], "voxel_count": 512, "estimated_peak_mb": 1.2, "available_memory_mb": 1000, "runtime_class": "fast"}
    obs = observation_for_estimate(p, estimate)
    assert obs.tool_name == "estimate_resources"
    assert "Generate Preview" in obs.next_recommended_action
    assert next_action_for_estimate({"status": "conditionally_feasible"}).startswith("Resource estimate is high")


def test_preview_and_final_observations(tmp_path):
    p = plan(tmp_path)
    validation = tmp_path / "validation_report.json"
    validation.write_text('{"checks":[{"name":"watertight","status":"pass"}]}', encoding="utf-8")
    preview = observation_for_run(p, {"profile": "preview", "run_id": "p1", "validation_report_path": str(validation), "validation_passed": True, "stl_path": str(tmp_path / "p.stl")})
    final = observation_for_run(p, {"profile": "final", "run_id": "f1", "validation_report_path": str(validation), "validation_passed": True, "stl_sha256": "abc"})
    assert preview.tool_name == "generate_preview"
    assert final.tool_name == "generate_final"
    assert "Export" in final.next_recommended_action


def test_validation_gate_mapping(tmp_path):
    p = plan(tmp_path)
    assert validation_gates_from_estimate(p, {"status": "feasible"})[0].status == "PASS"
    report = {"checks": [{"name": "watertight", "status": "fail"}, {"name": "nonmanifold_edges", "status": "warning"}]}
    gates = validation_gates_from_report(p, report, profile="final")
    statuses = {gate.check_name: gate.status for gate in gates}
    assert statuses["watertight"] == "FAIL"
    assert statuses["nonmanifold_edges"] == "WARNING"


def test_optional_step_skipping_and_required_cancel_state(tmp_path):
    p = plan(tmp_path)
    skipped = skipped_observation(p, "optional", "run_sensitivity_analysis", "user skipped")
    cancelled = cancelled_observation(p, "step_5", "generate_final", "user cancelled")
    assert skipped.status == "skipped"
    assert cancelled.status == "cancelled"


def test_report_observation_hash(tmp_path):
    p = plan(tmp_path)
    report = tmp_path / "pgg_report.html"
    report.write_text("<html>ok</html>", encoding="utf-8")
    obs = observation_for_report(p, report)
    assert obs.status == "completed"
    assert obs.scalar_result_summary["report_sha256"]


def test_provider_wording_cannot_change_status(tmp_path):
    p = plan(tmp_path)
    obs = observation_for_estimate(p, {"status": "infeasible"})
    rec = recommendation_from_observation(obs)
    changed = apply_provider_next_action_wording(rec, {"status": "failed", "message": "Everything passed."})
    forbidden = apply_provider_next_action_wording(rec, {"status": rec.status, "message": "Run FEA next."})
    assert changed == rec
    assert forbidden == rec


def test_no_automatic_next_step_execution_model(tmp_path):
    p = plan(tmp_path)
    session = create_execution_session(p)
    assert session.current_step_id == ""
    assert session.completed_steps == []
