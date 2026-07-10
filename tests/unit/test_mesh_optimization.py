from pathlib import Path

import pytest
import trimesh

from porous_designer.exporters.stl_exporter import export_stl
from porous_designer.services.mesh_optimization import (
    OptimizationProfile,
    deterministic_surface_deviation,
    optimize_and_validate_mesh,
)


def test_surface_deviation_identical_mesh_is_zero():
    mesh = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    deviation = deterministic_surface_deviation(mesh, mesh.copy(), sample_count=128)
    assert deviation == pytest.approx(0.0, abs=1e-9)


def test_optimization_none_preserves_master(tmp_path: Path):
    mesh = trimesh.creation.box(extents=(1, 1, 1))
    master = tmp_path / "master.stl"
    export_stl(mesh, master)
    result, export = optimize_and_validate_mesh(
        mesh,
        master_path=master,
        optimized_path=tmp_path / "optimized.stl",
        domain_volume_mm3=1.0,
        profile=OptimizationProfile.NONE,
    )
    assert not result.accepted
    assert result.recommended_path == master
    assert export is None


def test_optimization_rejection_on_tight_threshold(tmp_path: Path):
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    master = tmp_path / "master.stl"
    export_stl(mesh, master)
    result, _export = optimize_and_validate_mesh(
        mesh,
        master_path=master,
        optimized_path=tmp_path / "optimized.stl",
        domain_volume_mm3=8.0,
        profile=OptimizationProfile.CONSERVATIVE,
    )
    assert result.recommended_path == master or result.accepted
