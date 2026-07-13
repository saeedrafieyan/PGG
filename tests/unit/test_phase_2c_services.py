import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import trimesh

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
from porous_designer.exporters.stl_exporter import export_stl
from porous_designer.services.mesh_optimization import (
    OptimizationThresholds,
    bidirectional_surface_deviation,
    validate_optimization_pair,
)
from porous_designer.services.phase_2c import cylinder_accuracy_study, determinism_study
from porous_designer.services.sensitivity_service import run_resolution_sensitivity


def _small_tpms_spec(tmp_path: Path) -> DesignSpecification:
    return DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[3, 3, 3]),
        structure=StructureSpec(family=StructureFamily.GYROID, unit_cell_size_mm=1.5),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.6, tolerance=0.2)),
        constraints=ConstraintsSpec(require_open_pores=False),
        generation=GenerationSpec(preview_resolution_mm=0.3, final_resolution_mm=0.3),
        export=ExportSpec(output_directory=str(tmp_path), output_name="det_small"),
    )


def test_bidirectional_surface_deviation_is_symmetric_for_identical_mesh():
    mesh = trimesh.creation.icosphere(subdivisions=2)
    stats = bidirectional_surface_deviation(mesh, mesh.copy(), sample_count=64, seed=7)
    assert stats["master_to_candidate"]["max"] == 0.0
    assert stats["candidate_to_master"]["max"] == 0.0
    assert stats["bidirectional"]["max"] == 0.0


def test_validate_optimization_pair_accepts_identical_mesh(tmp_path: Path):
    mesh = trimesh.creation.box(extents=(1, 1, 1))
    master = tmp_path / "master.stl"
    candidate = tmp_path / "candidate.stl"
    export_stl(mesh, master)
    export_stl(mesh.copy(), candidate)
    result = validate_optimization_pair(
        master,
        candidate,
        domain_volume_mm3=1.0,
        thresholds=OptimizationThresholds(sample_count=32),
    )
    assert result["accepted"]
    assert result["surface_deviation"]["bidirectional"]["max"] == 0.0


def test_determinism_study_reports_classification(tmp_path: Path):
    spec = _small_tpms_spec(tmp_path)
    result = determinism_study(spec, runs=2, output_dir=tmp_path / "determinism")
    assert result["classification"] in {"bitwise deterministic", "numerically deterministic"}
    assert len(result["runs"]) == 2
    assert "stl_sha256" in result["runs"][0]


def test_cylinder_accuracy_improves_with_resolution(tmp_path: Path):
    result = cylinder_accuracy_study(
        diameter_mm=4.0,
        height_mm=4.0,
        resolutions=[0.4, 0.2],
        output_dir=tmp_path / "cylinder",
    )
    coarse, fine = result["rows"]
    assert fine["volume_error_fraction"] <= coarse["volume_error_fraction"]
    assert "minimum_recommended_resolution_mm" in fine


def test_sensitivity_records_deltas_against_finest_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    spec = _small_tpms_spec(tmp_path)

    def fake_generate(run_spec: DesignSpecification, profile):
        res = run_spec.generation.final_resolution_mm
        return SimpleNamespace(
            success=True,
            run_id=f"run-{res}",
            lattice_spacing_mm=1.0 + res,
            final_voxel_porosity=0.5 + res,
            final_mesh_porosity=0.6 + res,
            solid_components=1,
            connectivity={
                "pore_component_count": 1,
                "pore_connected_x": True,
                "pore_connected_y": True,
                "pore_connected_z": True,
            },
            triangle_count=int(1000 / res),
            timing=SimpleNamespace(total_s=1.0),
            peak_memory_mb=2.0,
            stl_sha256=f"sha-{res}",
            stl_path=tmp_path / f"mesh-{res}.stl",
        )

    monkeypatch.setattr("porous_designer.services.sensitivity_service.generate_porous_stl", fake_generate)
    result = run_resolution_sensitivity(spec, resolutions=[0.2, 0.1], output_dir=tmp_path / "sensitivity")
    payload = json.loads((result.output_dir / "sensitivity.json").read_text(encoding="utf-8"))

    assert result.reference_resolution_mm == 0.1
    assert payload["reference_resolution_mm"] == 0.1
    assert payload["rows"][0]["delta_vs_finest"]["control_parameter"] == pytest.approx(0.1)
    assert payload["rows"][1]["delta_vs_finest"]["triangle_count"] == 0
