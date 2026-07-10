"""Finite-domain masks and measurements."""

from __future__ import annotations

import math
from dataclasses import dataclass
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
    if domain.shape == DomainShape.BOX:
        return tuple(domain.dimensions_mm)  # type: ignore[return-value]
    diameter, height = domain.dimensions_mm
    return (diameter, diameter, height)


def domain_volume(domain: DomainSpec) -> float:
    if domain.shape == DomainShape.BOX:
        lx, ly, lz = domain.dimensions_mm
        return float(lx * ly * lz)
    diameter, height = domain.dimensions_mm
    radius = diameter / 2.0
    return float(math.pi * radius * radius * height)


def voxel_counts(bounds_mm: Sequence[float], voxel_mm: float) -> tuple[int, int, int]:
    return tuple(max(1, int(round(d / voxel_mm))) for d in bounds_mm)  # type: ignore[return-value]


def build_domain_grid(domain: DomainSpec, voxel_mm: float) -> DomainGrid:
    bounds = domain_bounds(domain)
    nx, ny, nz = voxel_counts(bounds, voxel_mm)
    if domain.shape == DomainShape.BOX:
        mask = np.ones((nx, ny, nz), dtype=bool)
    else:
        diameter, _height = domain.dimensions_mm
        radius = diameter / 2.0
        xs = (np.arange(nx) + 0.5) * voxel_mm
        ys = (np.arange(ny) + 0.5) * voxel_mm
        cx = diameter / 2.0
        cy = diameter / 2.0
        radial = (xs[:, None] - cx) ** 2 + (ys[None, :] - cy) ** 2 <= radius * radius
        mask = np.repeat(radial[:, :, None], nz, axis=2)
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
