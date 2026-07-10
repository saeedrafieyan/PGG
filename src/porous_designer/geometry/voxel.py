"""Voxel solid-field construction for sphere-pore lattices."""

from __future__ import annotations

from dataclasses import dataclass
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
    domain_mask: np.ndarray | None = None,
    return_center_count: bool = False,
    center_predicate=None,
) -> np.ndarray | tuple[np.ndarray, int]:
    """Build a boolean solid grid (True = solid material) inside the box domain.

    Voxel centres are at (i+0.5)*voxel_mm. Pores are carved as spheres at lattice centers.
    """
    margin = margin if margin is not None else pore_radius_mm
    nx, ny, nz = box_voxel_counts(box, voxel_mm)
    grid = np.ones((nx, ny, nz), dtype=bool)
    if domain_mask is not None:
        grid &= domain_mask
    gx = (np.arange(nx) + 0.5) * voxel_mm
    gy = (np.arange(ny) + 0.5) * voxel_mm
    gz = (np.arange(nz) + 0.5) * voxel_mm

    centers = generate_sphere_centers(box, lattice_spacing_mm, margin, lattice)
    centers = filter_intersecting_centers(centers, pore_radius_mm, box)
    if center_predicate is not None:
        centers = np.array([c for c in centers if center_predicate(c)], dtype=np.float64).reshape(-1, 3)
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
        carved = d2 <= r2
        if domain_mask is not None:
            grid[x0:x1, y0:y1, z0:z1] &= (~carved) | (~domain_mask[x0:x1, y0:y1, z0:z1])
        else:
            grid[x0:x1, y0:y1, z0:z1] &= ~carved
    if return_center_count:
        return grid, int(len(centers))
    return grid


def voxel_porosity(solid_grid: np.ndarray, domain_mask: np.ndarray | None = None) -> float:
    """Void fraction from voxel occupancy (1 - solid fraction)."""
    if domain_mask is None:
        return float(1.0 - solid_grid.mean())
    total = int(domain_mask.sum())
    if total == 0:
        return 0.0
    solid = int((solid_grid & domain_mask).sum())
    return float(1.0 - solid / total)


def void_grid(solid_grid: np.ndarray) -> np.ndarray:
    """Return boolean void (pore) grid."""
    return ~solid_grid


@dataclass
class CleanupReport:
    component_count_before: int
    component_count_after: int
    removed_component_count: int
    removed_voxel_count: int
    removed_volume_mm3: float
    removed_solid_fraction: float
    porosity_before: float
    porosity_after: float
    removed_touched_boundary: bool
    largest_removed_component_voxels: int
    accepted: bool
    reason: str = ""


def remove_small_solid_components(
    solid_grid: np.ndarray,
    *,
    min_voxels: int = 8,
    voxel_mm: float = 1.0,
    domain_mask: np.ndarray | None = None,
    max_removed_solid_fraction: float = 1e-5,
    max_removed_component_voxels: int | None = None,
    reject_boundary_touching: bool = True,
) -> tuple[np.ndarray, CleanupReport]:
    """Remove tiny disconnected solid islands from voxelization.

    Uses 26-neighbour connectivity because diagonal voxel contacts can represent
    sub-voxel material connections after marching cubes. Returns the cleaned
    grid, removed component count, and removed voxel count.
    """
    domain_mask = domain_mask if domain_mask is not None else np.ones_like(solid_grid, dtype=bool)
    por_before = voxel_porosity(solid_grid, domain_mask)
    if min_voxels <= 1:
        report = CleanupReport(1, 1, 0, 0, 0.0, 0.0, por_before, por_before, False, 0, True)
        return solid_grid, report
    structure = np.ones((3, 3, 3), dtype=int)
    labels, count = ndimage.label(solid_grid, structure=structure)
    if count <= 1:
        report = CleanupReport(int(count), int(count), 0, 0, 0.0, 0.0, por_before, por_before, False, 0, True)
        return solid_grid, report
    sizes = np.bincount(labels.ravel())
    remove_labels = np.flatnonzero((sizes > 0) & (sizes < min_voxels))
    remove_labels = remove_labels[remove_labels != 0]
    if len(remove_labels) == 0:
        report = CleanupReport(int(count), int(count), 0, 0, 0.0, 0.0, por_before, por_before, False, 0, True)
        return solid_grid, report
    mask = np.isin(labels, remove_labels)
    boundary = np.zeros_like(solid_grid, dtype=bool)
    boundary[0, :, :] = True
    boundary[-1, :, :] = True
    boundary[:, 0, :] = True
    boundary[:, -1, :] = True
    boundary[:, :, 0] = True
    boundary[:, :, -1] = True
    removed_touch = bool((mask & boundary).any())
    removed_voxels = int(mask.sum())
    solid_voxels = int((solid_grid & domain_mask).sum())
    removed_fraction = float(removed_voxels / max(solid_voxels, 1))
    largest_removed = int(max((sizes[i] for i in remove_labels), default=0))
    max_removed_component_voxels = max_removed_component_voxels or max(min_voxels - 1, 0)

    reason = ""
    accepted = True
    if removed_fraction > max_removed_solid_fraction:
        accepted = False
        reason = "removed solid fraction exceeds configured threshold"
    elif reject_boundary_touching and removed_touch:
        accepted = False
        reason = "removed component touches domain boundary"
    elif largest_removed > max_removed_component_voxels:
        accepted = False
        reason = "largest removed component exceeds configured threshold"

    if not accepted:
        report = CleanupReport(
            int(count),
            int(count),
            int(len(remove_labels)),
            removed_voxels,
            float(removed_voxels * voxel_mm**3),
            removed_fraction,
            por_before,
            por_before,
            removed_touch,
            largest_removed,
            False,
            reason,
        )
        return solid_grid, report

    cleaned = solid_grid.copy()
    cleaned[mask] = False
    labels_after, count_after = ndimage.label(cleaned, structure=structure)
    por_after = voxel_porosity(cleaned, domain_mask)
    report = CleanupReport(
        int(count),
        int(count_after),
        int(len(remove_labels)),
        removed_voxels,
        float(removed_voxels * voxel_mm**3),
        removed_fraction,
        por_before,
        por_after,
        removed_touch,
        largest_removed,
        True,
    )
    return cleaned, report
