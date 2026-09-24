"""Deterministic STL generation service."""

from __future__ import annotations

import csv
import json
import logging
import time
import tracemalloc
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from porous_designer.blackboard.persistence import persist_blackboard, save_environment
from porous_designer.blackboard.state import Blackboard
from porous_designer.blackboard.state_machine import StateMachine
from porous_designer.domain.enums import ExportFormat, FeasibilityStatus, RunStatus
from porous_designer.domain.specification import DesignSpecification
from porous_designer.exporters.stl_exporter import export_stl
from porous_designer.generators.registry import get_generator
from porous_designer.geometry.connectivity import analyze_void_connectivity
from porous_designer.geometry.domains import build_domain_grid, domain_volume
from porous_designer.geometry.mesh import mesh_porosity, solid_grid_to_mesh
from porous_designer.paths import default_config_path
from porous_designer.geometry.voxel import (
    remove_small_solid_components,
    void_grid,
    voxel_porosity,
)
from porous_designer.services.mesh_optimization import (
    MeshOptimizationResult,
    OptimizationProfile,
    OptimizationThresholds,
    optimize_and_validate_mesh,
)
from porous_designer.services.resource_estimation import ResourceEstimate, estimate_resources
from porous_designer.services.validation_service import ValidationConfig, run_validation
from porous_designer.tuning.porosity_solver import TuningResult, bisection_solve


class GenerationProfile(str, Enum):
    PREVIEW = "preview"
    FINAL = "final"
    REFERENCE = "reference"


@dataclass
class TimingBreakdown:
    tuning_s: float = 0.0
    voxel_generation_s: float = 0.0
    marching_cubes_s: float = 0.0
    validation_s: float = 0.0
    export_s: float = 0.0
    total_s: float = 0.0


@dataclass
class GenerationResult:
    success: bool
    run_id: str
    run_dir: Path
    profile: GenerationProfile
    lattice_spacing_mm: float
    tuning_grid_porosity: float
    final_voxel_porosity: float
    final_mesh_porosity: float
    triangle_count: int
    solid_components: int
    watertight: bool
    stl_path: Path | None
    stl_sha256: str | None
    tuning: TuningResult | None
    timing: TimingBreakdown
    peak_memory_mb: float
    validation_passed: bool
    messages: list[str] = field(default_factory=list)
    connectivity: dict[str, Any] = field(default_factory=dict)
    resource_estimate: ResourceEstimate | None = None
    optimization: MeshOptimizationResult | None = None


def load_app_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path is not None else default_config_path()
    if not p.exists():
        logging.getLogger(__name__).warning("Configuration file not found at %s; using built-in defaults.", p)
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _resolution_for_profile(spec: DesignSpecification, profile: GenerationProfile) -> float:
    if profile == GenerationProfile.PREVIEW:
        return spec.generation.preview_resolution_mm
    if profile == GenerationProfile.REFERENCE:
        return getattr(spec.generation, "reference_resolution_mm", spec.generation.final_resolution_mm)
    return spec.generation.final_resolution_mm


def _tuning_voxel_mm(spec: DesignSpecification, final_voxel_mm: float) -> float:
    box = spec.domain.dimensions_mm
    coarse = min(box) / 80.0
    return max(final_voxel_mm, coarse)


def generate_porous_stl(
    spec: DesignSpecification,
    *,
    profile: GenerationProfile = GenerationProfile.FINAL,
    optimization_profile: OptimizationProfile = OptimizationProfile.NONE,
    run_dir: Path | None = None,
    blackboard: Blackboard | None = None,
    config: dict[str, Any] | None = None,
) -> GenerationResult:
    """End-to-end deterministic STL pipeline for registered generators.

    The caller's specification is never modified; the tuned control parameter
    is recorded on a private copy that is saved as ``approved_specification.yaml``.
    """
    spec = spec.model_copy(deep=True)
    generator = get_generator(spec.structure.family)
    generator.validate_specification(spec)
    if spec.domain.shape not in generator.supported_domains():
        raise ValueError(f"{spec.structure.family.value} does not support {spec.domain.shape.value}")

    config = config or load_app_config()
    val_cfg = ValidationConfig(
        dimension_tolerance_mm=config.get("validation", {}).get("dimension_tolerance_mm", 0.05),
        porosity_tolerance=config.get("validation", {}).get("porosity_tolerance_default", 0.02),
        max_porosity_method_disagreement=config.get("validation", {}).get(
            "max_porosity_method_disagreement", 0.03
        ),
        porosity_disagreement_policy=config.get("validation", {}).get(
            "porosity_disagreement_policy", "fail"
        ),
    )

    bb = blackboard or Blackboard(raw_request=spec.source_text)
    sm = StateMachine(bb)
    if bb.status == RunStatus.CREATED:
        sm.transition(RunStatus.PARSING, "Structured specification loaded")
        bb.set_parsed_spec(spec)
        sm.transition(RunStatus.NEEDS_USER_REVIEW, "Specification ready for review")
        sm.transition(RunStatus.SPECIFICATION_APPROVED, "CLI auto-approve")
        bb.set_approved_spec(spec)
        sm.transition(RunStatus.FEASIBILITY_CHECKING, "Deterministic feasibility gate")

    run_dir = run_dir or Path(spec.export.output_directory) / bb.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    geom_dir = run_dir / "geometry"
    geom_dir.mkdir(exist_ok=True)

    messages: list[str] = []
    if ExportFormat.STEP in spec.export.formats:
        messages.append(
            "STEP export is disabled in Phase 2B (known failing fixture: negative B-Rep volume). "
            "Generating STL only."
        )

    final_voxel = _resolution_for_profile(spec, profile)
    tune_voxel = _tuning_voxel_mm(spec, final_voxel)
    target_porosity = spec.targets.porosity_target.target
    porosity_tol = spec.targets.porosity_target.tolerance or val_cfg.porosity_tolerance
    resources_cfg = config.get("resources", {})
    resource_estimate = estimate_resources(
        spec,
        final_voxel,
        warning_memory_fraction=resources_cfg.get("warning_memory_fraction", 0.50),
        maximum_memory_fraction=resources_cfg.get("maximum_memory_fraction", 0.75),
    )
    bb.feasibility = None
    bb.geometry_metrics["resource_estimate"] = resource_estimate.to_dict()
    if resource_estimate.status == FeasibilityStatus.INFEASIBLE:
        sm.transition(RunStatus.INFEASIBLE, resource_estimate.message)
        persist_blackboard(bb, spec.export.output_directory)
        return GenerationResult(
            success=False,
            run_id=bb.run_id,
            run_dir=run_dir,
            profile=profile,
            lattice_spacing_mm=0.0,
            tuning_grid_porosity=0.0,
            final_voxel_porosity=0.0,
            final_mesh_porosity=0.0,
            triangle_count=0,
            solid_components=0,
            watertight=False,
            stl_path=None,
            stl_sha256=None,
            tuning=None,
            timing=TimingBreakdown(),
            peak_memory_mb=0.0,
            validation_passed=False,
            messages=messages + [resource_estimate.message],
            resource_estimate=resource_estimate,
        )
    if resource_estimate.status == FeasibilityStatus.CONDITIONALLY_FEASIBLE:
        messages.append(resource_estimate.message)

    timing = TimingBreakdown()
    tracemalloc.start()
    t_total = time.perf_counter()

    # --- tuning ---
    sm.transition(RunStatus.PREVIEW_GENERATING if profile == GenerationProfile.PREVIEW else RunStatus.FINAL_GENERATING)
    t0 = time.perf_counter()

    tune_domain = build_domain_grid(spec.domain, tune_voxel)

    def eval_porosity(parameter: float) -> float:
        field = generator.generate_voxels(spec, tune_domain, parameter)
        return voxel_porosity(field.solid_grid, tune_domain.mask)

    param_lo, param_hi = generator.default_search_interval(spec)
    tuning = bisection_solve(
        target_porosity,
        eval_porosity,
        param_lo,
        param_hi,
        decreasing=generator.monotonic_decreasing,
        tolerance=porosity_tol,
        max_iterations=40,
    )
    timing.tuning_s = time.perf_counter() - t0

    if not tuning.reachable:
        sm.transition(RunStatus.INFEASIBLE, tuning.message)
        persist_blackboard(bb, spec.export.output_directory)
        return GenerationResult(
            success=False,
            run_id=bb.run_id,
            run_dir=run_dir,
            profile=profile,
            lattice_spacing_mm=tuning.parameter_mm,
            tuning_grid_porosity=tuning.estimated_porosity,
            final_voxel_porosity=0.0,
            final_mesh_porosity=0.0,
            triangle_count=0,
            solid_components=0,
            watertight=False,
            stl_path=None,
            stl_sha256=None,
            tuning=tuning,
            timing=timing,
            peak_memory_mb=0.0,
            validation_passed=False,
            messages=messages + [tuning.message],
        )

    control_parameter = tuning.parameter_mm
    if spec.structure.family.is_sphere_lattice:
        spec.structure.lattice_spacing_mm = control_parameter
    else:
        spec.structure.tpms_level_set = control_parameter

    # --- final voxel grid ---
    t0 = time.perf_counter()
    final_domain = build_domain_grid(spec.domain, final_voxel)
    generated = generator.generate_voxels(spec, final_domain, control_parameter)
    solid_grid = generated.solid_grid
    cleanup_cfg = config.get("cleanup", {})
    solid_grid, cleanup_report = remove_small_solid_components(
        solid_grid,
        min_voxels=int(config.get("validation", {}).get("minimum_solid_component_voxels", 8)),
        voxel_mm=final_voxel,
        domain_mask=final_domain.mask,
        max_removed_solid_fraction=cleanup_cfg.get("max_removed_solid_fraction", 1e-5),
        max_removed_component_voxels=cleanup_cfg.get("max_removed_component_voxels"),
        reject_boundary_touching=cleanup_cfg.get("reject_boundary_touching", False),
    )
    if not cleanup_report.accepted:
        messages.append(f"cleanup rejected: {cleanup_report.reason}")
    final_vox_por = voxel_porosity(solid_grid, final_domain.mask)
    void = void_grid(solid_grid)
    connectivity = analyze_void_connectivity(void, final_domain.mask)
    timing.voxel_generation_s = time.perf_counter() - t0

    # --- mesh ---
    t0 = time.perf_counter()
    mesh_result = solid_grid_to_mesh(solid_grid, final_voxel)
    timing.marching_cubes_s = time.perf_counter() - t0
    domain_vol = domain_volume(spec.domain)
    mesh_por = mesh_porosity(mesh_result.volume_mm3, domain_vol)

    # --- validation ---
    t0 = time.perf_counter()
    sm.transition(RunStatus.VALIDATING)
    report = run_validation(spec, mesh_result.mesh, solid_grid, final_voxel, connectivity, final_domain.mask, val_cfg)
    bb.set_validation_report(report)
    timing.validation_s = time.perf_counter() - t0

    # --- export ---
    t0 = time.perf_counter()
    if profile == GenerationProfile.PREVIEW:
        stl_name = spec.export.output_name + ".preview.stl"
    elif profile == GenerationProfile.REFERENCE:
        stl_name = spec.export.output_name + "_reference.stl"
    else:
        stl_name = spec.export.output_name + "_master.stl"
    stl_path = geom_dir / stl_name
    export_result = export_stl(mesh_result.mesh, stl_path)
    optimization_result = None
    optimization_export = None
    if profile == GenerationProfile.FINAL:
        opt_cfg = config.get("optimization", {})
        thresholds = OptimizationThresholds(
            max_porosity_change=opt_cfg.get("max_porosity_change", 0.005),
            max_volume_change_fraction=opt_cfg.get("max_volume_change_fraction", 0.005),
            max_bbox_change_mm=opt_cfg.get("max_bounding_box_change_mm", 0.02),
            max_surface_deviation_mm=opt_cfg.get("max_surface_deviation_mm", final_voxel),
            sample_count=opt_cfg.get("surface_sample_count", 2048),
        )
        optimized_path = geom_dir / f"{spec.export.output_name}_optimized.stl"
        optimization_result, optimization_export = optimize_and_validate_mesh(
            mesh_result.mesh,
            master_path=stl_path,
            optimized_path=optimized_path,
            domain_volume_mm3=domain_vol,
            profile=optimization_profile,
            thresholds=thresholds,
        )
    timing.export_s = time.perf_counter() - t0

    timing.total_s = time.perf_counter() - t_total
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_mb = peak / (1024 * 1024)

    # --- provenance ---
    _write_tuning_history(run_dir / "tuning_history.csv", tuning)
    _write_timing(run_dir / "timing.json", timing, peak_mb)
    spec.save_yaml(run_dir / "approved_specification.yaml")
    bb.geometry_metrics = {
        "control_parameter": control_parameter,
        "control_parameter_name": generator.control_parameter,
        "lattice_spacing_mm": spec.structure.lattice_spacing_mm,
        "tpms_level_set": spec.structure.tpms_level_set,
        "tuning_grid_porosity": tuning.estimated_porosity,
        "tuning_voxel_mm": tune_voxel,
        "final_voxel_porosity": final_vox_por,
        "final_mesh_porosity": mesh_por,
        "final_voxel_mm": final_voxel,
        "cleanup": cleanup_report.__dict__,
        "resource_estimate": resource_estimate.to_dict(),
        "generator": generator.describe_parameters(),
        "generator_metrics": generated.generator_metrics,
    }
    bb.mesh_metrics = {
        "triangle_count": mesh_result.faces,
        "watertight": mesh_result.watertight,
        "volume_mm3": mesh_result.volume_mm3,
    }
    bb.connectivity_metrics = connectivity.__dict__
    bb.export_results = {
        "stl": str((optimization_result.recommended_path if optimization_result else export_result.path)),
        "master_stl": str(export_result.path),
        "optimized_stl": str(optimization_export.path) if optimization_export else None,
        "sha256": export_result.sha256,
        "optimized_sha256": optimization_export.sha256 if optimization_export else None,
        "step": "disabled_phase_2a",
    }
    bb.artifacts["stl"] = bb.export_results["stl"]
    bb.artifacts["master_stl"] = str(export_result.path)
    if optimization_export:
        bb.artifacts["optimized_stl"] = str(optimization_export.path)
    if optimization_result:
        bb.mesh_metrics["optimization"] = optimization_result.to_dict()

    checksums = {
        "stl_sha256": export_result.sha256,
        "optimized_stl_sha256": optimization_export.sha256 if optimization_export else None,
        "recommended_stl": bb.export_results["stl"],
        "step_status": "disabled_phase_2b",
        "legacy_federica_step_fixture": {
            "validation_status": "FAILED",
            "reason": "negative B-Rep volume on gmsh reimport; bbox extends outside nominal domain",
        },
    }
    (run_dir / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    (run_dir / "validation_report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    final_acceptance_profile = profile == GenerationProfile.FINAL
    passed = tuning.converged and (
        (report.overall_status.value == "pass" and cleanup_report.accepted)
        if final_acceptance_profile
        else True
    )
    if passed:
        sm.transition(RunStatus.PASSED, "Validation passed")
        sm.transition(RunStatus.EXPORTED, "STL exported")
    else:
        sm.transition(RunStatus.FAILED, "Validation failed")
    save_environment(bb, run_dir)
    persist_blackboard(bb, spec.export.output_directory)

    solid_comp = connectivity.solid_component_count

    return GenerationResult(
        success=passed,
        run_id=bb.run_id,
        run_dir=run_dir,
        profile=profile,
        lattice_spacing_mm=control_parameter,
        tuning_grid_porosity=tuning.estimated_porosity,
        final_voxel_porosity=final_vox_por,
        final_mesh_porosity=mesh_por,
        triangle_count=mesh_result.faces,
        solid_components=solid_comp,
        watertight=mesh_result.watertight,
        stl_path=Path(bb.export_results["stl"]),
        stl_sha256=optimization_export.sha256 if optimization_export else export_result.sha256,
        tuning=tuning,
        timing=timing,
        peak_memory_mb=peak_mb,
        validation_passed=passed,
        messages=messages,
        connectivity=connectivity.__dict__,
        resource_estimate=resource_estimate,
        optimization=optimization_result,
    )


def generate_sphere_lattice_stl(
    spec: DesignSpecification,
    *,
    profile: GenerationProfile = GenerationProfile.FINAL,
    run_dir: Path | None = None,
    blackboard: Blackboard | None = None,
    config: dict[str, Any] | None = None,
) -> GenerationResult:
    """Backward-compatible Phase 2A entry point."""
    return generate_porous_stl(
        spec,
        profile=profile,
        run_dir=run_dir,
        blackboard=blackboard,
        config=config,
    )


def _write_tuning_history(path: Path, tuning: TuningResult) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["iteration", "parameter_mm", "estimated_porosity", "residual", "runtime_s"],
        )
        writer.writeheader()
        for it in tuning.iterations:
            writer.writerow(
                {
                    "iteration": it.iteration,
                    "parameter_mm": it.parameter_mm,
                    "estimated_porosity": it.estimated_porosity,
                    "residual": it.residual,
                    "runtime_s": it.runtime_s,
                }
            )


def _write_timing(path: Path, timing: TimingBreakdown, peak_mb: float) -> None:
    path.write_text(
        json.dumps(
            {
                "tuning_s": timing.tuning_s,
                "voxel_generation_s": timing.voxel_generation_s,
                "marching_cubes_s": timing.marching_cubes_s,
                "validation_s": timing.validation_s,
                "export_s": timing.export_s,
                "total_s": timing.total_s,
                "peak_memory_mb": peak_mb,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
