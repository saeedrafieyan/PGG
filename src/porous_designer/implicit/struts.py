"""Strut (beam) lattices as exact distance fields.

Every lattice here has full cubic (Oh) symmetry about a node at the origin
and is periodic with period 1 in cell units. A point is therefore folded into
the fundamental region ``0 <= z <= y <= x <= 1/2`` (translate to the nearest
cell centre, reflect to the positive octant, sort coordinates) without
changing its distance to the lattice. Only the few segments that can be
nearest to that region are then tested, which keeps the cost at a handful of
point-segment distances per voxel.

Lattices (conventional cubic cell, edge 1):

* cubic  - simple-cubic nodes, edges along the axes,
* bcc    - body-centred nodes, edges along the half body diagonals,
* octet  - face-centred nodes, edges between nearest neighbours (octet truss),
* kelvin - edges of the truncated-octahedron (Kelvin) foam, BCC packing.
"""

from __future__ import annotations

import itertools
from functools import lru_cache

import numpy as np

from porous_designer.domain.enums import StructureFamily

# Largest strut radius (cell units) the prefiltered segment set is valid for.
MAX_RADIUS_CELL = 0.5
_TOL = 1e-9


def _nodes_and_edges(kind: str) -> tuple[np.ndarray, list[tuple[int, int]]]:
    rng = range(-2, 3)
    cube = np.array(list(itertools.product(rng, rng, rng)), dtype=float)
    if kind == "cubic":
        nodes = cube
        edge_length = 1.0
    elif kind == "bcc":
        nodes = np.vstack([cube, cube + 0.5])
        edge_length = np.sqrt(3) / 2
    elif kind == "octet":
        offsets = np.array([[0, 0, 0], [0.5, 0.5, 0], [0.5, 0, 0.5], [0, 0.5, 0.5]])
        nodes = np.vstack([cube + o for o in offsets])
        edge_length = np.sqrt(2) / 2
    elif kind == "kelvin":
        perms = set()
        for base in itertools.permutations((0.0, 0.25, 0.5)):
            for signs in itertools.product((-1, 1), repeat=3):
                perms.add(tuple(b * s for b, s in zip(base, signs)))
        centers = np.vstack([cube, cube + 0.5])
        vertices = (centers[:, None, :] + np.array(sorted(perms))[None, :, :]).reshape(-1, 3)
        nodes = np.unique(np.round(vertices, 9), axis=0)
        edge_length = np.sqrt(2) / 4
    else:
        raise ValueError(f"unknown strut lattice {kind}")
    # Keep a neighbourhood of the origin cell to limit the pair search.
    nodes = nodes[np.all(np.abs(nodes) <= 1.6, axis=1)]
    from scipy.spatial import cKDTree

    tree = cKDTree(nodes)
    pairs = tree.query_pairs(edge_length + 1e-6)
    edges = [(i, j) for i, j in sorted(pairs) if abs(np.linalg.norm(nodes[i] - nodes[j]) - edge_length) < 1e-6]
    return nodes, edges


def _segment_box_distance(a: np.ndarray, b: np.ndarray, lo: float, hi: float, samples: int = 64) -> float:
    t = np.linspace(0.0, 1.0, samples)[:, None]
    pts = a + t * (b - a)
    clamped = np.clip(pts, lo, hi)
    return float(np.min(np.linalg.norm(pts - clamped, axis=1)))


@lru_cache(maxsize=None)
def fundamental_segments(kind: str) -> np.ndarray:
    """Segments (K, 2, 3) that can be nearest to a point of the folded region."""
    nodes, edges = _nodes_and_edges(kind)
    keep = []
    for i, j in edges:
        a, b = nodes[i], nodes[j]
        # Conservative: anything within reach of the [0, 1/2]^3 box plus the
        # largest supported radius and a sampling margin.
        if _segment_box_distance(a, b, 0.0, 0.5) <= MAX_RADIUS_CELL + 0.05:
            keep.append((a, b))
    segments = np.array(keep, dtype=np.float64)
    # Remove segments that cannot be nearest inside the fundamental region
    # 0 <= z <= y <= x <= 0.5 by testing a dense sample of that region.
    # A segment matters only if it is (nearly) the nearest one somewhere in
    # the region; dropping the others leaves the minimum unchanged.
    # Mirror images tie exactly on the region's boundary planes, so the test
    # uses random interior points and keeps each point's true argmin.
    rng = np.random.default_rng(12345)
    pts = np.sort(rng.uniform(0.0, 0.5, size=(60000, 3)), axis=1)[:, ::-1]
    dist = np.stack([_point_segment_distance_np(pts, s[0], s[1]) for s in segments], axis=1)
    useful = np.zeros(len(segments), dtype=bool)
    useful[np.unique(np.argmin(dist, axis=1))] = True
    return segments[useful]


def _point_segment_distance_np(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    t = np.clip(((p - a) @ ab) / float(ab @ ab), 0.0, 1.0)
    closest = a + t[:, None] * ab
    return np.linalg.norm(p - closest, axis=1)


def fold(ops, ux, uy, uz):
    """Map cell coordinates into the fundamental region (x >= y >= z >= 0)."""
    fx = ops.abs(ux - ops.floor(ux + 0.5))
    fy = ops.abs(uy - ops.floor(uy + 0.5))
    fz = ops.abs(uz - ops.floor(uz + 0.5))
    folded = ops.sort_desc_last(ops.stack_last([fx, fy, fz]))
    return folded[..., 0], folded[..., 1], folded[..., 2]


def strut_distance(ops, kind: str, ux, uy, uz):
    """Distance (cell units) from points to the nearest strut axis."""
    x, y, z = fold(ops, ux, uy, uz)
    best = None
    for a, b in fundamental_segments(kind):
        ab = b - a
        denom = float(ab @ ab)
        t = ((x - a[0]) * ab[0] + (y - a[1]) * ab[1] + (z - a[2]) * ab[2]) / denom
        t = ops.clip(t, 0.0, 1.0)
        dx = x - (a[0] + t * ab[0])
        dy = y - (a[1] + t * ab[1])
        dz = z - (a[2] + t * ab[2])
        d2 = dx * dx + dy * dy + dz * dz
        best = d2 if best is None else ops.minimum(best, d2)
    return ops.sqrt(best)


def brute_force_distance(kind: str, points: np.ndarray) -> np.ndarray:
    """Reference distance using every edge near the points (for testing)."""
    nodes, edges = _nodes_and_edges(kind)
    shifted = points - np.floor(points)  # into [0, 1)
    best = np.full(len(points), np.inf)
    for i, j in edges:
        best = np.minimum(best, _point_segment_distance_np(shifted, nodes[i], nodes[j]))
    return best


STRUT_KINDS: dict[StructureFamily, str] = {
    StructureFamily.STRUT_CUBIC: "cubic",
    StructureFamily.STRUT_BCC: "bcc",
    StructureFamily.STRUT_OCTET: "octet",
    StructureFamily.STRUT_KELVIN: "kelvin",
}
