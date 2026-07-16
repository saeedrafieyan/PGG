from __future__ import annotations

import json
from pathlib import Path

from porous_designer.agentic.strategy import (
    approve_strategy_plan,
    create_execution_session,
    deterministic_strategy_plan,
    observation_for_estimate,
    observation_for_report,
    observation_for_run,
    skipped_observation,
    validation_gates_from_report,
    write_plan_execution_audit,
)
from porous_designer.domain.enums import DomainShape, StructureFamily
from porous_designer.domain.specification import DesignSpecification, DomainSpec, ExportSpec, GenerationSpec, PorosityTarget, StructureSpec, TargetsSpec
from porous_designer.gui.reporting import generate_html_report
from porous_designer.gui.models.run_history_model import RunHistoryStore
from porous_designer.services.generation_service import GenerationProfile, generate_porous_stl
from porous_designer.services.resource_estimation import estimate_resources


def small_hcp_spec(tmp_path: Path) -> DesignSpecification:
    return DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[2.5, 2.5, 2.5]),
        structure=StructureSpec(family=StructureFamily.SC_SPHERICAL_PORES, pore_diameter_mm=0.8),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.45, tolerance=0.2)),
        generation=GenerationSpec(preview_resolution_mm=0.5, final_resolution_mm=0.5, maximum_memory_gb=4.0),
        export=ExportSpec(output_directory=str(tmp_path), output_name="phase_3b3_exec"),
    )


def approved_plan(tmp_path: Path):
    spec = small_hcp_spec(tmp_path)
    plan = deterministic_strategy_plan(spec, specification_revision=1)
    plan, approval = approve_strategy_plan(plan, decision="approved")
    return spec, plan, approval


def test_approved_hcp_plan_run_estimate_step(tmp_path):
    spec, plan, _ = approved_plan(tmp_path)
    estimate = estimate_resources(spec, spec.generation.final_resolution_mm).to_dict()
    obs = observation_for_estimate(plan, estimate)
    assert obs.tool_name == "estimate_resources"
    assert obs.scalar_result_summary["voxel_count"] > 0


def test_approved_hcp_plan_run_preview_step(tmp_path):
    spec, plan, _ = approved_plan(tmp_path)
    result = generate_porous_stl(spec, profile=GenerationProfile.PREVIEW)
    payload = {
        "profile": "preview",
        "run_id": result.run_id,
        "run_dir": str(result.run_dir),
        "stl_path": str(result.stl_path),
        "validation_report_path": str(result.run_dir / "validation_report.json"),
        "validation_passed": result.validation_passed,
        "final_mesh_porosity": result.final_mesh_porosity,
        "connectivity": result.connectivity,
        "stl_sha256": result.stl_sha256,
    }
    obs = observation_for_run(plan, payload)
    assert obs.tool_name == "generate_preview"
    assert obs.artifact_paths


def test_approved_hcp_plan_run_final_step_with_small_fixture(tmp_path):
    spec, plan, _ = approved_plan(tmp_path)
    result = generate_porous_stl(spec, profile=GenerationProfile.FINAL)
    payload = {
        "profile": "final",
        "run_id": result.run_id,
        "run_dir": str(result.run_dir),
        "stl_path": str(result.stl_path),
        "validation_report_path": str(result.run_dir / "validation_report.json"),
        "validation_passed": result.validation_passed,
        "final_mesh_porosity": result.final_mesh_porosity,
        "watertight": result.watertight,
        "solid_components": result.solid_components,
        "connectivity": result.connectivity,
        "stl_sha256": result.stl_sha256,
        "timing": result.timing.__dict__,
        "peak_memory_mb": result.peak_memory_mb,
    }
    obs = observation_for_run(plan, payload)
    assert obs.tool_name == "generate_final"
    assert "stl_sha256" in obs.scalar_result_summary


def test_final_validation_result_maps_to_gates(tmp_path):
    spec, plan, _ = approved_plan(tmp_path)
    result = generate_porous_stl(spec, profile=GenerationProfile.PREVIEW)
    report = json.loads((result.run_dir / "validation_report.json").read_text(encoding="utf-8"))
    gates = validation_gates_from_report(plan, report, profile="preview")
    assert gates
    assert {gate.status for gate in gates} <= {"PASS", "WARNING", "FAIL", "NOT_AVAILABLE", "NOT_REQUESTED"}


def test_optional_sensitivity_step_can_be_skipped(tmp_path):
    _, plan, _ = approved_plan(tmp_path)
    obs = skipped_observation(plan, "optional_sensitivity", "run_sensitivity_analysis", "user skipped")
    assert obs.status == "skipped"


def test_execution_observations_written_to_audit_files(tmp_path):
    spec, plan, _ = approved_plan(tmp_path)
    session = create_execution_session(plan)
    obs = observation_for_estimate(plan, estimate_resources(spec, spec.generation.final_resolution_mm).to_dict())
    session.observations.append(obs)
    audit = write_plan_execution_audit(tmp_path / "session", execution_session=session, step_executions=[], validation_gates=[], next_actions=[])
    assert (audit / "plan_execution_session.json").exists()
    assert (audit / "plan_observations.json").exists()
    assert "estimate_resources" in (audit / "plan_observations.json").read_text(encoding="utf-8")


def test_report_includes_plan_execution_summary(tmp_path):
    spec, plan, _ = approved_plan(tmp_path)
    result = generate_porous_stl(spec, profile=GenerationProfile.PREVIEW)
    session = create_execution_session(plan)
    obs = observation_for_run(plan, {"profile": "preview", "run_id": result.run_id, "run_dir": str(result.run_dir), "validation_report_path": str(result.run_dir / "validation_report.json"), "validation_passed": result.validation_passed})
    session.observations.append(obs)
    write_plan_execution_audit(result.run_dir, execution_session=session, step_executions=[], validation_gates=[], next_actions=[])
    report = generate_html_report(result.run_dir)
    text = report.read_text(encoding="utf-8")
    assert "Agentic Plan Execution Evidence" in text
    assert plan.plan_id in text


def test_run_history_records_plan_step_execution_metadata(tmp_path):
    spec, plan, _ = approved_plan(tmp_path)
    result = generate_porous_stl(spec, profile=GenerationProfile.PREVIEW)
    (result.run_dir / "workflow_metadata.json").write_text(json.dumps({"application_mode": "agentic_design", "strategy_plan_id": plan.plan_id}), encoding="utf-8")
    session = create_execution_session(plan)
    session.completed_steps.append("step_1")
    write_plan_execution_audit(result.run_dir, execution_session=session, step_executions=[], validation_gates=[], next_actions=[])
    store = RunHistoryStore(tmp_path / "history.sqlite")
    record = store.upsert_from_run_dir(result.run_dir)
    assert record is not None
    assert record.mode == "agentic_plan_step_execution"
    assert record.plan_id == plan.plan_id
