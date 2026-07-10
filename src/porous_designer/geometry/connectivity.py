"""Pore and solid connectivity analysis on voxel grids."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy import ndimage


@dataclass
class ConnectivityMetrics:
    solid_component_count: int
    pore_component_count: int
    pore_boundary_connected_fraction: float
    pore_connected_x: bool
    pore_connected_y: bool
    pore_connected_z: bool
    largest_pore_component_fraction: float
    largest_solid_component_fraction: float


def _face_labels(void: np.ndarray, axis: int, side: int) -> set[int]:
    """Label IDs touching a domain face on void grid."""
    if axis == 0:
        slab = void[0 if side == 0 else -1, :, :]
    elif axis == 1:
        slab = void[:, 0 if side == 0 else -1, :]
    else:
        slab = void[:, :, 0 if side == 0 else -1]
    return set(np.unique(slab)) - {0}


def _percolates(void: np.ndarray, axis: int) -> bool:
    labels, _ = ndimage.label(void)
    low = _face_labels(labels, axis, 0)
    high = _face_labels(labels, axis, 1)
    low.discard(0)
    high.discard(0)
    return bool(low & high)


def analyze_void_connectivity(void_grid: np.ndarray, domain_mask: np.ndarray | None = None) -> ConnectivityMetrics:
    """Analyze pore-phase connectivity on a boolean void grid inside the domain."""
    if domain_mask is None:
        domain_mask = np.ones_like(void_grid, dtype=bool)
    void = void_grid.astype(bool) & domain_mask
    pore_labels, pore_count = ndimage.label(void)
    solid_structure = np.ones((3, 3, 3), dtype=int)
    solid = (~void) & domain_mask
    solid_labels, solid_count = ndimage.label(solid, structure=solid_structure)

    pore_sizes = np.bincount(pore_labels.ravel())
    if len(pore_sizes) > 1:
        pore_sizes[0] = 0
        largest_frac = float(pore_sizes.max() / void.sum()) if void.sum() > 0 else 0.0
    else:
        largest_frac = 0.0

    solid_sizes = np.bincount(solid_labels.ravel())
    if len(solid_sizes) > 1:
        solid_sizes[0] = 0
        solid_total = int(solid.sum())
        largest_solid_frac = float(solid_sizes.max() / solid_total) if solid_total > 0 else 0.0
    else:
        largest_solid_frac = 0.0

    boundary_mask = np.zeros_like(void, dtype=bool)
    boundary_mask[0, :, :] = void[0, :, :]
    boundary_mask[-1, :, :] = void[-1, :, :]
    boundary_mask[:, 0, :] = void[:, 0, :]
    boundary_mask[:, -1, :] = void[:, -1, :]
    boundary_mask[:, :, 0] = void[:, :, 0]
    boundary_mask[:, :, -1] = void[:, :, -1]
    boundary_void = void & boundary_mask
    pore_boundary_fraction = (
        float(boundary_void.sum() / void.sum()) if void.sum() > 0 else 0.0
    )

    return ConnectivityMetrics(
        solid_component_count=int(solid_count),
        pore_component_count=int(pore_count),
        pore_boundary_connected_fraction=pore_boundary_fraction,
        pore_connected_x=_percolates(void, 0),
        pore_connected_y=_percolates(void, 1),
        pore_connected_z=_percolates(void, 2),
        largest_pore_component_fraction=largest_frac,
        largest_solid_component_fraction=largest_solid_frac,
    )


def mesh_solid_component_count(mesh) -> int:
    import trimesh

    parts = mesh.split(only_watertight=False)
    return len(parts)
