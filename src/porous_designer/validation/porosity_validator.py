"""Porosity validation — voxel vs mesh methods."""

from __future__ import annotations

from porous_designer.domain.enums import Severity, ValidationStatus
from porous_designer.domain.validation import ValidationCheck


def validate_porosity(
    *,
    target: float,
    tolerance: float,
    voxel_porosity: float,
    mesh_porosity: float,
    voxel_resolution_mm: float,
    max_method_disagreement: float = 0.03,
    disagreement_policy: str = "fail",
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    uncertainty = voxel_resolution_mm  # resolution-limited reporting

    checks.append(
        ValidationCheck(
            name="porosity_voxel",
            requested_value=target,
            achieved_value=round(voxel_porosity, 4),
            units="fraction",
            tolerance=tolerance,
            status=ValidationStatus.PASS
            if abs(voxel_porosity - target) <= tolerance
            else ValidationStatus.FAIL,
            severity=Severity.CRITICAL,
            method=f"voxel occupancy at {voxel_resolution_mm} mm",
            message="Porosity from final-resolution voxel grid.",
        )
    )

    checks.append(
        ValidationCheck(
            name="porosity_mesh_volume",
            requested_value=target,
            achieved_value=round(mesh_porosity, 4),
            units="fraction",
            tolerance=tolerance,
            status=ValidationStatus.PASS
            if abs(mesh_porosity - target) <= tolerance
            else ValidationStatus.FAIL,
            severity=Severity.CRITICAL,
            method="1 - enclosed_mesh_volume / domain_volume",
            message="Porosity from enclosed STL mesh volume.",
        )
    )

    abs_diff = abs(voxel_porosity - mesh_porosity)
    rel_diff = abs_diff / max(target, 1e-9)
    disagree = abs_diff > max_method_disagreement
    if disagreement_policy == "warn":
        disagree_status = ValidationStatus.WARNING if disagree else ValidationStatus.PASS
        severity = Severity.WARNING
    else:
        disagree_status = ValidationStatus.FAIL if disagree else ValidationStatus.PASS
        severity = Severity.CRITICAL if disagree else Severity.INFO

    checks.append(
        ValidationCheck(
            name="porosity_method_disagreement",
            requested_value=f"<= {max_method_disagreement}",
            achieved_value=round(abs_diff, 4),
            units="fraction",
            tolerance=max_method_disagreement,
            status=disagree_status,
            severity=severity,
            method="abs(voxel - mesh)",
            message=(
                f"Absolute difference {abs_diff:.4f}, relative {rel_diff:.4f}. "
                f"Resolution uncertainty ~{uncertainty} mm."
            ),
        )
    )
    return checks
