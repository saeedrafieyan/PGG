"""Phase 4.2: measurements, periodic RVEs, flow and stiffness solvers, printability."""

from __future__ import annotations

import csv

import numpy as np
import pytest
import trimesh

from porous_designer.domain.enums import DomainShape, Severity, StructureFamily, TPMSVariant, ValidationStatus
from porous_designer.domain.specification import ConstraintsSpec, DesignSpecification, DomainSpec, PorosityTarget, StructureSpec, TargetsSpec
from porous_designer.implicit.calibration import calibration_for
from porous_designer.metrology import morphology as mm
from porous_designer.metrology.homogenization import effective_stiffness
from porous_designer.metrology.lbm import permeability
from porous_designer.metrology.report import MetrologyReport, metrology_checks
from porous_designer.metrology.rve import measurement_grid, periodic_voronoi_distance, sphere_lattice_rve, unit_cell_rve
from porous_designer.printability.coupon import calibrate_profile, make_coupon, write_coupon
from porous_designer.printability.profiles import all_profiles, get_profile, profile_for
from porous_designer.printability.rules import evaluate_printability, layer_islands, overhang_fraction

N = 40
X, Y, Z = np.meshgrid(*[np.arange(N) + 0.5] * 3, indexing="ij")


# ------------------------------------------------------------------ morphology
@pytest.mark.parametrize("t", [4, 5, 10, 11])
def test_slab_thickness_within_half_voxel(t):
    g = np.zeros((N, N, N), bool)
    g[:, :, 10 : 10 + t] = True
    sd = mm.size_distribution(g, 1.0, "wall")
    assert abs(sd.d50_mm - t) <= 0.5 + 1e-9


def test_channel_pore_percolation_tortuosity_and_closed_pores():
    void = (X - 20) ** 2 + (Y - 20) ** 2 < 36
    assert 10.0 <= mm.percolation_diameter(void, 2, 1.0) <= 12.5
    assert mm.percolation_diameter(void, 0, 1.0) == 0.0  # blocked sideways
    assert mm.geometric_tortuosity(void, 2) == pytest.approx(1.0)
    cavity = (X - 20) ** 2 + (Y - 20) ** 2 + (Z - 20) ** 2 < 25
    closed = mm.closed_pores(~cavity, 1.0)
    assert closed.count == 1 and closed.closed_void_fraction == pytest.approx(1.0)
    assert mm.closed_pores(~void, 1.0).count == 0


def test_intrusion_is_limited_by_the_bottleneck():
    chambers = ((X - 20) ** 2 + (Y - 20) ** 2 < 64) & ((Z < 18) | (Z > 22))
    void = chambers | ((X - 20) ** 2 + (Y - 20) ** 2 < 9)
    d = mm.percolation_diameter(void, 2, 1.0)
    assert 4.0 <= d <= 6.5  # the 6-voxel throat, not the 16-voxel chambers
    curve = mm.intrusion_curve(void, (2,), 1.0)
    assert np.all(np.diff(curve.intruded_fraction) <= 1e-12)
    assert curve.fraction_reached(1.5) == pytest.approx(1.0)


def test_curvature_of_a_sphere():
    h = 0.1
    c = (np.arange(80) + 0.5) * h
    Xs, Ys, Zs = np.meshgrid(c, c, c, indexing="ij")
    field = np.sqrt((Xs - 4) ** 2 + (Ys - 4) ** 2 + (Zs - 4) ** 2) - 2.0
    curv = mm.field_curvature(field.astype(np.float32), h)
    assert curv.mean_curvature_mean_per_mm == pytest.approx(0.5, rel=0.02)
    assert curv.gaussian_curvature_mean_per_mm2 == pytest.approx(0.25, rel=0.03)
    assert curv.saddle_fraction == 0.0


def test_gyroid_surface_is_saddle_shaped():
    rve = unit_cell_rve(StructureFamily.GYROID, TPMSVariant.NETWORK, 0.0, 2.0, n=64)
    from porous_designer.implicit.lattice import periodic_cell_distance

    d = periodic_cell_distance(StructureFamily.GYROID, TPMSVariant.NETWORK, 64) * 2.0
    curv = mm.field_curvature(d.astype(np.float32), rve.voxel_mm)
    assert curv.saddle_fraction > 0.95  # minimal surface: K <= 0 everywhere
    assert abs(curv.mean_curvature_mean_per_mm) < 0.1


# ------------------------------------------------------------------------ RVEs
def test_rve_porosity_matches_calibration_and_analytic_values():
    rve = unit_cell_rve(StructureFamily.GYROID, TPMSVariant.SHEET, 0.1, 2.0)
    assert rve.porosity == pytest.approx(float(calibration_for(StructureFamily.GYROID, TPMSVariant.SHEET).porosity_at(0.1)), abs=0.01)
    sc = sphere_lattice_rve(StructureFamily.SC_SPHERICAL_PORES, 1.0, 1.1)
    # Union of r = 0.55 spheres on a unit cubic lattice: 4/3 pi r^3 - 3 lens volumes.
    lens = np.pi * (4 * 0.55 + 1.0) * (2 * 0.55 - 1.0) ** 2 / 12.0
    assert sc.porosity == pytest.approx(4 / 3 * np.pi * 0.55**3 - 3 * lens, abs=0.005)
    hcp = sphere_lattice_rve(StructureFamily.HCP_SPHERICAL_PORES, 1.0, 0.9)
    # Non-overlapping spheres: HCP packing fraction pi/(3 sqrt 2) x (d/s)^3.
    assert hcp.porosity == pytest.approx(np.pi / (3 * np.sqrt(2)) * 0.9**3, abs=0.01)


def test_periodic_voronoi_tiles_without_seams():
    d = periodic_voronoi_distance(3, 1.0, 7, 16)
    # The field is continuous across the periodic boundary.
    assert np.max(np.abs(d[0] - d[-1])) < 2.5 / 16
    assert np.max(np.abs(d[:, 0] - d[:, -1])) < 2.5 / 16


def test_measurement_grid_keeps_small_rves():
    rve = unit_cell_rve(StructureFamily.GYROID, TPMSVariant.SHEET, 0.1, 2.0)
    grid, h = measurement_grid(rve.solid, rve.voxel_mm)
    assert grid.shape == rve.solid.shape and h == rve.voxel_mm


# ---------------------------------------------------------------------- solvers
@pytest.mark.parametrize("H", [10, 20])
def test_lbm_plane_poiseuille(H):
    s = np.zeros((4, H + 2, 4), bool)
    s[:, 0, :] = s[:, -1, :] = True
    k = permeability(s, 1.0, axis=0).permeability_mm2
    assert k == pytest.approx((H / (H + 2)) * H**2 / 12.0, rel=0.01)


def test_lbm_square_duct_and_viscosity_independence():
    a = 16
    s = np.ones((4, a + 2, a + 2), bool)
    s[:, 1:-1, 1:-1] = False
    exact = (a * a / (a + 2) ** 2) * a * a / 28.454
    k1 = permeability(s, 1.0, axis=0, tau_plus=1.0).permeability_mm2
    k2 = permeability(s, 1.0, axis=0, tau_plus=1.5).permeability_mm2
    assert k1 == pytest.approx(exact, rel=0.02)
    assert k2 == pytest.approx(k1, rel=0.01)


def test_fft_homogenisation_dense_and_laminate():
    dense = effective_stiffness(np.ones((8, 8, 8), bool))
    assert dense.youngs_relative == pytest.approx([1.0, 1.0, 1.0], rel=1e-6)
    assert dense.poisson == pytest.approx([0.3, 0.3, 0.3], rel=1e-6)
    s = np.zeros((16, 16, 16), bool)
    s[:, :, :8] = True
    lam = effective_stiffness(s)
    assert lam.youngs_relative[0] == pytest.approx(0.5, rel=0.01)  # parallel to layers: Voigt
    assert lam.youngs_relative[2] < 0.01  # across layers: Reuss with near-empty void


def test_gyroid_stiffness_in_published_range():
    rve = unit_cell_rve(StructureFamily.GYROID, TPMSVariant.SHEET, 0.1, 2.0)
    res = effective_stiffness(rve.solid)
    assert 0.07 < min(res.youngs_relative) < 0.14  # sheet gyroid, ~30 % relative density
    assert res.converged


# ---------------------------------------------------------------- printability
def test_profiles_and_process_resolution():
    profiles = all_profiles()
    assert {"generic_fdm_0.4", "generic_msla", "generic_volumetric_tomographic"} <= set(profiles)
    assert profile_for("sla", "generic_fdm").id == "generic_msla"
    assert profile_for("fdm", "generic_fdm").id == "generic_fdm_0.4"
    assert profile_for("unknown", "generic_fdm") is None
    assert profile_for("volumetric", "").vial_diameter_mm == 15.0


def test_layer_islands_and_overhangs():
    tower = np.zeros((20, 20, 30), bool)
    tower[5:15, 5:15, :] = True
    assert layer_islands(tower, 0.1, 0.1, 45)["island_count"] == 0
    floating = tower.copy()
    floating[0:3, 0:3, 20:25] = True  # a block in mid-air
    assert layer_islands(floating, 0.1, 0.1, 45)["island_count"] == 1
    box = trimesh.creation.box(extents=[4, 4, 4])
    assert overhang_fraction(box, 45, 0.1) == pytest.approx(0.0)  # only the bottom faces down, on the plate
    table = trimesh.util.concatenate([box, trimesh.creation.box(extents=[10, 10, 1]).apply_translation([0, 0, 2.5])])
    assert overhang_fraction(table, 45, 0.1) > 0.1


def _metrology(wall, throat, closed=0.0):
    rep = MetrologyReport(level="basic", voxel_mm=0.05)
    rep.part = {"percolation_diameter_min_mm": throat, "closed_pores": {"count": int(closed > 0), "closed_void_fraction": closed}, "intrusion": {"diameters_mm": [0.1, 0.5, 1.0], "intruded_fraction": [1.0, 0.99, 0.2]}}
    rep.rve = [{"wall_d10_mm": wall, "pore_d10_mm": throat, "pore_d50_mm": 2 * throat, "wall_d50_mm": wall}]
    return rep


def test_printability_rules_warn_or_fail():
    spec = DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[5, 5, 5]),
        structure=StructureSpec(family=StructureFamily.GYROID, unit_cell_size_mm=2.0),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.7)),
    )
    sla = get_profile("generic_msla")
    mesh = trimesh.creation.box(extents=[5, 5, 5])
    thin = evaluate_printability(spec, sla, metrology=_metrology(0.1, 0.8, closed=0.05), mesh=mesh)
    names = {c.name: c for c in thin.checks}
    assert names["print_min_wall"].status == ValidationStatus.WARNING
    assert names["print_closed_pores"].status == ValidationStatus.WARNING
    assert names["print_drainage"].status == ValidationStatus.PASS
    enforced = evaluate_printability(spec, sla, metrology=_metrology(0.1, 0.8), mesh=mesh, enforce=True)
    wall = next(c for c in enforced.checks if c.name == "print_min_wall")
    assert wall.status == ValidationStatus.FAIL and wall.severity == Severity.CRITICAL
    vol = evaluate_printability(spec, get_profile("generic_volumetric_tomographic"), metrology=_metrology(0.3, 0.2), mesh=trimesh.creation.box(extents=[20, 20, 5]))
    names = {c.name: c for c in vol.checks}
    assert names["print_fits_vial"].status != ValidationStatus.PASS
    assert names["print_stray_dose"].status == ValidationStatus.WARNING


def test_metrology_checks_against_constraints():
    spec = DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[5, 5, 5]),
        structure=StructureSpec(family=StructureFamily.GYROID, unit_cell_size_mm=2.0),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.7)),
        constraints=ConstraintsSpec(minimum_wall_thickness_mm=0.3, minimum_throat_size_mm=0.5),
    )
    checks = {c.name: c for c in metrology_checks(spec, _metrology(0.2, 0.8), percolation_axes=("x", "y", "z"))}
    assert checks["minimum_wall_thickness"].status == ValidationStatus.FAIL
    assert checks["minimum_throat_size"].status == ValidationStatus.PASS


# ----------------------------------------------------------------------- coupon
def test_coupon_is_watertight_and_calibrates(tmp_path, monkeypatch):
    monkeypatch.setenv("AGE_HOME", str(tmp_path / "home"))
    profile = get_profile("generic_msla")
    coupon = make_coupon(profile)
    assert all(m.is_watertight for parts in coupon.rows.values() for m in parts)
    files = write_coupon(coupon, tmp_path / "coupon", profile)
    assert files["coupon"].exists() and files["sheet"].exists()
    with files["sheet"].open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    walls = sorted(float(r["nominal_mm"]) for r in rows if r["row"] == "walls")
    for r in rows:
        v = float(r["nominal_mm"])
        if r["row"] == "walls":
            # a lucky thin one printed, then a gap: the limit is where everything above prints
            r["printed_ok"] = "yes" if v >= walls[3] or v == walls[0] else "no"
        elif r["row"] == "holes":
            r["printed_ok"] = "yes" if v >= 0.54 else "no"
            r["measured_mm"] = f"{v - 0.05:.3f}"
        else:
            r["printed_ok"] = "yes"
    with files["sheet"].open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    cal = calibrate_profile(profile, files["sheet"], "my_resin_printer")
    assert cal.min_wall_mm == pytest.approx(max(walls[3], min(float(r["nominal_mm"]) for r in rows if r["row"] == "pins")))
    assert cal.min_hole_mm == pytest.approx(0.54)
    assert cal.calibration["results"]["holes"]["bias_mm"] == pytest.approx(-0.05)
    assert get_profile("my_resin_printer").calibrated


def test_vial_coupon_rows_fit_the_vial():
    profile = get_profile("generic_volumetric_tomographic")
    coupon = make_coupon(profile)
    for row in coupon.rows:
        ext = coupon.row_mesh(row).extents
        assert np.hypot(ext[0], ext[1]) <= profile.vial_diameter_mm
