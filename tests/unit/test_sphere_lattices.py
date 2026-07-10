"""Tests for sphere lattice center generation."""

import math

import numpy as np
import pytest

from porous_designer.generators.sphere_lattices import (
    LatticeType,
    centers_bcc,
    centers_fcc,
    centers_hcp,
    centers_sc,
    filter_intersecting_centers,
    generate_sphere_centers,
    nearest_neighbor_distances,
    sphere_intersects_box,
)


BOX = (4.0, 4.0, 4.0)
SPACING = 1.0
RADIUS = 0.5


@pytest.mark.parametrize(
    "lattice,fn",
    [
        (LatticeType.SC, centers_sc),
        (LatticeType.BCC, centers_bcc),
        (LatticeType.FCC, centers_fcc),
        (LatticeType.HCP, centers_hcp),
    ],
)
def test_nearest_neighbor_distance(lattice, fn):
    pts = fn(BOX, SPACING, margin=0.0)
    # use interior points away from padding boundary
    interior = pts[(pts[:, 0] > 0.1) & (pts[:, 0] < 3.9)]
    if len(interior) < 2:
        pytest.skip("too few interior points")
    nn = nearest_neighbor_distances(interior)
    assert nn.min() == pytest.approx(SPACING, rel=1e-3)
    assert nn.max() == pytest.approx(SPACING, rel=1e-3)


def test_hcp_abab_layer_spacing():
    pts = centers_hcp((4, 4, 8), SPACING, margin=0.0)
    z_vals = np.unique(np.round(pts[:, 2], 6))
    dz = np.diff(np.sort(z_vals))
    expected_c = SPACING * math.sqrt(2.0 / 3.0)
    for d in dz:
        assert d == pytest.approx(expected_c, rel=1e-3)


def test_no_duplicates():
    for lattice in LatticeType:
        pts = generate_sphere_centers(BOX, SPACING, margin=SPACING, lattice=lattice)
        rounded = np.round(pts, 9)
        unique = np.unique(rounded, axis=0)
        assert len(unique) == len(pts)


def test_filter_intersecting():
    pts = generate_sphere_centers(BOX, SPACING, margin=RADIUS, lattice=LatticeType.SC)
    filtered = filter_intersecting_centers(pts, RADIUS, BOX)
    for c in filtered:
        assert sphere_intersects_box(c, RADIUS, BOX)
    assert len(filtered) <= len(pts)


def test_deterministic_ordering():
    a = generate_sphere_centers(BOX, SPACING, 0.5, LatticeType.FCC)
    b = generate_sphere_centers(BOX, SPACING, 0.5, LatticeType.FCC)
    np.testing.assert_array_equal(a, b)


def test_sc_small_lattice_count():
    pts = filter_intersecting_centers(
        centers_sc((2, 2, 2), 1.0, margin=0.0),
        radius=0.01,
        box=(2, 2, 2),
    )
    assert len(pts) == 27  # 3^3 grid from 0..2 after domain-intersection filtering
