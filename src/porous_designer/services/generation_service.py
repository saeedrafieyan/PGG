"""Deterministic STL generation service (Phase 2A)."""

from __future__ import annotations

import csv
import json
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
from porous_designer.domain.enums import ExportFormat, RunStatus, StructureFamily
from porous_designer.domain.specification import DesignSpecification
from porous_designer.exporters.stl_exporter import export_stl
from porous_designer.generators.sphere_lattices import LatticeType
from porous_designer.geometry.connectivity import analyze_void_connectivity
from porous_designer.geometry.mesh import mesh_domain_volume, mesh_porosity, solid_grid_to_mesh
from porous_designer.geometry.voxel import (
    remove_small_solid_components,
    sphere_solid_grid,
    void_grid,
    voxel_porosity,
)
from porous_designer.services.validation_service import ValidationConfig, run_validation
from porous_designer.tuning.porosity_solver import TuningResult, bisection_solve


class GenerationProfile(str, Enum):
    PREVIEW = "preview"
    FINAL = "final"


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


def load_app_config(path: str | Path = "configs/default.yaml") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _resolution_for_profile(spec: DesignSpecification, profile: GenerationProfile) -> float:
    if profile == GenerationProfile.PREVIEW:
        return spec.generation.preview_resolution_mm
    return spec.generation.final_resolution_mm


def _tuning_voxel_mm(spec: DesignSpecification, final_voxel_mm: float) -> float:
    box = spec.domain.dimensions_mm
    coarse = min(box) / 80.0
    return max(final_voxel_mm, coarse)


def generate_sphere_lattice_stl(
    spec: DesignSpecification,
    *,
    profile: GenerationProfile = GenerationProfile.FINAL,
    run_dir: Path | None = None,
    blackboard: Blackboard | None = None,
    config: dict[str, Any] | None = None,
) -> GenerationResult:
    """End-to-end deterministic STL pipeline for sphere-pore box domains."""
    if not spec.structure.family.is_sphere_lattice:
        raise ValueError(f"Phase 2A supports sphere lattices only, got {spec.structure.family}")
    if spec.domain.shape.value != "box":
        raise ValueError("Phase 2A supports box domains only.")

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
        sm.transition(RunStatus.FEASIBILITY_CHECKING, "Phase 2A deterministic feasibility gate")

    run_dir = run_dir or Path(spec.export.output_directory) / bb.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    geom_dir = run_dir / "geometry"
    geom_dir.mkdir(exist_ok=True)

    messages: list[str] = []
    if ExportFormat.STEP in spec.export.formats:
        messages.append(
            "STEP export is disabled in Phase 2A (known failing fixture: negative B-Rep volume). "
            "Generating STL only."
        )

    box = tuple(spec.domain.dimensions_mm)
    pore_d = spec.structure.pore_diameter_mm
    assert pore_d is not None
    radius = pore_d / 2.0
    lattice = LatticeType.from_family(spec.structure.family)
    final_voxel = _resolution_for_profile(spec, profile)
    tune_voxel = _tuning_voxel_mm(spec, final_voxel)
    target_porosity = spec.targets.porosity_target.target
    porosity_tol = spec.targets.porosity_target.tolerance or val_cfg.porosity_tolerance

    timing = TimingBreakdown()
    tracemalloc.start()
    t_total = time.perf_counter()

    # --- tuning ---
    sm.transition(RunStatus.PREVIEW_GENERATING if profile == GenerationProfile.PREVIEW else RunStatus.FINAL_GENERATING)
    t0 = time.perf_counter()

    def eval_porosity(spacing: float) -> float:
        grid = sphere_solid_grid(box, tune_voxel, radius, spacing, lattice)
        return voxel_porosity(grid)

    spacing_lo = 0.5 * pore_d
    spacing_hi = 3.0 * pore_d
    tuning = bisection_solve(
        target_porosity,
        eval_porosity,
        spacing_lo,
        spacing_hi,
        decreasing=True,
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

    lattice_spacing = tuning.parameter_mm
    spec.structure.lattice_spacing_mm = lattice_spacing

    # --- final voxel grid ---
    t0 = time.perf_counter()
    solid_grid = sphere_solid_grid(box, final_voxel, radius, lattice_spacing, lattice)
    solid_grid, removed_solid_components, removed_solid_voxels = remove_small_solid_components(
        solid_grid,
        min_voxels=int(config.get("validation", {}).get("minimum_solid_component_voxels", 8)),
    )
    final_vox_por = voxel_porosity(solid_grid)
    void = void_grid(solid_grid)
    connectivity = analyze_void_connectivity(void)
    timing.voxel_generation_s = time.perf_counter() - t0

    # --- mesh ---
    t0 = time.perf_counter()
    mesh_result = solid_grid_to_mesh(solid_grid, final_voxel)
    timing.marching_cubes_s = time.perf_counter() - t0
    domain_vol = mesh_domain_volume(box)
    mesh_por = mesh_porosity(mesh_result.volume_mm3, domain_vol)

    # --- validation ---
    t0 = time.perf_counter()
    sm.transition(RunStatus.VALIDATING)
    report = run_validation(spec, mesh_result.mesh, solid_grid, final_voxel, connectivity, val_cfg)
    bb.set_validation_report(report)
    timing.validation_s = time.perf_counter() - t0

    # --- export ---
    t0 = time.perf_counter()
    stl_name = spec.export.output_name + (".preview.stl" if profile == GenerationProfile.PREVIEW else ".stl")
    stl_path = geom_dir / stl_name
    export_result = export_stl(mesh_result.mesh, stl_path)
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
        "lattice_spacing_mm": lattice_spacing,
        "tuning_grid_porosity": tuning.estimated_porosity,
        "tuning_voxel_mm": tune_voxel,
        "final_voxel_porosity": final_vox_por,
        "final_mesh_porosity": mesh_por,
        "final_voxel_mm": final_voxel,
        "removed_solid_components": removed_solid_components,
        "removed_solid_voxels": removed_solid_voxels,
    }
    bb.mesh_metrics = {
        "triangle_count": mesh_result.faces,
        "watertight": mesh_result.watertight,
        "volume_mm3": mesh_result.volume_mm3,
    }
    bb.connectivity_metrics = connectivity.__dict__
    bb.export_results = {
        "stl": str(export_result.path),
        "sha256": export_result.sha256,
        "step": "disabled_phase_2a",
    }
    bb.artifacts["stl"] = str(export_result.path)

    checksums = {
        "stl_sha256": export_result.sha256,
        "step_status": "disabled_phase_2a",
        "legacy_federica_step_fixture": {
            "validation_status": "FAILED",
            "reason": "negative B-Rep volume on gmsh reimport; bbox extends outside nominal domain",
        },
    }
    (run_dir / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    (run_dir / "validation_report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    passed = report.overall_status.value == "pass" and tuning.converged
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
        lattice_spacing_mm=lattice_spacing,
        tuning_grid_porosity=tuning.estimated_porosity,
        final_voxel_porosity=final_vox_por,
        final_mesh_porosity=mesh_por,
        triangle_count=mesh_result.faces,
        solid_components=solid_comp,
        watertight=mesh_result.watertight,
        stl_path=export_result.path,
        stl_sha256=export_result.sha256,
        tuning=tuning,
        timing=timing,
        peak_memory_mb=peak_mb,
        validation_passed=passed,
        messages=messages,
        connectivity=connectivity.__dict__,
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
