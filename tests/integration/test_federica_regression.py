"""Integration and regression tests for Phase 2A pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import trimesh

from porous_designer.domain.specification import DesignSpecification
from porous_designer.geometry.mesh import load_stl
from porous_designer.services.generation_service import GenerationProfile, generate_sphere_lattice_stl

FIXTURES = Path(__file__).parent.parent / "fixtures"
BASELINE = json.loads((FIXTURES / "federica_baseline_metrics.json").read_text(encoding="utf-8"))
EXPECT = BASELINE["phase_2a_voxel_stl_expectations"]


@pytest.fixture
def federica_spec() -> DesignSpecification:
    return DesignSpecification.from_yaml_file(FIXTURES / "federica_regression.yaml")


@pytest.mark.slow
def test_federica_regression(federica_spec):
    import shutil

    out_base = Path("runs/_test_integration")
    if out_base.exists():
        shutil.rmtree(out_base)
    out_base.mkdir(parents=True)
    federica_spec.export.output_directory = str(out_base)
    result = generate_sphere_lattice_stl(federica_spec, profile=GenerationProfile.FINAL)

    assert result.success, f"Generation failed: {result.messages}"
    assert result.stl_path is not None
    assert result.stl_path.exists()

    lo, hi = EXPECT["spacing_mm_range"]
    assert lo <= result.lattice_spacing_mm <= hi
    # must be solver output, not a hard-coded constant check by value equality alone
    assert result.tuning is not None
    assert len(result.tuning.iterations) >= 1

    assert 0.75 <= result.final_mesh_porosity <= 0.80
    assert result.watertight
    assert result.solid_components == 1
    assert result.triangle_count >= EXPECT["triangle_count_range"][0]
    assert result.triangle_count <= EXPECT["triangle_count_range"][1]

    mesh = load_stl(result.stl_path)
    dims = mesh.bounds[1] - mesh.bounds[0]
    assert abs(dims[0] - 8.0) <= EXPECT["dimension_tolerance_mm"]
    assert abs(dims[1] - 14.0) <= EXPECT["dimension_tolerance_mm"]
    assert abs(dims[2] - 8.0) <= EXPECT["dimension_tolerance_mm"]
    assert mesh.volume > 0

    # pore connectivity reported
    assert result.connectivity.get("pore_connected_x") or result.connectivity.get("pore_connected_y")

    # provenance files
    assert (result.run_dir / "tuning_history.csv").exists()
    assert (result.run_dir / "validation_report.json").exists()
    assert (result.run_dir / "checksums.json").exists()
    checksums = json.loads((result.run_dir / "checksums.json").read_text())
    assert checksums["step_status"] in {"disabled_phase_2a", "disabled_phase_2b"}
    assert checksums["legacy_federica_step_fixture"]["validation_status"] == "FAILED"


@pytest.mark.slow
def test_federica_deterministic_repeat(federica_spec):
    import shutil

    out_base = Path("runs/_test_integration_det")
    if out_base.exists():
        shutil.rmtree(out_base)
    out_base.mkdir(parents=True)
    federica_spec.export.output_directory = str(out_base)

    r1 = generate_sphere_lattice_stl(federica_spec, profile=GenerationProfile.FINAL)
    federica_spec2 = DesignSpecification.from_yaml_file(FIXTURES / "federica_regression.yaml")
    federica_spec2.export.output_directory = str(out_base)
    r2 = generate_sphere_lattice_stl(federica_spec2, profile=GenerationProfile.FINAL)

    assert r1.lattice_spacing_mm == pytest.approx(r2.lattice_spacing_mm, rel=1e-6)
    assert r1.final_voxel_porosity == pytest.approx(r2.final_voxel_porosity, rel=1e-6)
    assert r1.final_mesh_porosity == pytest.approx(r2.final_mesh_porosity, rel=1e-5)
    assert r1.triangle_count == r2.triangle_count
    assert r1.stl_sha256 == r2.stl_sha256


def test_preview_faster_than_final(federica_spec):
    import shutil

    out_base = Path("runs/_test_integration_prev")
    if out_base.exists():
        shutil.rmtree(out_base)
    out_base.mkdir(parents=True)
    federica_spec.export.output_directory = str(out_base)
    prev = generate_sphere_lattice_stl(federica_spec, profile=GenerationProfile.PREVIEW)
    spec2 = DesignSpecification.from_yaml_file(FIXTURES / "federica_regression.yaml")
    spec2.export.output_directory = str(out_base)
    final = generate_sphere_lattice_stl(spec2, profile=GenerationProfile.FINAL)
    assert prev.triangle_count < final.triangle_count
