"""Phase 4.1 end-to-end generation: new families, domains, grading, skins, exports."""

from __future__ import annotations

import json

import numpy as np
import pytest
import trimesh

from porous_designer.cli import main as cli_main
from porous_designer.domain.enums import DomainShape, ExportFormat, GradingMode, SkinMode, StructureFamily, TPMSVariant
from porous_designer.domain.specification import (
    ConstraintsSpec,
    DesignSpecification,
    DomainSpec,
    ExportSpec,
    GenerationSpec,
    GradingSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
)
from porous_designer.geometry.phantoms import wound_cavity_phantom
from porous_designer.services.generation_service import GenerationProfile, generate_porous_stl

BOX = DomainSpec(shape=DomainShape.BOX, dimensions_mm=[4.0, 4.0, 4.0])


def _run(tmp_path, family, domain=BOX, *, target=0.7, res=0.1, formats=(ExportFormat.STL,), open_pores=True, targets=None, **structure):
    if family.uses_unit_cell:
        structure.setdefault("unit_cell_size_mm", 1.5)
    else:
        structure.setdefault("pore_diameter_mm", 1.0)
    spec = DesignSpecification(
        domain=domain,
        structure=StructureSpec(family=family, **structure),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=target, tolerance=0.02), **(targets or {})),
        constraints=ConstraintsSpec(require_open_pores=open_pores),
        generation=GenerationSpec(preview_resolution_mm=0.2, final_resolution_mm=res, compute_backend="cpu", step_max_triangles=8000),
        export=ExportSpec(output_directory=str(tmp_path), output_name=family.value, formats=list(formats)),
    )
    result = generate_porous_stl(spec, profile=GenerationProfile.FINAL)
    checks = json.loads((result.run_dir / "validation_report.json").read_text())["checks"] if (result.run_dir / "validation_report.json").exists() else []
    return result, {c["name"]: c for c in checks}


def _assert_part(result, checks, target=0.7):
    failing = {n: c["achieved_value"] for n, c in checks.items() if c["status"] == "fail"}
    assert result.success, (result.messages, failing)
    assert result.watertight and result.solid_components == 1
    assert abs(result.final_mesh_porosity - target) <= 0.02
    mesh = trimesh.load(result.stl_path)
    assert mesh.is_watertight


@pytest.mark.parametrize(
    "family,variant",
    [
        (StructureFamily.IWP, TPMSVariant.SHEET),
        (StructureFamily.NEOVIUS, TPMSVariant.SHEET),
        (StructureFamily.FISCHER_KOCH_S, TPMSVariant.SHEET),
        (StructureFamily.LIDINOID, TPMSVariant.SHEET),
        (StructureFamily.GYROID, TPMSVariant.NETWORK),
    ],
    ids=lambda v: getattr(v, "value", v),
)
def test_new_tpms_families(tmp_path, family, variant):
    result, checks = _run(tmp_path, family, tpms_variant=variant, unit_cell_size_mm=2.0)
    _assert_part(result, checks)
    assert result.control_parameter_name == ("kappa" if variant == TPMSVariant.NETWORK else "tau")


@pytest.mark.parametrize("family", [f for f in StructureFamily if f.is_strut_lattice], ids=lambda f: f.value)
def test_strut_lattices(tmp_path, family):
    result, checks = _run(tmp_path, family, target=0.75, unit_cell_size_mm=2.0)
    _assert_part(result, checks, target=0.75)


def test_voronoi_foam_in_sphere_is_deterministic(tmp_path):
    domain = DomainSpec(shape=DomainShape.SPHERE, dimensions_mm=[5.0])
    first, checks = _run(tmp_path / "a", StructureFamily.VORONOI_FOAM, domain, unit_cell_size_mm=1.2)
    _assert_part(first, checks)
    second, _ = _run(tmp_path / "b", StructureFamily.VORONOI_FOAM, domain, unit_cell_size_mm=1.2)
    assert first.stl_sha256 == second.stl_sha256
    ext = trimesh.load(first.stl_path).extents
    assert np.all(ext <= 5.0 + 1e-6) and np.all(ext > 4.6)


def test_radial_porosity_grading(tmp_path):
    domain = DomainSpec(shape=DomainShape.CYLINDER, dimensions_mm=[6.0, 4.0])
    grading = GradingSpec(mode=GradingMode.RADIAL, axis="z", start=0.85, end=0.55)
    result, checks = _run(tmp_path, StructureFamily.GYROID, domain, targets={"porosity_grading": grading})
    assert result.success, result.messages
    assert result.control_parameter_name == "porosity_shift"
    # The outermost band is cut by the cylinder wall and may deviate a little (warning).
    assert checks["porosity_grading_profile"]["status"] in {"pass", "warning"}
    profile = json.loads((result.run_dir / "blackboard.json").read_text())["geometry_metrics"]["porosity_profile"]
    assert all(abs(row["achieved"] - row["target"]) < 0.025 for row in profile[:-1])
    assert profile[0]["achieved"] > profile[-2]["achieved"] + 0.12  # porous centre, dense rim


def test_cell_size_grading(tmp_path):
    grading = GradingSpec(axis="z", start=1.0, end=2.0)
    result, checks = _run(tmp_path, StructureFamily.STRUT_OCTET, unit_cell_size_mm=1.5, cell_size_grading=grading)
    _assert_part(result, checks)


def test_fixed_wall_thickness_reports_porosity(tmp_path):
    result, checks = _run(tmp_path, StructureFamily.PRIMITIVE, unit_cell_size_mm=2.0, wall_thickness_mm=0.3)
    assert result.success, result.messages
    assert checks["porosity_mesh_volume"]["requested_value"] == "result (geometry fixed)"
    assert 0.5 < result.final_mesh_porosity < 0.95


def test_lateral_skin_keeps_axial_percolation(tmp_path):
    domain = DomainSpec(shape=DomainShape.CYLINDER, dimensions_mm=[6.0, 4.0], skin_thickness_mm=0.4, skin_mode=SkinMode.LATERAL)
    result, checks = _run(tmp_path, StructureFamily.GYROID, domain)
    _assert_part(result, checks)
    assert checks["pore_percolation_z"]["status"] == "pass"
    assert checks["pore_percolation_x"]["requested_value"] is None  # closed by the skin, not required
    ext = trimesh.load(result.stl_path).extents
    assert ext[0] == pytest.approx(6.0, abs=0.05)  # the skin restores the full diameter


def test_mesh_domain_wound_phantom_with_skin(tmp_path):
    path = tmp_path / "wound.stl"
    wound_cavity_phantom(12.0, 8.0, 3.0, seed=1).export(path)
    domain = DomainSpec.from_mesh_file(path, skin_thickness_mm=0.3)
    result, checks = _run(tmp_path, StructureFamily.GYROID, domain, res=0.1, open_pores=False, unit_cell_size_mm=1.5)
    _assert_part(result, checks)
    # The part keeps the coordinates of the source mesh (it overlays the scan).
    part = trimesh.load(result.stl_path)
    source = trimesh.load(path)
    assert np.allclose(part.bounds, source.bounds, atol=0.06)
    # The porosity applies to the core; the solid skin adds material on top.
    assert part.volume > source.volume * (1 - result.final_mesh_porosity)


def test_infeasible_thin_walls_are_reported(tmp_path):
    # 90% diamond at a 1.5 mm cell needs ~0.07 mm sheets: below a 0.2 mm voxel.
    result, _ = _run(tmp_path, StructureFamily.DIAMOND, target=0.90, res=0.2, unit_cell_size_mm=1.5)
    assert not result.success
    assert result.tuning is not None and not result.tuning.reachable
    assert any("thinner than" in m for m in result.messages)


def test_all_export_formats(tmp_path):
    result, checks = _run(
        tmp_path,
        StructureFamily.PRIMITIVE,
        DomainSpec(shape=DomainShape.BOX, dimensions_mm=[3.0, 3.0, 3.0]),
        res=0.15,
        unit_cell_size_mm=1.5,
        wall_thickness_mm=0.4,
        formats=(ExportFormat.STL, ExportFormat.THREE_MF, ExportFormat.STEP),
    )
    assert result.success, result.messages
    assert result.threemf_path is not None and result.threemf_path.exists()
    assert trimesh.load(result.threemf_path, force="mesh").volume == pytest.approx(trimesh.load(result.stl_path).volume, rel=1e-4)
    status = result.export_status["step"]
    assert status in {"exported", "skipped"}, result.messages
    if status == "exported":
        assert result.step_path.exists()
    else:
        assert any("STEP skipped" in m for m in result.messages)


def test_cli_families_and_phantom(tmp_path, capsys):
    assert cli_main(["families"]) == 0
    out = capsys.readouterr().out
    assert "strut_kelvin" in out and "voronoi_foam" in out and "3mf" in out
    target = tmp_path / "phantom.stl"
    assert cli_main(["make-phantom", str(target), "--length", "10", "--width", "6", "--depth", "2"]) == 0
    assert trimesh.load(target).is_watertight
