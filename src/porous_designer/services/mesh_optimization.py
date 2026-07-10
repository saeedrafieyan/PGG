"""Validated optional mesh optimization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from porous_designer.exporters.stl_exporter import STLExportResult, export_stl


class OptimizationProfile(str, Enum):
    NONE = "none"
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"


@dataclass
class OptimizationThresholds:
    max_porosity_change: float = 0.005
    max_volume_change_fraction: float = 0.005
    max_bbox_change_mm: float = 0.02
    max_surface_deviation_mm: float = 0.04
    sample_count: int = 2048


@dataclass
class MeshOptimizationResult:
    profile: OptimizationProfile
    accepted: bool
    reason: str
    master_path: Path
    optimized_path: Path | None
    recommended_path: Path
    master_triangles: int
    optimized_triangles: int | None
    master_size_bytes: int
    optimized_size_bytes: int | None
    reduction_percent: float
    max_surface_deviation_mm: float | None
    volume_change_fraction: float | None
    bbox_change_mm: float | None
    optimized_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        for key in ("master_path", "optimized_path", "recommended_path"):
            if data[key] is not None:
                data[key] = str(data[key])
        data["profile"] = self.profile.value
        return data


def deterministic_surface_deviation(
    master: trimesh.Trimesh,
    candidate: trimesh.Trimesh,
    *,
    sample_count: int,
) -> float:
    if (
        len(master.vertices) == len(candidate.vertices)
        and len(master.faces) == len(candidate.faces)
        and np.array_equal(master.vertices, candidate.vertices)
        and np.array_equal(master.faces, candidate.faces)
    ):
        return 0.0
    points, _ = trimesh.sample.sample_surface(master, sample_count, seed=0)
    try:
        closest, distances, _ = trimesh.proximity.closest_point(candidate, points)
        return float(np.max(distances))
    except Exception:
        # Fallback: deterministic vertex-to-nearest-vertex approximation.
        from scipy.spatial import cKDTree

        tree = cKDTree(candidate.vertices)
        distances, _ = tree.query(points, k=1)
        return float(np.max(distances))


def _target_faces(face_count: int, profile: OptimizationProfile) -> int:
    if profile == OptimizationProfile.CONSERVATIVE:
        return max(1000, int(face_count * 0.75))
    if profile == OptimizationProfile.BALANCED:
        return max(1000, int(face_count * 0.50))
    return face_count


def optimize_mesh_candidate(
    mesh: trimesh.Trimesh,
    profile: OptimizationProfile,
) -> trimesh.Trimesh | None:
    if profile == OptimizationProfile.NONE:
        return None
    target = _target_faces(len(mesh.faces), profile)
    if target >= len(mesh.faces):
        return None
    try:
        candidate = mesh.simplify_quadric_decimation(face_count=target)
    except TypeError:
        candidate = mesh.simplify_quadric_decimation(target)
    except Exception:
        return None
    if candidate is None or len(candidate.faces) == 0:
        return None
    candidate.fix_normals()
    return candidate


def optimize_and_validate_mesh(
    mesh: trimesh.Trimesh,
    *,
    master_path: Path,
    optimized_path: Path,
    domain_volume_mm3: float,
    profile: OptimizationProfile = OptimizationProfile.NONE,
    thresholds: OptimizationThresholds | None = None,
) -> tuple[MeshOptimizationResult, STLExportResult | None]:
    thresholds = thresholds or OptimizationThresholds()
    master_size = master_path.stat().st_size if master_path.exists() else 0
    if profile == OptimizationProfile.NONE:
        return (
            MeshOptimizationResult(
                profile,
                False,
                "optimization disabled",
                master_path,
                None,
                master_path,
                len(mesh.faces),
                None,
                master_size,
                None,
                0.0,
                None,
                None,
                None,
                None,
            ),
            None,
        )

    candidate = optimize_mesh_candidate(mesh, profile)
    if candidate is None:
        return (
            MeshOptimizationResult(
                profile,
                False,
                "optimizer unavailable or produced no candidate",
                master_path,
                None,
                master_path,
                len(mesh.faces),
                None,
                master_size,
                None,
                0.0,
                None,
                None,
                None,
                None,
            ),
            None,
        )

    master_components = len(mesh.split(only_watertight=False))
    candidate_components = len(candidate.split(only_watertight=False))
    volume_change = abs(float(candidate.volume) - float(mesh.volume)) / max(abs(float(mesh.volume)), 1e-9)
    bbox_change = float(np.max(np.abs((candidate.bounds[1] - candidate.bounds[0]) - (mesh.bounds[1] - mesh.bounds[0]))))
    porosity_change = volume_change * abs(float(mesh.volume)) / max(domain_volume_mm3, 1e-9)
    deviation = deterministic_surface_deviation(mesh, candidate, sample_count=thresholds.sample_count)

    checks_ok = (
        candidate.is_watertight
        and candidate.is_winding_consistent
        and float(candidate.volume) > 0
        and candidate_components == master_components
        and volume_change <= thresholds.max_volume_change_fraction
        and bbox_change <= thresholds.max_bbox_change_mm
        and porosity_change <= thresholds.max_porosity_change
        and deviation <= thresholds.max_surface_deviation_mm
        and int((candidate.area_faces == 0).sum()) == 0
    )
    export_result: STLExportResult | None = None
    if checks_ok:
        export_result = export_stl(candidate, optimized_path)
        opt_size = export_result.file_size_bytes
        recommended = optimized_path
        reason = "optimization accepted"
    else:
        opt_size = None
        recommended = master_path
        reason = "optimization rejected by validation thresholds"

    reduction = 100.0 * (1.0 - len(candidate.faces) / max(len(mesh.faces), 1))
    result = MeshOptimizationResult(
        profile=profile,
        accepted=checks_ok,
        reason=reason,
        master_path=master_path,
        optimized_path=optimized_path if checks_ok else None,
        recommended_path=recommended,
        master_triangles=len(mesh.faces),
        optimized_triangles=len(candidate.faces),
        master_size_bytes=master_size,
        optimized_size_bytes=opt_size,
        reduction_percent=round(reduction, 3),
        max_surface_deviation_mm=round(deviation, 6),
        volume_change_fraction=round(volume_change, 6),
        bbox_change_mm=round(bbox_change, 6),
        optimized_sha256=export_result.sha256 if export_result else None,
    )
    optimized_path.parent.mkdir(parents=True, exist_ok=True)
    (optimized_path.parent / "mesh_optimization.json").write_text(
        json.dumps(result.to_dict(), indent=2),
        encoding="utf-8",
    )
    return result, export_result
