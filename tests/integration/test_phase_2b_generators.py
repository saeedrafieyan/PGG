from pathlib import Path

from porous_designer.domain.enums import DomainShape, StructureFamily
from porous_designer.domain.specification import (
    ConstraintsSpec,
    DesignSpecification,
    DomainSpec,
    ExportSpec,
    GenerationSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
)
from porous_designer.services.generation_service import GenerationProfile, generate_porous_stl


def _spec(family, domain, *, pore=None, unit=None, target=0.6, tol=0.15):
    return DesignSpecification(
        domain=domain,
        structure=StructureSpec(
            family=family,
            pore_diameter_mm=pore,
            unit_cell_size_mm=unit,
        ),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=target, tolerance=tol)),
        constraints=ConstraintsSpec(require_open_pores=False),
        generation=GenerationSpec(preview_resolution_mm=0.2, final_resolution_mm=0.2),
        export=ExportSpec(output_directory="runs/_test_phase_2b", output_name=family.value),
    )


def test_gyroid_box_generation():
    spec = _spec(
        StructureFamily.GYROID,
        DomainSpec(shape=DomainShape.BOX, dimensions_mm=[4, 4, 4]),
        unit=2.0,
        target=0.65,
    )
    result = generate_porous_stl(spec, profile=GenerationProfile.FINAL)
    assert result.success
    assert result.stl_path and result.stl_path.exists()
    assert result.watertight


def test_primitive_cylinder_generation():
    spec = _spec(
        StructureFamily.PRIMITIVE,
        DomainSpec(shape=DomainShape.CYLINDER, dimensions_mm=[4, 5]),
        unit=2.0,
        target=0.65,
    )
    result = generate_porous_stl(spec, profile=GenerationProfile.FINAL)
    assert result.success
    assert result.stl_path and result.stl_path.exists()
    assert result.connectivity["solid_component_count"] == 1


def test_diamond_and_primitive_box_generation():
    for family in (StructureFamily.DIAMOND, StructureFamily.PRIMITIVE):
        spec = _spec(
            family,
            DomainSpec(shape=DomainShape.BOX, dimensions_mm=[4, 4, 4]),
            unit=2.0,
            target=0.65,
        )
        result = generate_porous_stl(spec, profile=GenerationProfile.FINAL)
        assert result.success
        assert result.triangle_count > 0


def test_hcp_cylinder_case_reports_metrics():
    spec = _spec(
        StructureFamily.HCP_SPHERICAL_PORES,
        DomainSpec(shape=DomainShape.CYLINDER, dimensions_mm=[5, 6]),
        pore=0.5,
        target=0.2,
        tol=0.3,
    )
    config = {
        "validation": {
            "dimension_tolerance_mm": 0.05,
            "porosity_tolerance_default": 0.3,
            "max_porosity_method_disagreement": 0.25,
            "porosity_disagreement_policy": "warn",
            "minimum_solid_component_voxels": 8,
        },
        "resources": {"warning_memory_fraction": 0.9, "maximum_memory_fraction": 0.99},
    }
    result = generate_porous_stl(spec, profile=GenerationProfile.FINAL, config=config)
    assert result.stl_path and result.stl_path.exists()
    assert result.connectivity["solid_component_count"] == 1
    assert result.resource_estimate is not None
