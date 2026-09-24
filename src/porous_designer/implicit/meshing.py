"""Triangle meshes from continuous solid fields.

Marching cubes runs on the float field itself (level 0), so vertices are
placed by linear interpolation of distances rather than on voxel faces: the
surface is smooth, walls keep their thickness, and flat domain faces land on
their true coordinates. The grid is padded with void so every surface is
closed.
"""

from __future__ import annotations

import numpy as np
import trimesh
from skimage import measure

from porous_designer.geometry.mesh import MeshBuildResult


def field_to_mesh(field: np.ndarray, voxel_mm: float, *, origin_mm: float = 0.0, pad: int = 2) -> MeshBuildResult:
    """Mesh the region ``field <= 0``; voxel i is centred at origin + (i + 0.5) * voxel."""
    if not np.any(field <= 0.0):
        raise ValueError("The solid field is empty: no material inside the domain.")
    void_value = np.float32(max(float(field.max()), voxel_mm) + voxel_mm)
    padded = np.full(tuple(np.array(field.shape) + 2 * pad), void_value, dtype=np.float32)
    padded[pad:-pad, pad:-pad, pad:-pad] = field
    # A sample lying (almost) exactly on the iso-level puts a vertex on a grid
    # corner; the zero-area triangles that result would be dropped and leave
    # holes. Nudging such samples off the level keeps the surface manifold
    # and moves it by at most 1e-4 voxel.
    eps = np.float32(1e-4 * voxel_mm)
    near = np.abs(padded) < eps
    padded[near] = eps
    # skimage treats values above the level as "inside"; negate so solid is inside.
    verts, faces, _normals, _ = measure.marching_cubes(-padded, level=0.0, spacing=(voxel_mm,) * 3, allow_degenerate=False)
    verts += origin_mm + (0.5 - pad) * voxel_mm
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    # Marching cubes orients all faces consistently from the field gradient.
    # trimesh.fix_normals would flip internal cavity shells (closed pores)
    # outward and count them as solid, so only the global sign is checked.
    if float(mesh.volume) < 0:
        mesh.invert()
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
