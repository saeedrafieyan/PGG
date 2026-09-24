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
    wall_voxels: float | None = None,
    mesh_authoritative: bool = False,
) -> list[ValidationCheck]:
    """Porosity checks.

    With ``mesh_authoritative`` the exported mesh was built from the
    continuous field (Phase 4.1 kernel), so its enclosed volume is the most
    accurate porosity and it alone is judged against the target. Voxel-centre
    counting is then a cross-check: it aliases on grid-aligned lattices and
    marching cubes thins walls a few voxels thick, so a moderate difference
    is a warning (with a resolution hint) and only a gross one - a sign of a
    real defect such as inverted shells - fails.
    ``wall_voxels`` is the thinnest wall/strut in voxels when known.
    """
    checks: list[ValidationCheck] = []
    uncertainty = voxel_resolution_mm  # resolution-limited reporting
    resolution_limited = wall_voxels is not None and wall_voxels < 3.0
    mesh_ok = abs(mesh_porosity - target) <= tolerance
    gross_disagreement = max(4.0 * max_method_disagreement, 0.12)

    voxel_ok = abs(voxel_porosity - target) <= tolerance
    voxel_status, voxel_severity, voxel_message = ValidationStatus.PASS, Severity.CRITICAL, "Porosity from final-resolution voxel grid."
    if not voxel_ok:
        if (resolution_limited or mesh_authoritative) and mesh_ok:
            voxel_status, voxel_severity = ValidationStatus.WARNING, Severity.WARNING
            voxel_message = "Voxel-centre count of the implicit field; the exported mesh (which meets the target) is the authoritative porosity."
        else:
            voxel_status = ValidationStatus.FAIL
    checks.append(
        ValidationCheck(
            name="porosity_voxel",
            requested_value=target,
            achieved_value=round(voxel_porosity, 4),
            units="fraction",
            tolerance=tolerance,
            status=voxel_status,
            severity=voxel_severity,
            method=f"voxel occupancy at {voxel_resolution_mm} mm",
            message=voxel_message,
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
    explained = (resolution_limited or mesh_authoritative) and abs_diff <= gross_disagreement
    if disagreement_policy == "warn" or explained:
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
                + (
                    f" The thinnest walls span {wall_voxels:.1f} voxels; a final resolution of about "
                    f"{wall_voxels * voxel_resolution_mm / 3.0:.3f} mm or finer resolves them."
                    if resolution_limited and disagree
                    else (" Voxel-centre counting aliases on grid-aligned lattices; the mesh is authoritative." if disagree and explained else "")
                )
            ),
        )
    )
    return checks
