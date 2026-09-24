"""Deterministic generation service: implicit field -> mesh -> validation -> STL/3MF/STEP."""

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
import numpy as np

from porous_designer.domain.enums import DomainShape, ExportFormat, FeasibilityStatus, RunStatus, SkinMode
from porous_designer.domain.specification import DesignSpecification
from porous_designer.exporters.step_exporter import export_faceted_step
from porous_designer.exporters.stl_exporter import export_stl
from porous_designer.exporters.threemf_exporter import export_3mf
from porous_designer.generators.registry import get_generator
from porous_designer.geometry.connectivity import analyze_void_connectivity
from porous_designer.geometry.domains import domain_volume
from porous_designer.geometry.mesh import load_stl, mesh_porosity
from porous_designer.implicit.domain_sdf import load_domain_mesh
from porous_designer.implicit.field import FieldModel
from porous_designer.implicit.meshing import field_to_mesh
from porous_designer.paths import default_config_path
from porous_designer.geometry.voxel import (
    remove_detached_fragments,
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
    control_parameter_name: str = ""
    target_porosity: float | None = None
    threemf_path: Path | None = None
    step_path: Path | None = None
    export_status: dict[str, Any] = field(default_factory=dict)


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
    from porous_designer.geometry.domains import domain_bounds

    coarse = min(domain_bounds(spec.domain)) / 80.0
    return max(final_voxel_mm, coarse)


def _failed_result(bb, run_dir, profile, messages, *, tuning=None, timing=None, resource_estimate=None, control=0.0) -> GenerationResult:
    return GenerationResult(
        success=False,
        run_id=bb.run_id,
        run_dir=run_dir,
        profile=profile,
        lattice_spacing_mm=control,
        tuning_grid_porosity=tuning.estimated_porosity if tuning else 0.0,
        final_voxel_porosity=0.0,
        final_mesh_porosity=0.0,
        triangle_count=0,
        solid_components=0,
        watertight=False,
        stl_path=None,
        stl_sha256=None,
        tuning=tuning,
        timing=timing or TimingBreakdown(),
        peak_memory_mb=0.0,
        validation_passed=False,
        messages=messages,
        resource_estimate=resource_estimate,
    )


def _tune(model: FieldModel, target: float, tolerance: float) -> TuningResult:
    """Tune the control parameter on ``model``'s grid (or report a fixed one)."""
    problem = model.control_problem()
    if problem.fixed is not None:
        porosity = model.porosity(problem.fixed)
        return TuningResult(
            parameter_mm=float(problem.fixed),
            estimated_porosity=porosity,
            converged=True,
            reachable=True,
            monotonic=True,
            message="Geometry fixed by the specification; porosity is a result, not a target.",
        )
    lo, hi = model.tight_interval(target) or (problem.lo, problem.hi)
    tuning = bisection_solve(target, model.porosity, lo, hi, decreasing=problem.decreasing, tolerance=tolerance, max_iterations=60)
    if not tuning.reachable and (lo, hi) != (problem.lo, problem.hi):
        tuning = bisection_solve(target, model.porosity, problem.lo, problem.hi, decreasing=problem.decreasing, tolerance=tolerance, max_iterations=60)
    return tuning


@dataclass
class _Realised:
    control: float
    generated: Any
    solid_core: np.ndarray
    cleanup_report: Any
    fragment_report: Any
    voxel_porosity: float
    mesh_result: Any
    mesh_porosity: float
    field_s: float
    mesh_s: float


def _smallest_cell_mm(spec: DesignSpecification) -> float | None:
    structure = spec.structure
    if structure.unit_cell_size_mm is None:
        return None
    if structure.cell_size_grading is not None:
        return min(structure.cell_size_grading.start, structure.cell_size_grading.end)
    return structure.unit_cell_size_mm


def _wall_voxels(spec: DesignSpecification, control_name: str, control: float, voxel_mm: float) -> float | None:
    """Thinnest wall / strut in voxels, when the control parameter sets it."""
    if spec.targets.porosity_grading is not None:
        return None  # thickness varies through the part
    cell = _smallest_cell_mm(spec)
    if control_name == "tau" and cell is not None:
        return float(control * cell / voxel_mm)
    if spec.structure.fixed_thickness and spec.structure.wall_thickness_mm is not None:
        return float(spec.structure.wall_thickness_mm / voxel_mm)
    return None


def _open_axes(spec: DesignSpecification) -> tuple[str, ...]:
    """Directions in which pores can reach the outside, given the skin."""
    if not spec.domain.skin_thickness_mm:
        return ("x", "y", "z")
    if spec.domain.skin_mode == SkinMode.LATERAL:
        return ("z",)
    return ()


def _crop_core(model: FieldModel, array: np.ndarray) -> np.ndarray:
    """Voxels whose centres lie inside the domain's bounding box.

    Drops the outer margin and any partial layer beyond the bounds, so the
    core's faces are the domain's faces (needed for percolation checks).
    """
    m = model.grid.margin
    counts = [max(1, int(round(b / model.grid.voxel_mm))) for b in model.grid.bounds_mm]
    return array[m : m + counts[0], m : m + counts[1], m : m + counts[2]]


def generate_porous_stl(
    spec: DesignSpecification,
    *,
    profile: GenerationProfile = GenerationProfile.FINAL,
    optimization_profile: OptimizationProfile = OptimizationProfile.NONE,
    run_dir: Path | None = None,
    blackboard: Blackboard | None = None,
    config: dict[str, Any] | None = None,
) -> GenerationResult:
    """End-to-end deterministic pipeline: tune, build field, mesh, validate, export.

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
        max_porosity_method_disagreement=config.get("validation", {}).get("max_porosity_method_disagreement", 0.03),
        porosity_disagreement_policy=config.get("validation", {}).get("porosity_disagreement_policy", "fail"),
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
    final_voxel = _resolution_for_profile(spec, profile)
    tune_voxel = _tuning_voxel_mm(spec, final_voxel)
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
        return _failed_result(bb, run_dir, profile, messages + [resource_estimate.message], resource_estimate=resource_estimate)
    if resource_estimate.status == FeasibilityStatus.CONDITIONALLY_FEASIBLE:
        messages.append(resource_estimate.message)

    timing = TimingBreakdown()
    owns_trace = not tracemalloc.is_tracing()
    if owns_trace:
        tracemalloc.start()
    t_total = time.perf_counter()

    # --- tuning on a coarse grid ---
    sm.transition(RunStatus.PREVIEW_GENERATING if profile == GenerationProfile.PREVIEW else RunStatus.FINAL_GENERATING)
    t0 = time.perf_counter()
    domain_mesh = load_domain_mesh(spec.domain) if spec.domain.shape == DomainShape.MESH else None
    try:
        tune_model = FieldModel.build(spec, tune_voxel, mesh=domain_mesh)
    except ValueError as exc:
        if owns_trace:
            tracemalloc.stop()
        sm.transition(RunStatus.INFEASIBLE, str(exc))
        persist_blackboard(bb, spec.export.output_directory)
        return _failed_result(bb, run_dir, profile, messages + [str(exc)], resource_estimate=resource_estimate)
    problem = tune_model.control_problem()
    target_porosity = float(problem.target_porosity)
    bisection_tol = min(porosity_tol / 4.0, 0.003)
    tuning = _tune(tune_model, target_porosity, bisection_tol)
    timing.tuning_s = time.perf_counter() - t0

    min_wall_voxels = float(config.get("generation", {}).get("minimum_wall_voxels", 0.75))
    if tuning.reachable and problem.fixed is None and problem.name == "tau":
        wall = _wall_voxels(spec, problem.name, tuning.parameter_mm, final_voxel)
        if wall is not None and wall < min_wall_voxels:
            tuning.reachable = False
            tuning.converged = False
            tuning.message = (
                f"Reaching {target_porosity:.1%} porosity needs walls/struts of {wall * final_voxel:.4f} mm, "
                f"thinner than {min_wall_voxels:g} voxel ({min_wall_voxels * final_voxel:.4f} mm) at this resolution. "
                "Lower the porosity target, enlarge the unit cell, or refine the resolution."
            )
    if not tuning.reachable:
        if owns_trace:
            tracemalloc.stop()
        achievable = tune_model.calibration.porosity_range if tune_model.calibration is not None else None
        in_range = achievable is not None and achievable[0] <= target_porosity <= achievable[1]
        detail = f" Achievable porosity for this family is about {achievable[0]:.0%}-{achievable[1]:.0%}." if achievable and not in_range else ""
        sm.transition(RunStatus.INFEASIBLE, tuning.message)
        persist_blackboard(bb, spec.export.output_directory)
        return _failed_result(bb, run_dir, profile, messages + [tuning.message + detail], tuning=tuning, timing=timing, resource_estimate=resource_estimate, control=tuning.parameter_mm)

    # --- final field ---
    t0 = time.perf_counter()
    final_model = tune_model if abs(tune_voxel - final_voxel) < 1e-12 else FieldModel.build(spec, final_voxel, mesh=domain_mesh)
    control_parameter = tuning.parameter_mm
    refined = None
    if problem.fixed is None and final_model is not tune_model and final_model.kind != "sphere":
        # Implicit fields are cheap to re-evaluate: refine on the final grid so
        # the delivered geometry, not the coarse proxy, meets the target.
        width = 0.05 * (problem.hi - problem.lo)
        lo, hi = max(problem.lo, control_parameter - width), min(problem.hi, control_parameter + width)
        refined = bisection_solve(target_porosity, final_model.porosity, lo, hi, decreasing=problem.decreasing, tolerance=bisection_tol, max_iterations=60)
        if refined.reachable:
            control_parameter = refined.parameter_mm
    cleanup_cfg = config.get("cleanup", {})
    min_island_voxels = int(config.get("validation", {}).get("minimum_solid_component_voxels", 8))
    inside_core = _crop_core(final_model, final_model.inside)
    region_core = _crop_core(final_model, final_model.porous_region)
    domain_vol = domain_volume(spec.domain)

    def realise(control: float) -> _Realised:
        """Field -> cleanup -> mesh for one control value on the final grid."""
        t_field = time.perf_counter()
        generated = generator.generate_field(final_model, control)
        field_grid = generated.field
        assert field_grid is not None
        solid_core = _crop_core(final_model, generated.solid_grid)
        cleaned_core, cleanup_report = remove_small_solid_components(
            solid_core,
            min_voxels=min_island_voxels,
            voxel_mm=final_voxel,
            domain_mask=inside_core,
            max_removed_solid_fraction=cleanup_cfg.get("max_removed_solid_fraction", 1e-5),
            max_removed_component_voxels=cleanup_cfg.get("max_removed_component_voxels"),
            reject_boundary_touching=cleanup_cfg.get("reject_boundary_touching", False),
        )
        # The small-island pass is conservative; when it declines, the fragment
        # pass below (which bounds the removed volume itself) decides instead.
        if not cleanup_report.accepted:
            cleaned_core = solid_core
        cleaned_core, fragment_report = remove_detached_fragments(
            cleaned_core,
            max_removed_solid_fraction=cleanup_cfg.get("max_detached_fragment_fraction", 0.02),
        )
        removed = solid_core & ~cleaned_core
        if removed.any():
            # Removed voxels become void in the field too, so the mesh matches.
            _crop_core(final_model, field_grid)[removed] = np.float32(final_voxel)
        field_s = time.perf_counter() - t_field
        t_mesh = time.perf_counter()
        mesh_result = field_to_mesh(field_grid, final_voxel, origin_mm=final_model.grid.origin_mm)
        mesh_por = mesh_porosity(mesh_result.volume_mm3, domain_vol)
        if final_model.skin is not None:
            mesh_por *= int(inside_core.sum()) / max(int(region_core.sum()), 1)
        return _Realised(
            control=control,
            generated=generated,
            solid_core=cleaned_core,
            cleanup_report=cleanup_report,
            fragment_report=fragment_report,
            voxel_porosity=voxel_porosity(cleaned_core, region_core),
            mesh_result=mesh_result,
            mesh_porosity=mesh_por,
            field_s=field_s,
            mesh_s=time.perf_counter() - t_mesh,
        )

    realised = realise(control_parameter)
    field_seconds, mesh_seconds = realised.field_s, realised.mesh_s
    mesh_corrections: list[dict[str, float]] = []
    if problem.fixed is None and final_model.kind != "sphere":
        # Marching cubes interpolates the field linearly, which thins walls
        # that span only a few voxels. The exported mesh is what gets
        # printed, so it - not the voxel samples - must meet the target: a
        # short secant search on the control parameter closes the gap.
        correction_tol = max(0.25 * porosity_tol, 0.004)
        c_hi = min(problem.hi, control_parameter + 0.01 * (problem.hi - problem.lo))
        c_lo = max(problem.lo, control_parameter - 0.01 * (problem.hi - problem.lo))
        slope = (final_model.porosity(c_hi) - final_model.porosity(c_lo)) / (c_hi - c_lo)
        previous: _Realised | None = None
        start_control = control_parameter
        for _ in range(3):
            error = target_porosity - realised.mesh_porosity
            if abs(error) <= correction_tol or abs(slope) < 1e-9:
                break
            if previous is not None and abs(realised.control - previous.control) > 1e-12:
                secant = (realised.mesh_porosity - previous.mesh_porosity) / (realised.control - previous.control)
                if abs(secant) > 1e-9 and secant * slope > 0:
                    slope = secant
            new_control = float(np.clip(realised.control + error / slope, problem.lo, problem.hi))
            if abs(new_control - realised.control) < 1e-12:
                break
            candidate = realise(new_control)
            field_seconds += candidate.field_s
            mesh_seconds += candidate.mesh_s
            mesh_corrections.append({"control": new_control, "mesh_porosity": candidate.mesh_porosity, "voxel_porosity": candidate.voxel_porosity})
            if abs(target_porosity - candidate.mesh_porosity) >= abs(error):
                break
            previous, realised = realised, candidate
        control_parameter = realised.control
        if abs(control_parameter - start_control) > 0:
            messages.append(
                f"adjusted {problem.name} by {control_parameter - start_control:+.5f} so the exported mesh meets the porosity target "
                f"({len(mesh_corrections)} extra meshing pass(es); thin walls are thinned by marching cubes)"
            )

    placement_offset = None
    if domain_mesh is not None and "age_source_min_mm" in domain_mesh.metadata:
        # Mesh domains keep the coordinates of the source file, so the part
        # overlays the scan or CAD model it was designed to fill.
        placement_offset = [float(v) for v in domain_mesh.metadata["age_source_min_mm"]]
        realised.mesh_result.mesh.apply_translation(placement_offset)
    generated = realised.generated
    solid_core = realised.solid_core
    cleanup_report = realised.cleanup_report
    fragment_report = realised.fragment_report
    mesh_result = realised.mesh_result
    mesh_por = realised.mesh_porosity
    final_vox_por = realised.voxel_porosity
    if not fragment_report.accepted:
        messages.append(f"design is disconnected: {fragment_report.reason}")
    elif fragment_report.removed_component_count:
        messages.append(
            f"removed {fragment_report.removed_component_count} detached fragment(s) "
            f"({fragment_report.removed_solid_fraction:.2%} of the material) left by the domain boundary"
        )
    if final_model.kind == "sphere":
        spec.structure.lattice_spacing_mm = control_parameter
    elif problem.name == "tau":
        spec.structure.wall_thickness_mm = float(control_parameter * spec.structure.unit_cell_size_mm) if spec.structure.cell_size_grading is None else spec.structure.wall_thickness_mm
    elif problem.name == "kappa":
        spec.structure.network_offset_mm = float(control_parameter * spec.structure.unit_cell_size_mm) if spec.structure.cell_size_grading is None else spec.structure.network_offset_mm
    wall_voxels = _wall_voxels(spec, problem.name, control_parameter, final_voxel)
    connectivity = analyze_void_connectivity(void_grid(solid_core), inside_core)
    porosity_profile = final_model.porosity_profile(control_parameter)
    timing.voxel_generation_s = field_seconds
    timing.marching_cubes_s = mesh_seconds

    # --- validation ---
    t0 = time.perf_counter()
    sm.transition(RunStatus.VALIDATING)
    report = run_validation(
        spec,
        mesh_result.mesh,
        solid_core,
        final_voxel,
        connectivity,
        inside_core,
        val_cfg,
        porosity_target=target_porosity,
        porosity_is_target=problem.fixed is None,
        porosity_profile=porosity_profile,
        porous_region_mask=region_core if final_model.skin is not None else None,
        percolation_axes=_open_axes(spec),
        wall_voxels=wall_voxels,
        mesh_authoritative=True,
    )
    bb.set_validation_report(report)
    timing.validation_s = time.perf_counter() - t0

    # --- export ---
    t0 = time.perf_counter()
    if profile == GenerationProfile.PREVIEW:
        stem = spec.export.output_name + ".preview"
    elif profile == GenerationProfile.REFERENCE:
        stem = spec.export.output_name + "_reference"
    else:
        stem = spec.export.output_name + "_master"
    stl_path = geom_dir / f"{stem}.stl"
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
    delivered_mesh = mesh_result.mesh
    if optimization_result is not None and optimization_export is not None and optimization_result.recommended_path == optimization_export.path:
        delivered_mesh = load_stl(optimization_export.path)
    export_status: dict[str, Any] = {"stl": "exported"}
    threemf_result = None
    step_result = None
    if ExportFormat.THREE_MF in spec.export.formats:
        threemf_result = export_3mf(delivered_mesh, geom_dir / f"{stem}.3mf", title=spec.export.output_name)
        export_status["3mf"] = "exported"
    if ExportFormat.STEP in spec.export.formats:
        if profile == GenerationProfile.PREVIEW:
            export_status["step"] = "skipped: STEP is produced for Final runs only"
        else:
            step_result = export_faceted_step(
                delivered_mesh,
                geom_dir / f"{stem}.step",
                max_triangles=spec.generation.step_max_triangles,
                max_deviation_mm=max(final_voxel, val_cfg.dimension_tolerance_mm),
            )
            export_status["step"] = step_result.status
            if step_result.status != "exported":
                messages.append(f"STEP {step_result.status}: {step_result.message}")
    timing.export_s = time.perf_counter() - t0

    timing.total_s = time.perf_counter() - t_total
    _, peak = tracemalloc.get_traced_memory()
    if owns_trace:
        tracemalloc.stop()
    peak_mb = peak / (1024 * 1024)

    # --- provenance ---
    _write_tuning_history(run_dir / "tuning_history.csv", tuning)
    _write_timing(run_dir / "timing.json", timing, peak_mb)
    spec.save_yaml(run_dir / "approved_specification.yaml")
    bb.geometry_metrics = {
        "control_parameter": control_parameter,
        "control_parameter_name": problem.name,
        "control_parameter_units": problem.units,
        "fixed_geometry": problem.fixed is not None,
        "target_porosity": target_porosity,
        "lattice_spacing_mm": spec.structure.lattice_spacing_mm,
        "wall_thickness_mm": spec.structure.wall_thickness_mm,
        "network_offset_mm": spec.structure.network_offset_mm,
        "tuning_grid_porosity": tuning.estimated_porosity,
        "final_grid_refinement": None if refined is None else {"converged": refined.converged, "porosity": refined.estimated_porosity},
        "mesh_porosity_corrections": mesh_corrections,
        "placement_offset_mm": placement_offset,
        "minimum_wall_voxels": wall_voxels,
        "tuning_voxel_mm": tune_voxel,
        "final_voxel_porosity": final_vox_por,
        "final_mesh_porosity": mesh_por,
        "final_voxel_mm": final_voxel,
        "achievable_porosity_range": list(final_model.calibration.porosity_range) if final_model.calibration is not None else None,
        "porosity_profile": porosity_profile,
        "cleanup": cleanup_report.__dict__,
        "detached_fragments": fragment_report.__dict__,
        "resource_estimate": resource_estimate.to_dict(),
        "field_timings_s": {"tuning_grid": tune_model.timings, "final_grid": final_model.timings},
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
        "3mf": str(threemf_result.path) if threemf_result else None,
        "step": str(step_result.path) if step_result and step_result.status == "exported" else None,
        "step_report": step_result.to_dict() if step_result else None,
        "status": export_status,
    }
    bb.artifacts["stl"] = bb.export_results["stl"]
    bb.artifacts["master_stl"] = str(export_result.path)
    if optimization_export:
        bb.artifacts["optimized_stl"] = str(optimization_export.path)
    if threemf_result:
        bb.artifacts["3mf"] = str(threemf_result.path)
    if step_result and step_result.status == "exported":
        bb.artifacts["step"] = str(step_result.path)
    if optimization_result:
        bb.mesh_metrics["optimization"] = optimization_result.to_dict()

    checksums = {
        "stl_sha256": export_result.sha256,
        "optimized_stl_sha256": optimization_export.sha256 if optimization_export else None,
        "3mf_sha256": threemf_result.sha256 if threemf_result else None,
        "recommended_stl": bb.export_results["stl"],
        "step_status": export_status.get("step", "not_requested"),
    }
    (run_dir / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    (run_dir / "validation_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    final_acceptance_profile = profile == GenerationProfile.FINAL
    # Warnings (e.g. resolution-limited voxel/mesh disagreement) are reported
    # but do not reject the part; any failed check does.
    # The coarse tuning grid only brackets the control; the final-grid
    # refinement and mesh correction decide the delivered porosity, which
    # validation then judges. So a reachable target is enough here.
    passed = tuning.reachable and ((report.overall_status.value in ("pass", "warning") and fragment_report.accepted) if final_acceptance_profile else True)
    if passed:
        sm.transition(RunStatus.PASSED, "Validation passed")
        sm.transition(RunStatus.EXPORTED, "Geometry exported")
    else:
        sm.transition(RunStatus.FAILED, "Validation failed")
    save_environment(bb, run_dir)
    persist_blackboard(bb, spec.export.output_directory)

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
        solid_components=connectivity.solid_component_count,
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
        control_parameter_name=problem.name,
        target_porosity=target_porosity,
        threemf_path=threemf_result.path if threemf_result else None,
        step_path=step_result.path if step_result and step_result.status == "exported" else None,
        export_status=export_status,
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
