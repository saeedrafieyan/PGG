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
    required_axes: tuple[str, ...] = ("x", "y", "z"),
) -> list[ValidationCheck]:
    """``required_axes`` lists the directions open to the outside (a lateral
    skin closes X and Y, a full skin closes all three)."""
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
        required = require_open_pores and axis in required_axes
        checks.append(
            ValidationCheck(
                name=f"pore_percolation_{axis}",
                requested_value=True if required else None,
                achieved_value=connected,
                units="bool",
                status=ValidationStatus.PASS if (connected or not required) else ValidationStatus.FAIL,
                severity=Severity.CRITICAL if required else Severity.INFO,
                method=f"void label overlap on opposing {axis} faces",
                message=f"Directional pore connectivity along {axis.upper()}." + ("" if axis in required_axes else " Closed by the solid skin (not required)."),
            )
        )

    by_axis = {"x": metrics.pore_connected_x, "y": metrics.pore_connected_y, "z": metrics.pore_connected_z}
    any_percolation = any(by_axis[a] for a in required_axes) if required_axes else False
    open_ok = any_percolation if require_open_pores else True
    open_message = "Open porosity requires percolation in at least one axis."
    if require_open_pores and not required_axes:
        open_message = "A skin on every boundary encloses all pores; disable require_open_pores or use a lateral skin."

    checks.append(
        ValidationCheck(
            name="open_pore_connectivity",
            requested_value="boundary-connected percolation" if require_open_pores else None,
            achieved_value=any_percolation,
            units="bool",
            status=ValidationStatus.PASS if open_ok else ValidationStatus.FAIL,
            severity=Severity.CRITICAL if require_open_pores else Severity.INFO,
            method="measured pore percolation (not inferred from sphere overlap)",
            message=open_message,
        )
    )

    return checks
