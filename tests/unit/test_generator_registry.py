from porous_designer.domain.enums import DomainShape, StructureFamily
from porous_designer.generators.registry import generator_registry, get_generator


def test_all_phase_2b_generators_registered():
    registry = generator_registry()
    for family in [
        StructureFamily.SC_SPHERICAL_PORES,
        StructureFamily.BCC_SPHERICAL_PORES,
        StructureFamily.FCC_SPHERICAL_PORES,
        StructureFamily.HCP_SPHERICAL_PORES,
        StructureFamily.GYROID,
        StructureFamily.DIAMOND,
        StructureFamily.PRIMITIVE,
    ]:
        assert family in registry
        assert DomainShape.BOX in registry[family].supported_domains()
        assert DomainShape.CYLINDER in registry[family].supported_domains()


def test_tpms_generator_uses_tpms_terms():
    generator = get_generator(StructureFamily.GYROID)
    description = generator.describe_parameters()
    names = {p["name"] for p in description["parameters"]}
    assert "unit_cell_size_mm" in names
    assert {"tpms_variant", "wall_thickness_mm", "network_offset_mm"} <= names
    assert "pore_diameter_mm" not in names
    assert description["supported_exports"] == ["stl", "3mf", "step"]
