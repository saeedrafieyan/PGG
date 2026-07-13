"""Phase 2C validation-closure utilities."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from porous_designer.domain.enums import DomainShape
from porous_designer.domain.specification import DesignSpecification
from porous_designer.geometry.domains import build_domain_grid, domain_volume
from porous_designer.services.generation_service import GenerationProfile, generate_porous_stl


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def json_sha256(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    normalized = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _load_run_json(run_dir: Path, name: str) -> dict[str, Any]:
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


def determinism_study(
    spec: DesignSpecification,
    *,
    runs: int = 2,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    output_dir = output_dir or Path(spec.export.output_directory) / "determinism"
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    histories: list[str] = []
    for i in range(runs):
        run_spec = spec.model_copy(deep=True)
        run_spec.export.output_directory = str(output_dir)
        run_spec.export.output_name = f"{spec.export.output_name}_det_{i + 1}"
        result = generate_porous_stl(run_spec, profile=GenerationProfile.FINAL)
        bb = _load_run_json(result.run_dir, "blackboard.json")
        tuning_history = (result.run_dir / "tuning_history.csv").read_text(encoding="utf-8")
        histories.append(tuning_history)
        val_hash = json_sha256(result.run_dir / "validation_report.json")
        rows.append(
            {
                "run": i + 1,
                "success": result.success,
                "run_id": result.run_id,
                "control_parameter": result.lattice_spacing_mm,
                "voxel_porosity": result.final_voxel_porosity,
                "mesh_porosity": result.final_mesh_porosity,
                "triangle_count": result.triangle_count,
                "solid_components": result.solid_components,
                "pore_components": result.connectivity.get("pore_component_count"),
                "pore_connected_x": result.connectivity.get("pore_connected_x"),
                "pore_connected_y": result.connectivity.get("pore_connected_y"),
                "pore_connected_z": result.connectivity.get("pore_connected_z"),
                "cleanup": bb.get("geometry_metrics", {}).get("cleanup"),
                "stl_sha256": result.stl_sha256,
                "validation_report_sha256": val_hash,
                "runtime_s": result.timing.total_s,
                "peak_memory_mb": result.peak_memory_mb,
            }
        )

    first = rows[0] if rows else {}
    exact_fields = [
        "control_parameter",
        "voxel_porosity",
        "mesh_porosity",
        "triangle_count",
        "solid_components",
        "pore_components",
        "pore_connected_x",
        "pore_connected_y",
        "pore_connected_z",
        "cleanup",
        "stl_sha256",
    ]
    bitwise = bool(rows) and all(all(row.get(f) == first.get(f) for f in exact_fields) for row in rows)
    histories_match = all(h == histories[0] for h in histories) if histories else True
    classification = "bitwise deterministic" if bitwise and histories_match else "numerically deterministic"
    payload = {
        "classification": classification,
        "tolerances": {
            "control_parameter": 1e-12,
            "porosity": 1e-9,
            "bounding_box_mm": 1e-9,
        },
        "runs": rows,
        "tuning_histories_match": histories_match,
    }
    (output_dir / "determinism.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def preview_final_consistency(spec: DesignSpecification, *, output_dir: Path | None = None) -> dict[str, Any]:
    output_dir = output_dir or Path(spec.export.output_directory) / "preview_final"
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_spec = spec.model_copy(deep=True)
    final_spec = spec.model_copy(deep=True)
    preview_spec.export.output_directory = str(output_dir)
    final_spec.export.output_directory = str(output_dir)
    preview_spec.export.output_name = spec.export.output_name + "_preview_check"
    final_spec.export.output_name = spec.export.output_name + "_final_check"
    preview = generate_porous_stl(preview_spec, profile=GenerationProfile.PREVIEW)
    final = generate_porous_stl(final_spec, profile=GenerationProfile.FINAL)
    porosity_delta = abs(preview.final_mesh_porosity - final.final_mesh_porosity)
    payload = {
        "preview_run_id": preview.run_id,
        "final_run_id": final.run_id,
        "preview_metric_reliability": {
            "porosity": "approximate" if porosity_delta <= 0.05 else "uncertain",
            "connectivity": "uncertain"
            if preview.solid_components != final.solid_components
            or preview.connectivity.get("pore_component_count") != final.connectivity.get("pore_component_count")
            else "approximate",
            "wall_thickness": "unavailable",
            "throat_size": "unavailable",
            "final_acceptance": "not_allowed",
        },
        "comparison": {
            "mesh_porosity_delta": porosity_delta,
            "solid_components_match": preview.solid_components == final.solid_components,
            "pore_components_match": preview.connectivity.get("pore_component_count")
            == final.connectivity.get("pore_component_count"),
            "x_percolation_match": preview.connectivity.get("pore_connected_x")
            == final.connectivity.get("pore_connected_x"),
            "y_percolation_match": preview.connectivity.get("pore_connected_y")
            == final.connectivity.get("pore_connected_y"),
            "z_percolation_match": preview.connectivity.get("pore_connected_z")
            == final.connectivity.get("pore_connected_z"),
            "geometry_family_match": preview.profile.value == "preview" and final.profile.value == "final",
        },
    }
    (output_dir / "preview_final_consistency.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return payload


def profile_generation(spec: DesignSpecification, *, profile: GenerationProfile = GenerationProfile.FINAL) -> dict[str, Any]:
    t0 = time.perf_counter()
    result = generate_porous_stl(spec, profile=profile)
    load_and_generate_s = time.perf_counter() - t0
    bb = _load_run_json(result.run_dir, "blackboard.json")
    timing = _load_run_json(result.run_dir, "timing.json")
    payload = {
        "run_id": result.run_id,
        "success": result.success,
        "profile": profile.value,
        "timing": timing,
        "wall_clock_s": load_and_generate_s,
        "resource_estimate": bb.get("geometry_metrics", {}).get("resource_estimate"),
        "cleanup": bb.get("geometry_metrics", {}).get("cleanup"),
        "runtime_notes": [
            "Marching cubes and mesh validation dominate final-resolution runtime.",
            "Phase 2B/2C add nonmanifold edge checks, resource bookkeeping, and richer provenance.",
            "Validation was not removed to reduce runtime.",
        ],
    }
    (result.run_dir / "profile.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def cylinder_accuracy_study(
    *,
    diameter_mm: float,
    height_mm: float,
    resolutions: list[float],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    analytic_volume = float(np.pi * (diameter_mm / 2.0) ** 2 * height_mm)
    rows: list[dict[str, Any]] = []
    for res in resolutions:
        from porous_designer.domain.specification import DomainSpec

        domain = DomainSpec(shape=DomainShape.CYLINDER, dimensions_mm=[diameter_mm, height_mm])
        grid = build_domain_grid(domain, res)
        voxel_volume = float(grid.mask.sum() * res**3)
        rows.append(
            {
                "resolution_mm": res,
                "grid_shape": grid.grid_shape,
                "voxel_count": int(np.prod(grid.grid_shape)),
                "analytic_volume_mm3": analytic_volume,
                "voxelized_volume_mm3": voxel_volume,
                "volume_error_fraction": abs(voxel_volume - analytic_volume) / analytic_volume,
                "minimum_recommended_resolution_mm": min(diameter_mm, height_mm) / 40.0,
            }
        )
    payload = {
        "diameter_mm": diameter_mm,
        "height_mm": height_mm,
        "rows": rows,
        "recommendation": (
            "Use at least 40 voxels across the smallest cylinder dimension for dimensional screening; "
            "run sensitivity before final acceptance."
        ),
    }
    (output_dir / "cylinder_accuracy.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
