"""Orchestrated validation for Phase 2A STL pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import trimesh

from porous_designer.domain.enums import DomainShape, Severity, ValidationStatus
from porous_designer.domain.specification import DesignSpecification
from porous_designer.domain.validation import ValidationCheck, ValidationReport
from porous_designer.geometry.domains import domain_bounds, domain_volume
from porous_designer.geometry.connectivity import ConnectivityMetrics, analyze_void_connectivity
from porous_designer.geometry.mesh import mesh_porosity
from porous_designer.geometry.voxel import void_grid, voxel_porosity
from porous_designer.validation.connectivity_validator import validate_connectivity
from porous_designer.validation.geometry_validator import add_checks_to_report, validate_dimensions
from porous_designer.validation.mesh_validator import validate_mesh
from porous_designer.validation.porosity_validator import validate_porosity


@dataclass
class ValidationConfig:
    dimension_tolerance_mm: float = 0.05
    porosity_tolerance: float = 0.02
    max_porosity_method_disagreement: float = 0.03
    porosity_disagreement_policy: str = "fail"


def run_validation(
    spec: DesignSpecification,
    mesh: trimesh.Trimesh,
    solid_grid,
    voxel_mm: float,
    connectivity: ConnectivityMetrics,
    domain_mask=None,
    config: ValidationConfig | None = None,
    *,
    porosity_target: float | None = None,
    porosity_is_target: bool = True,
    porosity_profile: list[dict] | None = None,
    porous_region_mask=None,
    percolation_axes: tuple[str, ...] = ("x", "y", "z"),
    wall_voxels: float | None = None,
    mesh_authoritative: bool = False,
) -> ValidationReport:
    """Validate a generated part.

    ``porosity_target`` overrides the specification target (the mean of a
    graded target). With ``porosity_is_target=False`` (geometry fixed by the
    user) porosity is reported but not judged against the target.
    """
    config = config or ValidationConfig()
    report = ValidationReport()
    bounds = domain_bounds(spec.domain)
    domain_vol = domain_volume(spec.domain)
    vox_por = voxel_porosity(solid_grid, domain_mask)
    mesh_por = mesh_porosity(float(mesh.volume), domain_vol)
    if porous_region_mask is not None and domain_mask is not None:
        # With a solid skin the target applies to the porous core. All void
        # lies in the core, so the mesh estimate scales by the volume ratio.
        region_voxels = int(porous_region_mask.sum())
        ratio = int(domain_mask.sum()) / max(region_voxels, 1)
        vox_por = voxel_porosity(solid_grid, porous_region_mask)
        mesh_por = mesh_por * ratio
    target = spec.targets.porosity_target.target if porosity_target is None else porosity_target
    tol = spec.targets.porosity_target.tolerance or config.porosity_tolerance

    curved = spec.domain.shape != DomainShape.BOX
    add_checks_to_report(report, validate_dimensions(mesh.bounds[0], mesh.bounds[1], bounds, config.dimension_tolerance_mm, undersize_is_warning=curved))
    add_checks_to_report(report, validate_mesh(mesh, domain_volume_mm3=domain_vol, require_single_solid=spec.constraints.require_single_solid_component))
    porosity_checks = validate_porosity(
        target=target,
        tolerance=tol,
        voxel_porosity=vox_por,
        mesh_porosity=mesh_por,
        voxel_resolution_mm=voxel_mm,
        max_method_disagreement=config.max_porosity_method_disagreement,
        disagreement_policy=config.porosity_disagreement_policy,
        wall_voxels=wall_voxels,
        mesh_authoritative=mesh_authoritative,
    )
    if not porosity_is_target:
        for check in porosity_checks:
            if check.name in ("porosity_voxel", "porosity_mesh_volume"):
                check.requested_value = "result (geometry fixed)"
                check.status = ValidationStatus.PASS
                check.severity = Severity.INFO
                check.message = "Wall thickness was fixed by the specification; porosity is reported as a result."
    add_checks_to_report(report, porosity_checks)
    if porosity_profile:
        worst = max(porosity_profile, key=lambda row: abs(row["achieved"] - row["target"]))
        deviation = abs(worst["achieved"] - worst["target"])
        ok = deviation <= 2.0 * tol
        report.add_check(
            ValidationCheck(
                name="porosity_grading_profile",
                requested_value=f"graded {porosity_profile[0]['target']:.3f} -> {porosity_profile[-1]['target']:.3f}",
                achieved_value=round(deviation, 4),
                units="fraction",
                tolerance=round(2.0 * tol, 4),
                status=ValidationStatus.PASS if ok else ValidationStatus.WARNING,
                severity=Severity.INFO if ok else Severity.WARNING,
                method=f"porosity per band of the grading coordinate ({len(porosity_profile)} bands)",
                message=f"Largest band deviation {deviation:.3f} at s={worst['s_from']:.1f}-{worst['s_to']:.1f} (target {worst['target']:.3f}, achieved {worst['achieved']:.3f}).",
            )
        )
    add_checks_to_report(
        report,
        validate_connectivity(
            connectivity,
            require_open_pores=spec.constraints.require_open_pores,
            require_single_solid=spec.constraints.require_single_solid_component,
            required_axes=percolation_axes,
        ),
    )
    report.compute_overall_status()
    return report


def validate_standalone_stl(
    path: str,
    expected_dims: list[float] | None = None,
    config: ValidationConfig | None = None,
) -> ValidationReport:
    from porous_designer.validation.mesh_validator import validate_stl_file

    config = config or ValidationConfig()
    return validate_stl_file(
        path,
        expected_dims=expected_dims,
        dimension_tolerance_mm=config.dimension_tolerance_mm,
    )
