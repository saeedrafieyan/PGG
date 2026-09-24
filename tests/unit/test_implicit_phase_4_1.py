"""Phase 4.1: implicit field kernel, new families, domains, grading, exports."""

from __future__ import annotations

import zipfile

import numpy as np
import pytest
import trimesh

from porous_designer.domain.enums import DomainShape, GradingMode, SkinMode, StructureFamily, TPMSVariant
from porous_designer.domain.specification import (
    DesignSpecification,
    DomainSpec,
    GenerationSpec,
    GradingSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
)
from porous_designer.exporters.threemf_exporter import export_3mf
from porous_designer.geometry.phantoms import wound_cavity_phantom
from porous_designer.geometry.voxel import remove_detached_fragments
from porous_designer.implicit.backend import NumpyOps, cuda_available, select_backend
from porous_designer.implicit.calibration import calibration_for
from porous_designer.implicit.domain_sdf import GridGeometry, domain_sdf_grid, mesh_sdf_grid
from porous_designer.implicit.field import FieldModel
from porous_designer.implicit.grading import graded_value, normalized_coordinate
from porous_designer.implicit.meshing import field_to_mesh
from porous_designer.implicit.struts import STRUT_KINDS, brute_force_distance, strut_distance
from porous_designer.implicit.tpms import SURFACES

OPS = NumpyOps()
TPMS_FAMILIES = [f for f in StructureFamily if f.is_tpms]
STRUT_FAMILIES = [f for f in StructureFamily if f.is_strut_lattice]


def _spec(family: StructureFamily, domain: DomainSpec | None = None, **structure) -> DesignSpecification:
    kwargs = {"unit_cell_size_mm": 2.0} if family.uses_unit_cell else {"pore_diameter_mm": 1.0}
    kwargs.update(structure)
    return DesignSpecification(
        domain=domain or DomainSpec(shape=DomainShape.BOX, dimensions_mm=[4.0, 4.0, 4.0]),
        structure=StructureSpec(family=family, **kwargs),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.7, tolerance=0.02)),
        generation=GenerationSpec(preview_resolution_mm=0.2, final_resolution_mm=0.1, compute_backend="cpu"),
    )


# --------------------------------------------------------------------------- TPMS
@pytest.mark.parametrize("family", TPMS_FAMILIES, ids=lambda f: f.value)
def test_tpms_analytic_gradient_matches_finite_differences(family):
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 2 * np.pi, size=(3, 400))
    f, gx, gy, gz = SURFACES[family](OPS, *[np.asarray(a, dtype=np.float64) for a in p])
    h = 1e-6
    for axis, g in enumerate((gx, gy, gz)):
        plus, minus = p.copy(), p.copy()
        plus[axis] += h
        minus[axis] -= h
        numeric = (SURFACES[family](OPS, *plus)[0] - SURFACES[family](OPS, *minus)[0]) / (2 * h)
        assert np.max(np.abs(numeric - g)) < 1e-6


@pytest.mark.parametrize("family", TPMS_FAMILIES, ids=lambda f: f.value)
def test_tpms_calibration_is_monotone_and_spans_useful_range(family):
    for variant in TPMSVariant:
        curve = calibration_for(family, variant)
        assert np.all(np.diff(curve.porosity) <= 1e-12)
        lo, hi = curve.porosity_range
        assert lo < 0.35 and hi > 0.85, (variant, lo, hi)
        # The inverse recovers the parameter for an interior porosity.
        tau = float(curve.parameter_for(0.7))
        assert abs(float(curve.porosity_at(tau)) - 0.7) < 0.01


# ------------------------------------------------------------------------ struts
@pytest.mark.parametrize("family", STRUT_FAMILIES, ids=lambda f: f.value)
def test_strut_distance_is_exact_against_brute_force(family):
    kind = STRUT_KINDS[family]
    rng = np.random.default_rng(7)
    points = rng.uniform(-1.5, 2.5, size=(3000, 3))
    fast = strut_distance(OPS, kind, *(points[:, i].astype(np.float64) for i in range(3)))
    reference = brute_force_distance(kind, points)
    assert np.max(np.abs(fast - reference)) < 1e-7


# ------------------------------------------------------------------ domains/SDF
def test_mesh_sdf_matches_analytic_sphere():
    radius = 3.0
    mesh = trimesh.creation.icosphere(subdivisions=4, radius=radius)
    mesh.apply_translation([radius, radius, radius])
    grid = GridGeometry.covering((2 * radius, 2 * radius, 2 * radius), 0.2)
    X, Y, Z = np.meshgrid(grid.axis(0), grid.axis(1), grid.axis(2), indexing="ij")
    exact = np.sqrt((X - radius) ** 2 + (Y - radius) ** 2 + (Z - radius) ** 2) - radius
    sdf = mesh_sdf_grid(mesh, grid)
    band = np.abs(exact) < 0.55  # exact point-triangle band (3 voxels)
    assert np.max(np.abs(sdf[band] - exact[band])) < 0.01  # facet error of the icosphere
    clear = np.abs(exact) > 0.01  # the icosphere's facets lie up to ~0.005 mm inside the sphere
    assert not np.any((sdf[clear] < 0) != (exact[clear] < 0))
    deep = mesh_sdf_grid(mesh, grid, exact_depth_mm=1.5)
    mid = np.abs(exact) < 1.5
    assert np.max(np.abs(deep[mid] - exact[mid])) < 0.03  # e.g. for a 1.5 mm skin


def test_sphere_domain_sdf_and_volume():
    domain = DomainSpec(shape=DomainShape.SPHERE, dimensions_mm=[6.0])
    assert domain.volume_mm3 == pytest.approx(4.0 / 3.0 * np.pi * 27.0)
    grid = GridGeometry.covering((6.0, 6.0, 6.0), 0.1)
    inside = domain_sdf_grid(domain, grid) <= 0
    assert inside.sum() * 0.1**3 == pytest.approx(domain.volume_mm3, rel=0.01)


def test_mesh_domain_from_file_units(tmp_path):
    path = tmp_path / "part_cm.stl"
    trimesh.creation.box(extents=[1.0, 2.0, 0.5]).export(path)
    domain = DomainSpec.from_mesh_file(path, units="cm")
    assert domain.shape == DomainShape.MESH
    assert domain.dimensions_mm == pytest.approx([10.0, 20.0, 5.0])
    assert domain.volume_mm3 == pytest.approx(1000.0, rel=1e-6)


def test_yaml_mesh_domain_resolves_relative_path_and_measures_extents(tmp_path):
    trimesh.creation.box(extents=[2.0, 3.0, 4.0]).export(tmp_path / "part.stl")
    (tmp_path / "spec.yaml").write_text(
        "domain: {shape: mesh, mesh_path: part.stl, mesh_units: cm, dimensions_mm: [1, 1, 1]}\n"
        "structure: {family: gyroid, unit_cell_size_mm: 2.0}\n"
        "targets: {porosity_target: {target: 0.7}}\n",
        encoding="utf-8",
    )
    spec = DesignSpecification.from_yaml_file(tmp_path / "spec.yaml")
    assert spec.domain.mesh_path == str((tmp_path / "part.stl").resolve())
    assert spec.domain.dimensions_mm == pytest.approx([20.0, 30.0, 40.0])  # the file wins


def test_wound_phantom_is_closed_and_sized():
    mesh = wound_cavity_phantom(20.0, 12.0, 4.0, seed=3)
    assert mesh.is_watertight and mesh.volume > 0
    assert mesh.bounds[1][2] == pytest.approx(0.0, abs=0.05)  # skin plane
    ext = mesh.extents
    assert 17.0 < ext[0] < 24.0 and 10.0 < ext[1] < 15.0 and 3.0 < ext[2] < 5.5


# ----------------------------------------------------------------------- grading
def test_linear_and_radial_grading_coordinates():
    xs = np.linspace(0, 4, 5)
    X, Y, Z = np.meshgrid(xs, xs, xs, indexing="ij")
    linear = GradingSpec(mode=GradingMode.LINEAR, axis="z", start=0.5, end=0.8)
    s = normalized_coordinate(linear, (X, Y, Z), (4.0, 4.0, 4.0), None)
    assert s.min() == pytest.approx(0.0) and s.max() == pytest.approx(1.0)
    assert np.allclose(s[:, :, 2], 0.5)
    assert np.allclose(graded_value(linear, s)[:, :, -1], 0.8)
    radial = GradingSpec(mode=GradingMode.RADIAL, axis="z", start=0.5, end=0.8)
    r = normalized_coordinate(radial, (X, Y, Z), (4.0, 4.0, 4.0), None)
    assert r[2, 2, 0] == pytest.approx(0.0) and r.max() == pytest.approx(1.0)


def test_surface_grading_requires_depth():
    with pytest.raises(ValueError):
        GradingSpec(mode=GradingMode.SURFACE_DISTANCE, start=0.5, end=0.8)


def test_graded_porosity_profile_follows_target():
    spec = _spec(StructureFamily.GYROID)
    spec.targets.porosity_grading = GradingSpec(mode=GradingMode.LINEAR, axis="z", start=0.55, end=0.85)
    model = FieldModel.build(spec, 0.08)
    problem = model.control_problem()
    assert problem.name == "porosity_shift"
    profile = model.porosity_profile(0.0)
    achieved = [row["achieved"] for row in profile]
    assert achieved[-1] - achieved[0] > 0.2
    assert all(abs(row["achieved"] - row["target"]) < 0.06 for row in profile)


def test_grading_rejected_for_sphere_lattices_and_fixed_thickness():
    with pytest.raises(ValueError):
        spec = _spec(StructureFamily.HCP_SPHERICAL_PORES)
        DesignSpecification.model_validate(
            {**spec.model_dump(), "targets": {"porosity_target": {"target": 0.7}, "porosity_grading": {"start": 0.5, "end": 0.8}}}
        )
    with pytest.raises(ValueError):
        spec = _spec(StructureFamily.GYROID, wall_thickness_mm=0.2)
        DesignSpecification.model_validate(
            {**spec.model_dump(), "targets": {"porosity_target": {"target": 0.7}, "porosity_grading": {"start": 0.5, "end": 0.8}}}
        )


# ------------------------------------------------------------------ field model
@pytest.mark.parametrize(
    "family,variant,control",
    [
        (StructureFamily.GYROID, TPMSVariant.SHEET, "tau"),
        (StructureFamily.DIAMOND, TPMSVariant.NETWORK, "kappa"),
        (StructureFamily.STRUT_OCTET, TPMSVariant.SHEET, "tau"),
        (StructureFamily.VORONOI_FOAM, TPMSVariant.SHEET, "tau"),
        (StructureFamily.BCC_SPHERICAL_PORES, TPMSVariant.SHEET, "lattice_spacing_mm"),
    ],
)
def test_field_model_porosity_is_monotone_in_control(family, variant, control):
    spec = _spec(family, tpms_variant=variant) if family.is_tpms else _spec(family)
    model = FieldModel.build(spec, 0.1)
    problem = model.control_problem()
    assert problem.name == control
    values = np.linspace(problem.lo, problem.hi, 9)
    porosity = np.array([model.porosity(v) for v in values])
    steps = np.diff(porosity)
    assert np.all(steps <= 1e-9) if problem.decreasing else np.all(steps >= -1e-9)


def test_skin_region_excludes_core_from_porosity():
    domain = DomainSpec(shape=DomainShape.CYLINDER, dimensions_mm=[6.0, 4.0], skin_thickness_mm=0.5, skin_mode=SkinMode.LATERAL)
    model = FieldModel.build(_spec(StructureFamily.GYROID, domain), 0.1)
    assert model.skin is not None
    assert model.porous_region.sum() < model.inside.sum()
    # Lateral skin leaves the top and bottom open: the core reaches z = 0.
    top_layer = model.porous_region[:, :, 1]
    assert top_layer.any()


def test_fixed_thickness_makes_porosity_a_result():
    spec = _spec(StructureFamily.PRIMITIVE, wall_thickness_mm=0.3)
    assert spec.structure.fixed_thickness
    problem = FieldModel.build(spec, 0.1).control_problem()
    assert problem.fixed is not None and problem.fixed == pytest.approx(0.15)


# ----------------------------------------------------------------------- meshing
@pytest.mark.parametrize("tau", [0.05, 0.08, 0.12, 0.2, 0.3])
def test_field_to_mesh_is_watertight_across_thicknesses(tau):
    model = FieldModel.build(_spec(StructureFamily.GYROID), 0.1)
    result = field_to_mesh(model.field(tau), 0.1, origin_mm=model.grid.origin_mm)
    assert result.watertight
    # Walls thinner than a voxel meet the domain face slightly inside it.
    assert result.mesh.bounds[0] == pytest.approx([0, 0, 0], abs=1e-3)
    assert result.mesh.bounds[1] == pytest.approx([4, 4, 4], abs=1e-3)


def test_field_to_mesh_keeps_internal_cavities_as_void():
    # A solid cube with a closed spherical cavity: the cavity must reduce the volume.
    h = 0.1
    xs = (np.arange(40) + 0.5) * h
    X, Y, Z = np.meshgrid(xs, xs, xs, indexing="ij")
    cube = np.maximum.reduce([np.abs(X - 2) - 1.5, np.abs(Y - 2) - 1.5, np.abs(Z - 2) - 1.5])
    cavity = 0.8 - np.sqrt((X - 2) ** 2 + (Y - 2) ** 2 + (Z - 2) ** 2)
    result = field_to_mesh(np.maximum(cube, cavity).astype(np.float32), h)
    expected = 27.0 - 4.0 / 3.0 * np.pi * 0.8**3
    assert result.volume_mm3 == pytest.approx(expected, rel=0.01)


def test_remove_detached_fragments_keeps_main_body():
    grid = np.zeros((20, 20, 20), dtype=bool)
    grid[2:18, 2:18, 2:18] = True
    grid[0, 0, 0] = True  # a one-voxel fragment
    cleaned, report = remove_detached_fragments(grid, max_removed_solid_fraction=0.02)
    assert report.accepted and report.removed_component_count == 1
    assert not cleaned[0, 0, 0] and cleaned[10, 10, 10]
    big = grid.copy()
    big[0:2, 0:20, 0:1] = True  # a large second body
    big[1, :, :] = False
    _, report = remove_detached_fragments(big, max_removed_solid_fraction=0.0001)
    assert not report.accepted


# ------------------------------------------------------------------------ exports
def test_3mf_declares_millimetres_and_round_trips(tmp_path):
    mesh = trimesh.creation.box(extents=[3.0, 4.0, 5.0])
    result = export_3mf(mesh, tmp_path / "part.3mf")
    with zipfile.ZipFile(result.path) as z:
        model = z.read("3D/3dmodel.model").decode()
    assert 'unit="millimeter"' in model
    loaded = trimesh.load(result.path, force="mesh")
    assert loaded.volume == pytest.approx(60.0, rel=1e-6)
    assert result.triangle_count == 12


def test_faceted_step_export_round_trips(tmp_path):
    pytest.importorskip("gmsh")
    from porous_designer.exporters.step_exporter import export_faceted_step

    mesh = trimesh.creation.icosphere(subdivisions=2, radius=2.0)
    result = export_faceted_step(mesh, tmp_path / "part.step", max_triangles=5000)
    assert result.status == "exported", result.message
    assert result.path.exists() and result.path.read_text(errors="ignore").startswith("ISO-10303-21")
    assert result.step_volume_mm3 == pytest.approx(mesh.volume, rel=0.01)


# ----------------------------------------------------------------------- backend
def test_backend_selection_falls_back_to_cpu():
    assert select_backend("cpu").name == "numpy"
    assert select_backend("auto", point_count=10).name == "numpy"
    choice = select_backend("cuda")
    assert choice.name == ("torch" if cuda_available() else "numpy")


@pytest.mark.skipif(not cuda_available(), reason="CUDA not available")
@pytest.mark.parametrize("family", [StructureFamily.GYROID, StructureFamily.LIDINOID, StructureFamily.STRUT_KELVIN])
def test_cpu_and_cuda_fields_agree(family):
    cpu = _spec(family)
    gpu = cpu.model_copy(deep=True)
    gpu.generation.compute_backend = "cuda"
    a = FieldModel.build(cpu, 0.1)
    b = FieldModel.build(gpu, 0.1)
    control = 0.5 * (a.control_problem().lo + a.control_problem().hi) if family.is_strut_lattice else 0.1
    fa, fb = a.field(control), b.field(control)
    near = np.abs(fa) < 0.2
    assert np.max(np.abs(fa[near] - fb[near])) < 1e-4
    assert a.porosity(control) == pytest.approx(b.porosity(control), abs=1e-4)
