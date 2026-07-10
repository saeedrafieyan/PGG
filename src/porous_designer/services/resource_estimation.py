"""Conservative resource estimates before voxel allocation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from porous_designer.domain.enums import FeasibilityStatus
from porous_designer.domain.specification import DesignSpecification
from porous_designer.geometry.domains import domain_bounds, voxel_counts


@dataclass
class ResourceEstimate:
    grid_shape: tuple[int, int, int]
    voxel_count: int
    base_array_mb: float
    temporary_array_mb: float
    marching_cubes_mb: float
    estimated_peak_mb: float
    available_memory_mb: float | None
    memory_fraction: float | None
    status: FeasibilityStatus
    runtime_class: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "grid_shape": self.grid_shape,
            "voxel_count": self.voxel_count,
            "base_array_mb": self.base_array_mb,
            "temporary_array_mb": self.temporary_array_mb,
            "marching_cubes_mb": self.marching_cubes_mb,
            "estimated_peak_mb": self.estimated_peak_mb,
            "available_memory_mb": self.available_memory_mb,
            "memory_fraction": self.memory_fraction,
            "status": self.status.value,
            "runtime_class": self.runtime_class,
            "message": self.message,
        }


def available_memory_mb() -> float | None:
    try:
        import psutil  # type: ignore

        return float(psutil.virtual_memory().available / (1024 * 1024))
    except Exception:
        if hasattr(os, "sysconf"):
            try:
                pages = os.sysconf("SC_AVPHYS_PAGES")
                page_size = os.sysconf("SC_PAGE_SIZE")
                return float(pages * page_size / (1024 * 1024))
            except Exception:
                return None
    return None


def estimate_resources(
    spec: DesignSpecification,
    resolution_mm: float,
    *,
    warning_memory_fraction: float = 0.50,
    maximum_memory_fraction: float = 0.75,
    available_mb: float | None = None,
) -> ResourceEstimate:
    shape = voxel_counts(domain_bounds(spec.domain), resolution_mm)
    voxel_count = int(shape[0] * shape[1] * shape[2])
    base = voxel_count / (1024 * 1024)  # boolean grid, 1 byte per voxel
    temporary = base * 6.0  # coordinate slices, masks, labels, working fields
    marching = base * 240.0  # conservative marching-cubes mesh amplification
    peak = base + temporary + marching
    available = available_mb if available_mb is not None else available_memory_mb()
    fraction = peak / available if available else None
    if voxel_count < 2_000_000:
        runtime_class = "fast"
    elif voxel_count < 20_000_000:
        runtime_class = "moderate"
    else:
        runtime_class = "heavy"

    status = FeasibilityStatus.FEASIBLE
    message = "resource estimate within configured limits"
    if fraction is not None and fraction >= maximum_memory_fraction:
        status = FeasibilityStatus.INFEASIBLE
        message = "estimated peak memory exceeds hard configured memory fraction"
    elif fraction is not None and fraction >= warning_memory_fraction:
        status = FeasibilityStatus.CONDITIONALLY_FEASIBLE
        message = "estimated peak memory exceeds warning fraction"

    return ResourceEstimate(
        grid_shape=shape,
        voxel_count=voxel_count,
        base_array_mb=round(base, 2),
        temporary_array_mb=round(temporary, 2),
        marching_cubes_mb=round(marching, 2),
        estimated_peak_mb=round(peak, 2),
        available_memory_mb=round(available, 2) if available else None,
        memory_fraction=round(fraction, 4) if fraction is not None else None,
        status=status,
        runtime_class=runtime_class,
        message=message,
    )
