"""Voxel solid-field construction for sphere-pore lattices."""

from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy import ndimage

from porous_designer.generators.sphere_lattices import (
    LatticeType,
    filter_intersecting_centers,
    generate_sphere_centers,
)


def box_voxel_counts(box: Sequence[float], voxel_mm: float) -> tuple[int, int, int]:
    return (
        int(round(box[0] / voxel_mm)),
        int(round(box[1] / voxel_mm)),
        int(round(box[2] / voxel_mm)),
    )


def sphere_solid_grid(
    box: Sequence[float],
    voxel_mm: float,
    pore_radius_mm: float,
    lattice_spacing_mm: float,
    lattice: LatticeType,
    *,
    margin: float | None = None,
) -> np.ndarray:
    """Build a boolean solid grid (True = solid material) inside the box domain.

    Voxel centres are at (i+0.5)*voxel_mm. Pores are carved as spheres at lattice centers.
    """
    margin = margin if margin is not None else pore_radius_mm
    nx, ny, nz = box_voxel_counts(box, voxel_mm)
    grid = np.ones((nx, ny, nz), dtype=bool)
    gx = (np.arange(nx) + 0.5) * voxel_mm
    gy = (np.arange(ny) + 0.5) * voxel_mm
    gz = (np.arange(nz) + 0.5) * voxel_mm

    centers = generate_sphere_centers(box, lattice_spacing_mm, margin, lattice)
    centers = filter_intersecting_centers(centers, pore_radius_mm, box)
    r2 = pore_radius_mm * pore_radius_mm
    rr = int(np.ceil(pore_radius_mm / voxel_mm)) + 1

    for cx, cy, cz in centers:
        ix = int(round(cx / voxel_mm - 0.5))
        iy = int(round(cy / voxel_mm - 0.5))
        iz = int(round(cz / voxel_mm - 0.5))
        x0, x1 = max(0, ix - rr), min(nx, ix + rr + 1)
        y0, y1 = max(0, iy - rr), min(ny, iy + rr + 1)
        z0, z1 = max(0, iz - rr), min(nz, iz + rr + 1)
        if x0 >= x1 or y0 >= y1 or z0 >= z1:
            continue
        sx = gx[x0:x1] - cx
        sy = gy[y0:y1] - cy
        sz = gz[z0:z1] - cz
        d2 = sx[:, None, None] ** 2 + sy[None, :, None] ** 2 + sz[None, None, :] ** 2
        grid[x0:x1, y0:y1, z0:z1] &= d2 > r2
    return grid


def voxel_porosity(solid_grid: np.ndarray) -> float:
    """Void fraction from voxel occupancy (1 - solid fraction)."""
    return float(1.0 - solid_grid.mean())


def void_grid(solid_grid: np.ndarray) -> np.ndarray:
    """Return boolean void (pore) grid."""
    return ~solid_grid


def remove_small_solid_components(
    solid_grid: np.ndarray,
    *,
    min_voxels: int = 8,
) -> tuple[np.ndarray, int, int]:
    """Remove tiny disconnected solid islands from voxelization.

    Uses 26-neighbour connectivity because diagonal voxel contacts can represent
    sub-voxel material connections after marching cubes. Returns the cleaned
    grid, removed component count, and removed voxel count.
    """
    if min_voxels <= 1:
        return solid_grid, 0, 0
    structure = np.ones((3, 3, 3), dtype=int)
    labels, count = ndimage.label(solid_grid, structure=structure)
    if count <= 1:
        return solid_grid, 0, 0
    sizes = np.bincount(labels.ravel())
    remove_labels = np.flatnonzero((sizes > 0) & (sizes < min_voxels))
    remove_labels = remove_labels[remove_labels != 0]
    if len(remove_labels) == 0:
        return solid_grid, 0, 0
    cleaned = solid_grid.copy()
    mask = np.isin(labels, remove_labels)
    cleaned[mask] = False
    return cleaned, int(len(remove_labels)), int(mask.sum())
