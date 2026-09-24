"""Finite-domain masks and measurements."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np

from porous_designer.domain.enums import DomainShape
from porous_designer.domain.specification import DomainSpec


@dataclass(frozen=True)
class DomainGrid:
    shape: DomainShape
    dimensions_mm: tuple[float, ...]
    voxel_mm: float
    grid_shape: tuple[int, int, int]
    mask: np.ndarray
    bounds_mm: tuple[float, float, float]
    volume_mm3: float


def domain_bounds(domain: DomainSpec) -> tuple[float, float, float]:
    if domain.shape in (DomainShape.BOX, DomainShape.MESH):
        return tuple(domain.dimensions_mm)  # type: ignore[return-value]
    if domain.shape == DomainShape.SPHERE:
        d = domain.dimensions_mm[0]
        return (d, d, d)
    diameter, height = domain.dimensions_mm
    return (diameter, diameter, height)


@lru_cache(maxsize=16)
def _mesh_volume(path: str, units: str, mtime: float) -> float:
    from porous_designer.domain.specification import DomainSpec as _DomainSpec
    from porous_designer.implicit.domain_sdf import load_domain_mesh

    import trimesh

    extents = [float(e) for e in trimesh.load(path, force="mesh").extents]
    probe = _DomainSpec(shape=DomainShape.MESH, dimensions_mm=extents, mesh_path=path, mesh_units=units)
    return float(load_domain_mesh(probe).volume)


def domain_volume(domain: DomainSpec) -> float:
    if domain.shape == DomainShape.BOX:
        lx, ly, lz = domain.dimensions_mm
        return float(lx * ly * lz)
    if domain.shape == DomainShape.SPHERE:
        r = domain.dimensions_mm[0] / 2.0
        return float(4.0 / 3.0 * math.pi * r**3)
    if domain.shape == DomainShape.MESH:
        path = str(domain.mesh_path)
        return _mesh_volume(path, domain.mesh_units, Path(path).stat().st_mtime)
    diameter, height = domain.dimensions_mm
    radius = diameter / 2.0
    return float(math.pi * radius * radius * height)


def voxel_counts(bounds_mm: Sequence[float], voxel_mm: float) -> tuple[int, int, int]:
    return tuple(max(1, int(round(d / voxel_mm))) for d in bounds_mm)  # type: ignore[return-value]


def build_domain_grid(domain: DomainSpec, voxel_mm: float) -> DomainGrid:
    """Legacy boolean domain grid (voxel centres at (i + 0.5) * voxel from 0)."""
    bounds = domain_bounds(domain)
    nx, ny, nz = voxel_counts(bounds, voxel_mm)
    if domain.shape == DomainShape.BOX:
        mask = np.ones((nx, ny, nz), dtype=bool)
    elif domain.shape == DomainShape.CYLINDER:
        diameter, _height = domain.dimensions_mm
        radius = diameter / 2.0
        xs = (np.arange(nx) + 0.5) * voxel_mm
        ys = (np.arange(ny) + 0.5) * voxel_mm
        radial = (xs[:, None] - radius) ** 2 + (ys[None, :] - radius) ** 2 <= radius * radius
        mask = np.repeat(radial[:, :, None], nz, axis=2)
    else:
        from porous_designer.implicit.domain_sdf import GridGeometry, domain_sdf_grid

        grid = GridGeometry(voxel_mm=voxel_mm, shape=(nx, ny, nz), bounds_mm=tuple(bounds), margin=0)  # type: ignore[arg-type]
        mask = domain_sdf_grid(domain, grid) <= 0.0
    return DomainGrid(
        shape=domain.shape,
        dimensions_mm=tuple(domain.dimensions_mm),
        voxel_mm=voxel_mm,
        grid_shape=(nx, ny, nz),
        mask=mask,
        bounds_mm=bounds,
        volume_mm3=domain_volume(domain),
    )


def unit_cells_per_axis(domain: DomainSpec, unit_cell_size_mm: float | None) -> list[float] | None:
    if not unit_cell_size_mm:
        return None
    return [round(d / unit_cell_size_mm, 3) for d in domain_bounds(domain)]
