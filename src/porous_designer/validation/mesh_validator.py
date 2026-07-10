"""STL mesh quality validation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from porous_designer.domain.enums import Severity, ValidationStatus
from porous_designer.domain.validation import ValidationCheck, ValidationReport


def validate_mesh(
    mesh: trimesh.Trimesh,
    *,
    domain_volume_mm3: float,
    require_single_solid: bool = True,
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    volume = float(mesh.volume)
    checks.append(
        ValidationCheck(
            name="enclosed_volume_positive",
            requested_value="> 0",
            achieved_value=round(volume, 4),
            units="mm^3",
            tolerance=None,
            status=ValidationStatus.PASS if volume > 0 else ValidationStatus.FAIL,
            severity=Severity.CRITICAL,
            method="trimesh.volume (signed)",
            message="Solid enclosed volume must be positive.",
        )
    )

    wt = bool(mesh.is_watertight)
    checks.append(
        ValidationCheck(
            name="watertight",
            requested_value=True,
            achieved_value=wt,
            units="bool",
            status=ValidationStatus.PASS if wt else ValidationStatus.FAIL,
            severity=Severity.CRITICAL,
            method="trimesh.is_watertight",
            message="Mesh watertightness check.",
        )
    )

    winding = bool(mesh.is_winding_consistent)
    checks.append(
        ValidationCheck(
            name="winding_consistent",
            requested_value=True,
            achieved_value=winding,
            units="bool",
            status=ValidationStatus.PASS if winding else ValidationStatus.FAIL,
            severity=Severity.ERROR,
            method="trimesh.is_winding_consistent",
            message="Normal winding consistency.",
        )
    )

    components = len(mesh.split(only_watertight=False))
    checks.append(
        ValidationCheck(
            name="mesh_shell_component_count",
            requested_value=None,
            achieved_value=components,
            units="count",
            status=ValidationStatus.PASS,
            severity=Severity.INFO,
            method="trimesh.split",
            message=(
                "Connected mesh shell count recorded. Material connectivity is "
                "validated on the voxel solid phase."
            ),
        )
    )

    degenerate = int((mesh.area_faces == 0).sum()) if hasattr(mesh, "area_faces") else 0
    checks.append(
        ValidationCheck(
            name="degenerate_faces",
            requested_value=0,
            achieved_value=degenerate,
            units="count",
            status=ValidationStatus.PASS if degenerate == 0 else ValidationStatus.WARNING,
            severity=Severity.WARNING,
            method="zero-area face count",
            message="Degenerate triangle count.",
        )
    )

    checks.append(
        ValidationCheck(
            name="triangle_count",
            requested_value=None,
            achieved_value=len(mesh.faces),
            units="count",
            status=ValidationStatus.PASS,
            severity=Severity.INFO,
            method="mesh face count",
            message="Triangle count recorded.",
        )
    )

    return checks


def validate_stl_file(
    path: str | Path,
    *,
    domain_volume_mm3: float | None = None,
    expected_dims: list[float] | None = None,
    dimension_tolerance_mm: float = 0.05,
    require_single_solid: bool = True,
) -> ValidationReport:
    from porous_designer.validation.geometry_validator import validate_dimensions

    report = ValidationReport()
    mesh = trimesh.load(path, force="mesh")
    for check in validate_mesh(mesh, domain_volume_mm3=domain_volume_mm3 or mesh.volume, require_single_solid=require_single_solid):
        report.add_check(check)

    if expected_dims:
        for check in validate_dimensions(mesh.bounds[0], mesh.bounds[1], expected_dims, dimension_tolerance_mm):
            report.add_check(check)

    size_mb = Path(path).stat().st_size / 1e6
    report.add_check(
        ValidationCheck(
            name="stl_file_size",
            achieved_value=round(size_mb, 2),
            units="MB",
            status=ValidationStatus.PASS,
            severity=Severity.INFO,
            method="filesystem",
            message="STL file size.",
        )
    )
    report.compute_overall_status()
    return report
