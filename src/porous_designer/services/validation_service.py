"""Orchestrated validation for Phase 2A STL pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import trimesh

from porous_designer.domain.specification import DesignSpecification
from porous_designer.domain.validation import ValidationReport
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
) -> ValidationReport:
    config = config or ValidationConfig()
    report = ValidationReport()
    bounds = domain_bounds(spec.domain)
    domain_vol = domain_volume(spec.domain)
    vox_por = voxel_porosity(solid_grid, domain_mask)
    mesh_por = mesh_porosity(float(mesh.volume), domain_vol)
    target = spec.targets.porosity_target.target
    tol = spec.targets.porosity_target.tolerance or config.porosity_tolerance

    add_checks_to_report(report, validate_dimensions(mesh.bounds[0], mesh.bounds[1], bounds, config.dimension_tolerance_mm))
    add_checks_to_report(report, validate_mesh(mesh, domain_volume_mm3=domain_vol, require_single_solid=spec.constraints.require_single_solid_component))
    add_checks_to_report(
        report,
        validate_porosity(
            target=target,
            tolerance=tol,
            voxel_porosity=vox_por,
            mesh_porosity=mesh_por,
            voxel_resolution_mm=voxel_mm,
            max_method_disagreement=config.max_porosity_method_disagreement,
            disagreement_policy=config.porosity_disagreement_policy,
        ),
    )
    add_checks_to_report(
        report,
        validate_connectivity(
            connectivity,
            require_open_pores=spec.constraints.require_open_pores,
            require_single_solid=spec.constraints.require_single_solid_component,
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
