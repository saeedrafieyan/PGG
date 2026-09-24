"""Point-set based fields: sphere-pore lattices and Voronoi open-cell foam.

Both are evaluated with KD-trees on the CPU:

* sphere pores - exact distance to the union of equal spheres is
  ``|x - nearest centre| - r``; solid is the complement of the pores.
* Voronoi foam - struts along the edges of the Voronoi diagram of jittered
  seeds. Edges are sampled densely and the distance to the nearest sample
  approximates the distance to the edge network (error below a quarter of
  the sampling step for points near the struts).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import Voronoi, cKDTree


def sphere_pore_distance(points: np.ndarray, centers: np.ndarray, radius: float) -> np.ndarray:
    """Signed distance to the pore union (negative inside a pore)."""
    if len(centers) == 0:
        return np.full(len(points), np.float32(1e6))
    tree = cKDTree(centers)
    dist, _ = tree.query(points, k=1, workers=-1)
    return (dist - radius).astype(np.float32)


@dataclass
class VoronoiNetwork:
    seeds: np.ndarray
    edges: np.ndarray  # (E, 2, 3) mm
    samples: np.ndarray  # (S, 3) mm
    sample_step_mm: float

    @property
    def edge_count(self) -> int:
        return int(len(self.edges))


def jittered_seeds(bounds_mm: tuple[float, float, float], cell_mm: float, randomness: float, seed: int, margin_cells: int = 2) -> np.ndarray:
    """Seeds on a cubic grid of spacing ``cell_mm`` with uniform jitter.

    ``randomness`` 0 gives a regular grid (a cubic Voronoi network); 1 moves
    every seed uniformly within its cell. The grid extends ``margin_cells``
    beyond the domain so edges near the boundary are complete.
    """
    rng = np.random.default_rng(seed)
    axes = []
    for extent in bounds_mm:
        n = int(np.ceil(extent / cell_mm))
        axes.append((np.arange(-margin_cells, n + margin_cells) + 0.5) * cell_mm)
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    jitter = rng.uniform(-0.5, 0.5, size=grid.shape) * cell_mm * randomness
    return grid + jitter


def voronoi_network(bounds_mm: tuple[float, float, float], cell_mm: float, randomness: float, seed: int, sample_step_mm: float) -> VoronoiNetwork:
    seeds = jittered_seeds(bounds_mm, cell_mm, randomness, seed)
    vor = Voronoi(seeds)
    lo = -cell_mm
    hi = np.asarray(bounds_mm) + cell_mm
    edge_set: set[tuple[int, int]] = set()
    for ridge in vor.ridge_vertices:
        if -1 in ridge or len(ridge) < 2:
            continue
        for a, b in zip(ridge, ridge[1:] + ridge[:1]):
            edge_set.add((a, b) if a < b else (b, a))
    vertices = vor.vertices
    edges = []
    for a, b in sorted(edge_set):
        va, vb = vertices[a], vertices[b]
        if np.all(va >= lo) and np.all(va <= hi) and np.all(vb >= lo) and np.all(vb <= hi):
            edges.append((va, vb))
    edges_arr = np.asarray(edges, dtype=np.float64).reshape(-1, 2, 3)
    lengths = np.linalg.norm(edges_arr[:, 1] - edges_arr[:, 0], axis=1)
    samples = []
    for (va, vb), length in zip(edges_arr, lengths):
        count = max(2, int(np.ceil(length / sample_step_mm)) + 1)
        t = np.linspace(0.0, 1.0, count)[:, None]
        samples.append(va + t * (vb - va))
    sample_arr = np.vstack(samples) if samples else np.zeros((0, 3))
    return VoronoiNetwork(seeds=seeds, edges=edges_arr, samples=sample_arr, sample_step_mm=sample_step_mm)


def voronoi_edge_distance(points: np.ndarray, network: VoronoiNetwork, *, reach_mm: float) -> np.ndarray:
    """Approximate distance (mm) to the Voronoi edge network, capped at ``reach_mm``."""
    if len(network.samples) == 0:
        return np.full(len(points), np.float32(reach_mm))
    tree = cKDTree(network.samples)
    dist, _ = tree.query(points, k=1, workers=-1, distance_upper_bound=reach_mm)
    dist = np.where(np.isfinite(dist), dist, reach_mm)
    return dist.astype(np.float32)
