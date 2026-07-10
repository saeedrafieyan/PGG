"""Pore and solid connectivity validation."""

from __future__ import annotations

from porous_designer.domain.enums import Severity, ValidationStatus
from porous_designer.domain.validation import ValidationCheck
from porous_designer.geometry.connectivity import ConnectivityMetrics


def validate_connectivity(
    metrics: ConnectivityMetrics,
    *,
    require_open_pores: bool,
    require_single_solid: bool,
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []

    solid_ok = metrics.solid_component_count == 1 if require_single_solid else metrics.solid_component_count >= 1
    checks.append(
        ValidationCheck(
            name="solid_components_voxel",
            requested_value=1 if require_single_solid else ">=1",
            achieved_value=metrics.solid_component_count,
            units="count",
            status=ValidationStatus.PASS if solid_ok else ValidationStatus.FAIL,
            severity=Severity.CRITICAL,
            method="scipy.ndimage.label on solid phase",
            message="Solid phase connected components.",
        )
    )

    checks.append(
        ValidationCheck(
            name="pore_components_voxel",
            achieved_value=metrics.pore_component_count,
            units="count",
            status=ValidationStatus.PASS,
            severity=Severity.INFO,
            method="scipy.ndimage.label on void phase",
            message="Pore phase connected components.",
        )
    )

    checks.append(
        ValidationCheck(
            name="pore_boundary_fraction",
            achieved_value=round(metrics.pore_boundary_connected_fraction, 4),
            units="fraction",
            status=ValidationStatus.PASS,
            severity=Severity.INFO,
            method="void voxels on domain boundary / total void",
            message="Fraction of void voxels touching domain boundary.",
        )
    )

    for axis, connected in [
        ("x", metrics.pore_connected_x),
        ("y", metrics.pore_connected_y),
        ("z", metrics.pore_connected_z),
    ]:
        checks.append(
            ValidationCheck(
                name=f"pore_percolation_{axis}",
                requested_value=True if require_open_pores else None,
                achieved_value=connected,
                units="bool",
                status=(
                    ValidationStatus.PASS
                    if (connected or not require_open_pores)
                    else ValidationStatus.FAIL
                ),
                severity=Severity.CRITICAL if require_open_pores else Severity.INFO,
                method=f"void label overlap on opposing {axis} faces",
                message=f"Directional pore connectivity along {axis.upper()}.",
            )
        )

    any_percolation = metrics.pore_connected_x or metrics.pore_connected_y or metrics.pore_connected_z
    open_ok = any_percolation if require_open_pores else True
    checks.append(
        ValidationCheck(
            name="open_pore_connectivity",
            requested_value="boundary-connected percolation" if require_open_pores else None,
            achieved_value=any_percolation,
            units="bool",
            status=ValidationStatus.PASS if open_ok else ValidationStatus.FAIL,
            severity=Severity.CRITICAL if require_open_pores else Severity.INFO,
            method="measured pore percolation (not inferred from sphere overlap)",
            message="Open porosity requires percolation in at least one axis.",
        )
    )

    return checks
