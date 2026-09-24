"""Validated optional mesh optimization."""

from __future__ import annotations

import json
import time
import tracemalloc
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
    surface_deviation: dict[str, Any] | None
    volume_change_fraction: float | None
    bbox_change_mm: float | None
    optimized_sha256: str | None
    optimization_runtime_s: float | None = None
    peak_memory_mb: float | None = None

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
                None,
                None,
            ),
            None,
        )

    # The generation pipeline may already be tracing; starting/stopping here
    # would discard its measurement. In that case report the traced peak so
    # far, which is an upper bound for the optimization step.
    owns_trace = not tracemalloc.is_tracing()
    if owns_trace:
        tracemalloc.start()
    t0 = time.perf_counter()
    candidate = optimize_mesh_candidate(mesh, profile)
    optimization_runtime = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    if owns_trace:
        tracemalloc.stop()
    peak_mb = peak / (1024 * 1024)
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
                None,
                round(optimization_runtime, 6),
                round(peak_mb, 3),
            ),
            None,
        )

    master_components = len(mesh.split(only_watertight=False))
    candidate_components = len(candidate.split(only_watertight=False))
    volume_change = abs(float(candidate.volume) - float(mesh.volume)) / max(abs(float(mesh.volume)), 1e-9)
    bbox_change = float(np.max(np.abs((candidate.bounds[1] - candidate.bounds[0]) - (mesh.bounds[1] - mesh.bounds[0]))))
    porosity_change = volume_change * abs(float(mesh.volume)) / max(domain_volume_mm3, 1e-9)
    deviation_stats = bidirectional_surface_deviation(
        mesh,
        candidate,
        sample_count=thresholds.sample_count,
        seed=0,
    )
    deviation = float(deviation_stats["bidirectional"]["max"])

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
    export_result: STLExportResult | None = export_stl(candidate, optimized_path)
    opt_size = export_result.file_size_bytes
    if checks_ok:
        recommended = optimized_path
        reason = "optimization accepted"
    else:
        recommended = master_path
        reason = "optimization rejected by validation thresholds"

    reduction = 100.0 * (1.0 - len(candidate.faces) / max(len(mesh.faces), 1))
    result = MeshOptimizationResult(
        profile=profile,
        accepted=checks_ok,
        reason=reason,
        master_path=master_path,
        optimized_path=optimized_path,
        recommended_path=recommended,
        master_triangles=len(mesh.faces),
        optimized_triangles=len(candidate.faces),
        master_size_bytes=master_size,
        optimized_size_bytes=opt_size,
        reduction_percent=round(reduction, 3),
        max_surface_deviation_mm=round(deviation, 6),
        surface_deviation=deviation_stats,
        volume_change_fraction=round(volume_change, 6),
        bbox_change_mm=round(bbox_change, 6),
        optimized_sha256=export_result.sha256 if export_result else None,
        optimization_runtime_s=round(optimization_runtime, 6),
        peak_memory_mb=round(peak_mb, 3),
    )
    optimized_path.parent.mkdir(parents=True, exist_ok=True)
    (optimized_path.parent / "mesh_optimization.json").write_text(
        json.dumps(result.to_dict(), indent=2),
        encoding="utf-8",
    )
    return result, export_result


def _sample_distances(source: trimesh.Trimesh, target: trimesh.Trimesh, *, sample_count: int, seed: int) -> np.ndarray:
    points, _ = trimesh.sample.sample_surface(source, sample_count, seed=seed)
    try:
        _closest, distances, _tri = trimesh.proximity.closest_point(target, points)
        return np.asarray(distances, dtype=float)
    except Exception:
        from scipy.spatial import cKDTree

        tree = cKDTree(target.vertices)
        distances, _ = tree.query(points, k=1)
        return np.asarray(distances, dtype=float)


def _distance_summary(distances: np.ndarray) -> dict[str, float]:
    if len(distances) == 0:
        return {"mean": 0.0, "median": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "mean": round(float(np.mean(distances)), 6),
        "median": round(float(np.median(distances)), 6),
        "p95": round(float(np.percentile(distances, 95)), 6),
        "p99": round(float(np.percentile(distances, 99)), 6),
        "max": round(float(np.max(distances)), 6),
    }


def bidirectional_surface_deviation(
    master: trimesh.Trimesh,
    candidate: trimesh.Trimesh,
    *,
    sample_count: int,
    seed: int = 0,
) -> dict[str, Any]:
    if (
        len(master.vertices) == len(candidate.vertices)
        and len(master.faces) == len(candidate.faces)
        and np.array_equal(master.vertices, candidate.vertices)
        and np.array_equal(master.faces, candidate.faces)
    ):
        zero = {"mean": 0.0, "median": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
        return {
            "seed": seed,
            "sample_count": sample_count,
            "master_to_candidate": zero,
            "candidate_to_master": zero,
            "bidirectional": zero,
        }
    a = _sample_distances(master, candidate, sample_count=sample_count, seed=seed)
    b = _sample_distances(candidate, master, sample_count=sample_count, seed=seed + 1)
    both = np.concatenate([a, b])
    return {
        "seed": seed,
        "sample_count": sample_count,
        "master_to_candidate": _distance_summary(a),
        "candidate_to_master": _distance_summary(b),
        "bidirectional": _distance_summary(both),
    }


def nonmanifold_edge_count(mesh: trimesh.Trimesh) -> int:
    try:
        _edges, counts = np.unique(np.sort(mesh.edges, axis=1), axis=0, return_counts=True)
        return int((counts != 2).sum())
    except Exception:
        return -1


def validate_optimization_pair(
    master_path: Path,
    candidate_path: Path,
    *,
    domain_volume_mm3: float,
    thresholds: OptimizationThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or OptimizationThresholds()
    master = trimesh.load(master_path, force="mesh")
    candidate = trimesh.load(candidate_path, force="mesh")
    master_volume = float(master.volume)
    candidate_volume = float(candidate.volume)
    volume_change = abs(candidate_volume - master_volume) / max(abs(master_volume), 1e-9)
    porosity_before = 1.0 - master_volume / max(domain_volume_mm3, 1e-9)
    porosity_after = 1.0 - candidate_volume / max(domain_volume_mm3, 1e-9)
    bbox_before = (master.bounds[1] - master.bounds[0]).tolist()
    bbox_after = (candidate.bounds[1] - candidate.bounds[0]).tolist()
    bbox_change = float(np.max(np.abs(np.asarray(bbox_after) - np.asarray(bbox_before))))
    surface = bidirectional_surface_deviation(master, candidate, sample_count=thresholds.sample_count, seed=0)
    checks = {
        "watertight": bool(candidate.is_watertight),
        "winding_consistent": bool(candidate.is_winding_consistent),
        "positive_volume": candidate_volume > 0,
        "nonmanifold_edges_zero": nonmanifold_edge_count(candidate) == 0,
        "component_count_unchanged": len(master.split(only_watertight=False)) == len(candidate.split(only_watertight=False)),
        "bbox_within_threshold": bbox_change <= thresholds.max_bbox_change_mm,
        "volume_within_threshold": volume_change <= thresholds.max_volume_change_fraction,
        "porosity_within_threshold": abs(porosity_after - porosity_before) <= thresholds.max_porosity_change,
        "surface_within_threshold": float(surface["bidirectional"]["max"]) <= thresholds.max_surface_deviation_mm,
        "degenerate_faces_zero": int((candidate.area_faces == 0).sum()) == 0,
    }
    return {
        "accepted": all(checks.values()),
        "checks": checks,
        "master": {
            "path": str(master_path),
            "triangles": int(len(master.faces)),
            "size_bytes": master_path.stat().st_size,
            "watertight": bool(master.is_watertight),
            "winding_consistent": bool(master.is_winding_consistent),
            "nonmanifold_edges": nonmanifold_edge_count(master),
            "degenerate_faces": int((master.area_faces == 0).sum()),
            "components": len(master.split(only_watertight=False)),
            "bbox": bbox_before,
            "volume_mm3": master_volume,
            "porosity": porosity_before,
        },
        "candidate": {
            "path": str(candidate_path),
            "triangles": int(len(candidate.faces)),
            "size_bytes": candidate_path.stat().st_size,
            "watertight": bool(candidate.is_watertight),
            "winding_consistent": bool(candidate.is_winding_consistent),
            "nonmanifold_edges": nonmanifold_edge_count(candidate),
            "degenerate_faces": int((candidate.area_faces == 0).sum()),
            "components": len(candidate.split(only_watertight=False)),
            "bbox": bbox_after,
            "volume_mm3": candidate_volume,
            "porosity": porosity_after,
        },
        "changes": {
            "triangle_reduction_percent": round(100.0 * (1.0 - len(candidate.faces) / max(len(master.faces), 1)), 3),
            "volume_change_fraction": round(volume_change, 6),
            "porosity_change": round(abs(porosity_after - porosity_before), 6),
            "bbox_change_mm": round(bbox_change, 6),
        },
        "surface_deviation": surface,
    }
