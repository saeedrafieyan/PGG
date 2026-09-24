"""Unit tests for DesignSpecification."""

import pytest
from pydantic import ValidationError

from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily
from porous_designer.domain.specification import (
    DesignSpecification,
    DomainSpec,
    ExportSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
    load_legacy_spec,
)


def test_federica_legacy_spec_load():
    spec = load_legacy_spec("sample_spec.txt")
    assert spec.domain.dimensions_mm == [8.0, 14.0, 8.0]
    assert spec.structure.family == StructureFamily.HCP_SPHERICAL_PORES
    assert spec.structure.pore_diameter_mm == 1.0
    assert spec.targets.porosity_target.target == pytest.approx(0.775)
    assert spec.targets.porosity_target.min_value == pytest.approx(0.75)
    assert spec.targets.porosity_target.max_value == pytest.approx(0.80)
    assert ExportFormat.STL in spec.export.formats
    assert ExportFormat.STEP in spec.export.formats


def test_gyroid_accepts_step_export():
    # Phase 4.1: every family can be exported as a faceted STEP solid.
    spec = DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[10, 10, 10]),
        structure=StructureSpec(family=StructureFamily.GYROID, unit_cell_size_mm=2.0),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.5)),
        export=ExportSpec(formats=[ExportFormat.STL, ExportFormat.STEP]),
    )
    assert ExportFormat.STEP in spec.export.formats


def test_cylinder_domain_requires_two_dimensions():
    with pytest.raises(ValidationError):
        DomainSpec(shape=DomainShape.CYLINDER, dimensions_mm=[10, 10, 10])

    spec = DomainSpec(shape=DomainShape.CYLINDER, dimensions_mm=[10, 20])
    assert spec.volume_mm3 == pytest.approx(3.14159 * 25 * 20, rel=1e-3)


def test_spec_yaml_roundtrip():
    import shutil
    from pathlib import Path

    tmp = Path("runs/_test_tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    spec = load_legacy_spec("sample_spec.txt")
    path = tmp / "spec.yaml"
    spec.save_yaml(path)
    loaded = DesignSpecification.from_yaml_file(path)
    assert loaded.structure.family == spec.structure.family
    assert loaded.domain.dimensions_mm == spec.domain.dimensions_mm
    shutil.rmtree(tmp)


def test_porosity_range_midpoint():
    from porous_designer.domain.specification import _parse_porosity

    p = _parse_porosity("75-80%")
    assert p.target == pytest.approx(0.775)
    assert p.min_value == pytest.approx(0.75)
    assert p.max_value == pytest.approx(0.80)
