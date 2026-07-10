"""Mesh construction from voxel fields."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import trimesh
from skimage import measure


@dataclass
class MeshBuildResult:
    mesh: trimesh.Trimesh
    vertices: int
    faces: int
    volume_mm3: float
    watertight: bool
    bounds_min: np.ndarray
    bounds_max: np.ndarray


def solid_grid_to_mesh(solid_grid: np.ndarray, voxel_mm: float) -> MeshBuildResult:
    """Marching cubes on a padded solid field; domain corner at origin."""
    pad = 2
    field = np.zeros(tuple(np.array(solid_grid.shape) + 2 * pad), dtype=np.float32)
    field[pad:-pad, pad:-pad, pad:-pad] = solid_grid.astype(np.float32)
    verts, faces, normals, _ = measure.marching_cubes(
        field, level=0.5, spacing=(voxel_mm, voxel_mm, voxel_mm)
    )
    verts -= pad * voxel_mm
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, vertex_normals=normals, process=True)
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()
    bounds = mesh.bounds
    return MeshBuildResult(
        mesh=mesh,
        vertices=len(mesh.vertices),
        faces=len(mesh.faces),
        volume_mm3=float(mesh.volume),
        watertight=bool(mesh.is_watertight),
        bounds_min=bounds[0].copy(),
        bounds_max=bounds[1].copy(),
    )


def mesh_domain_volume(box: Sequence[float]) -> float:
    return float(box[0] * box[1] * box[2])


def mesh_porosity(mesh_volume_mm3: float, domain_volume_mm3: float) -> float:
    if domain_volume_mm3 <= 0:
        return 0.0
    return float(1.0 - mesh_volume_mm3 / domain_volume_mm3)


def export_binary_stl(mesh: trimesh.Trimesh, path: str | Path) -> Path:
    """Export compact binary STL."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(out)
    return out


def load_stl(path: str | Path) -> trimesh.Trimesh:
    return trimesh.load(path, force="mesh")
