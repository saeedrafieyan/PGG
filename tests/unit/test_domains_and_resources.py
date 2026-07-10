import numpy as np

from porous_designer.domain.enums import DomainShape, StructureFamily
from porous_designer.domain.specification import (
    DesignSpecification,
    DomainSpec,
    GenerationSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
)
from porous_designer.geometry.domains import build_domain_grid, domain_bounds, domain_volume
from porous_designer.services.resource_estimation import estimate_resources


def test_cylinder_domain_mask_and_volume():
    domain = DomainSpec(shape=DomainShape.CYLINDER, dimensions_mm=[4.0, 6.0])
    grid = build_domain_grid(domain, 0.2)
    assert grid.grid_shape == (20, 20, 30)
    assert grid.mask.any()
    assert not grid.mask.all()
    assert domain_bounds(domain) == (4.0, 4.0, 6.0)
    assert domain_volume(domain) > 70.0


def test_resource_estimate_warns_and_rejects():
    spec = DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[10, 10, 10]),
        structure=StructureSpec(family=StructureFamily.HCP_SPHERICAL_PORES, pore_diameter_mm=1.0),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.6)),
        generation=GenerationSpec(final_resolution_mm=0.05),
    )
    estimate = estimate_resources(spec, 0.05, available_mb=100.0)
    assert estimate.status.value == "infeasible"
    assert estimate.voxel_count == 8_000_000


def test_resource_estimate_safe_for_small_grid():
    spec = DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[2, 2, 2]),
        structure=StructureSpec(family=StructureFamily.GYROID, unit_cell_size_mm=1.0),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.6)),
    )
    estimate = estimate_resources(spec, 0.2, available_mb=10_000.0)
    assert estimate.status.value == "feasible"
