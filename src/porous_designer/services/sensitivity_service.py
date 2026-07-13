"""Resolution-sensitivity analysis."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from porous_designer.domain.specification import DesignSpecification
from porous_designer.services.generation_service import GenerationProfile, generate_porous_stl


@dataclass
class SensitivityResult:
    output_dir: Path
    rows: list[dict[str, Any]]
    status: dict[str, str]
    reference_resolution_mm: float | None = None


def classify_metric(values: list[float], *, tolerance: float) -> str:
    if len(values) < 2:
        return "stable"
    span = max(values) - min(values)
    if span <= tolerance:
        return "stable"
    if abs(values[-1] - values[-2]) <= tolerance:
        return "converging"
    return "unstable"


def run_resolution_sensitivity(
    spec: DesignSpecification,
    *,
    resolutions: list[float],
    output_dir: Path | None = None,
) -> SensitivityResult:
    output_dir = output_dir or Path(spec.export.output_directory) / "sensitivity"
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for res in resolutions:
        run_spec = spec.model_copy(deep=True)
        run_spec.generation.final_resolution_mm = res
        run_spec.generation.preview_resolution_mm = res
        run_spec.export.output_directory = str(output_dir)
        run_spec.export.output_name = f"{spec.export.output_name}_res_{str(res).replace('.', 'p')}"
        result = generate_porous_stl(run_spec, profile=GenerationProfile.FINAL)
        row = {
            "resolution_mm": res,
            "success": result.success,
            "run_id": result.run_id,
            "control_parameter": result.lattice_spacing_mm,
            "voxel_porosity": result.final_voxel_porosity,
            "mesh_porosity": result.final_mesh_porosity,
            "solid_components": result.solid_components,
            "pore_components": result.connectivity.get("pore_component_count"),
            "pore_connected_x": result.connectivity.get("pore_connected_x"),
            "pore_connected_y": result.connectivity.get("pore_connected_y"),
            "pore_connected_z": result.connectivity.get("pore_connected_z"),
            "triangle_count": result.triangle_count,
            "runtime_s": result.timing.total_s,
            "peak_memory_mb": result.peak_memory_mb,
            "stl_sha256": result.stl_sha256,
            "stl_path": str(result.stl_path) if result.stl_path else None,
        }
        rows.append(row)

    finest = min(rows, key=lambda r: float(r["resolution_mm"])) if rows else None
    if finest:
        for row in rows:
            row["delta_vs_finest"] = {
                "control_parameter": float(row["control_parameter"]) - float(finest["control_parameter"]),
                "voxel_porosity": float(row["voxel_porosity"]) - float(finest["voxel_porosity"]),
                "mesh_porosity": float(row["mesh_porosity"]) - float(finest["mesh_porosity"]),
                "triangle_count": int(row["triangle_count"]) - int(finest["triangle_count"]),
            }

    thresholds = {
        "control_parameter": 0.01,
        "voxel_porosity": 0.01,
        "mesh_porosity": 0.01,
        "triangle_count": 100000,
    }
    status = {
        "control_parameter": classify_metric(
            [float(r["control_parameter"]) for r in rows],
            tolerance=thresholds["control_parameter"],
        ),
        "voxel_porosity": classify_metric(
            [float(r["voxel_porosity"]) for r in rows],
            tolerance=thresholds["voxel_porosity"],
        ),
        "mesh_porosity": classify_metric(
            [float(r["mesh_porosity"]) for r in rows],
            tolerance=thresholds["mesh_porosity"],
        ),
        "triangle_count": classify_metric(
            [float(r["triangle_count"]) for r in rows],
            tolerance=thresholds["triangle_count"],
        ),
    }
    payload = {
        "rows": rows,
        "status": status,
        "classification_thresholds": thresholds,
        "reference_resolution_mm": finest["resolution_mm"] if finest else None,
    }
    (output_dir / "sensitivity.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with open(output_dir / "sensitivity.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["resolution_mm"])
        writer.writeheader()
        writer.writerows(rows)
    return SensitivityResult(
        output_dir=output_dir,
        rows=rows,
        status=status,
        reference_resolution_mm=finest["resolution_mm"] if finest else None,
    )
