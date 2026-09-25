"""Exactly periodic representative volume elements (RVEs) of a design.

Effective properties (permeability, stiffness) are computed with periodic
boundary conditions, so the sample must tile space without seams. Instead of
cutting a block out of the part, the lattice is re-evaluated on its own
periodic cell at high resolution:

* TPMS and strut lattices: one unit cell (the kernel's normalised distance),
* sphere-pore lattices: the conventional cell (orthorhombic for HCP),
* Voronoi foam: a periodic tessellation of a 3x3x3-cell box.

Graded designs are represented by RVEs at the two ends of the grading.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.spatial import Voronoi, cKDTree

from porous_designer.domain.enums import StructureFamily, TPMSVariant
from porous_designer.implicit.lattice import lattice_kind, periodic_cell_distance

# Largest RVE: keeps LBM and FFT homogenisation to seconds on a GPU.
MAX_RVE_VOXELS = 1_200_000


@dataclass
class RVE:
    solid: np.ndarray  # bool, periodic in all directions
    lengths_mm: tuple[float, float, float]
    label: str
    note: str = ""

    @property
    def voxel_mm(self) -> float:
        return float(self.lengths_mm[0] / self.solid.shape[0])

    @property
    def porosity(self) -> float:
        return float(1.0 - self.solid.mean())

    def summary(self) -> dict:
        return {
            "label": self.label,
            "shape": list(self.solid.shape),
            "lengths_mm": [float(v) for v in self.lengths_mm],
            "voxel_mm": self.voxel_mm,
            "porosity": self.porosity,
            "note": self.note,
        }


def resample_periodic(solid: np.ndarray, voxel_mm: float, factor: float) -> tuple[np.ndarray, float]:
    """Periodic nearest-sample resampling of an RVE by ``factor`` (> 1 = coarser)."""
    if factor <= 1.0:
        return solid, voxel_mm
    shape = tuple(max(8, int(round(n / factor))) for n in solid.shape)
    index = [np.minimum(((np.arange(m) + 0.5) * n / m).astype(np.int64), n - 1) for m, n in zip(shape, solid.shape)]
    h = float(np.mean([n * voxel_mm / m for n, m in zip(solid.shape, shape)]))
    return solid[np.ix_(*index)], h


def measurement_grid(solid: np.ndarray, voxel_mm: float, *, max_voxels: int = 400_000, min_nodes: float = 10.0) -> tuple[np.ndarray, float]:
    """A coarser copy for size / stiffness measurement when the RVE is over-resolved.

    The typical wall and pore (twice the 90th-percentile distance to the other
    phase) must still span ``min_nodes`` voxels.
    """
    from scipy import ndimage

    if solid.size <= max_voxels or solid.all() or not solid.any():
        return solid, voxel_mm
    ds = ndimage.distance_transform_edt(solid)
    dv = ndimage.distance_transform_edt(~solid)
    feature = 2.0 * min(np.percentile(ds[solid], 90), np.percentile(dv[~solid], 90))
    factor = min((solid.size / max_voxels) ** (1.0 / 3.0), feature / min_nodes)
    return resample_periodic(solid, voxel_mm, factor) if factor >= 1.2 else (solid, voxel_mm)


def _cells_for_resolution(feature_cells: float, *, min_voxels_across: float = 6.0, lo: int = 40, hi: int = 112) -> int:
    """Voxels per cell so the thinnest feature spans ``min_voxels_across``."""
    n = int(math.ceil(min_voxels_across / max(feature_cells, 1e-3)))
    return int(min(hi, max(lo, n + (n % 2))))


# ---------------------------------------------------------------------------
# Periodic TPMS / strut cell
# ---------------------------------------------------------------------------


def unit_cell_rve(family: StructureFamily, variant: TPMSVariant, control: float, cell_mm: float, *, n: int | None = None, label: str = "unit cell") -> RVE:
    kind = lattice_kind(family, variant)
    if kind == "tpms_network":
        n = n or 64
        d = periodic_cell_distance(family, variant, n)
        solid = d <= control
    else:
        # Walls tau*cell thick and pores of comparable size: resolve the thinner.
        n = n or _cells_for_resolution(min(control, max(1.0 - control, 0.05)))
        d = periodic_cell_distance(family, variant, n)
        solid = d <= control / 2.0
    return RVE(solid=solid, lengths_mm=(cell_mm,) * 3, label=label, note=f"{kind}, {n}^3 voxels per cell")


# ---------------------------------------------------------------------------
# Periodic sphere-pore cells
# ---------------------------------------------------------------------------


def _sphere_basis(family: StructureFamily, spacing: float) -> tuple[tuple[float, float, float], np.ndarray]:
    """Conventional cell lengths (mm) and basis points (fractional) for nearest-neighbour spacing s."""
    s = spacing
    if family == StructureFamily.SC_SPHERICAL_PORES:
        return (s, s, s), np.array([[0.0, 0.0, 0.0]])
    if family == StructureFamily.BCC_SPHERICAL_PORES:
        a = 2.0 * s / math.sqrt(3.0)
        return (a, a, a), np.array([[0, 0, 0], [0.5, 0.5, 0.5]], dtype=float)
    if family == StructureFamily.FCC_SPHERICAL_PORES:
        a = s * math.sqrt(2.0)
        return (a, a, a), np.array([[0, 0, 0], [0.5, 0.5, 0], [0.5, 0, 0.5], [0, 0.5, 0.5]], dtype=float)
    if family == StructureFamily.HCP_SPHERICAL_PORES:
        # ABAB stacking as in generators.sphere_lattices: orthorhombic a x a*sqrt3 x 2c.
        a = s
        c = a * math.sqrt(2.0 / 3.0)
        lengths = (a, a * math.sqrt(3.0), 2.0 * c)
        basis = np.array(
            [
                [0.0, 0.0, 0.0],
                [0.5, 0.5, 0.0],
                [0.5, 1.0 / 6.0, 0.5],
                [0.0, 2.0 / 3.0, 0.5],
            ]
        )
        return lengths, basis
    raise ValueError(f"{family.value} is not a sphere-pore lattice")


def sphere_lattice_rve(family: StructureFamily, spacing_mm: float, pore_diameter_mm: float, *, voxel_mm: float | None = None) -> RVE:
    lengths, basis = _sphere_basis(family, spacing_mm)
    r = pore_diameter_mm / 2.0
    # Resolve the thinner of the pore throats and the struts between pores.
    gap = abs(spacing_mm - pore_diameter_mm)
    h = voxel_mm or max(min(lengths) / 112.0, min(spacing_mm / 48.0, max(gap, 0.02 * spacing_mm) / 6.0))
    h = max(h, (float(np.prod(lengths)) / MAX_RVE_VOXELS) ** (1.0 / 3.0))
    shape = tuple(max(8, int(round(L / h))) for L in lengths)
    axes = [(np.arange(n) + 0.5) * (L / n) for n, L in zip(shape, lengths)]
    pts = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    centres = (basis * np.asarray(lengths)) % np.asarray(lengths)
    tree = cKDTree(centres, boxsize=np.asarray(lengths))
    dist, _ = tree.query(pts, k=1, workers=-1)
    solid = (dist >= r).reshape(shape)
    return RVE(solid=solid, lengths_mm=tuple(float(v) for v in lengths), label="conventional cell", note=f"{family.value} periodic cell")


# ---------------------------------------------------------------------------
# Periodic Voronoi foam
# ---------------------------------------------------------------------------


def periodic_voronoi_distance(cells: int, randomness: float, seed: int, n_per_cell: int) -> np.ndarray:
    """Distance (cell units) to the edges of a periodic Voronoi tessellation of a cells^3 box."""
    rng = np.random.default_rng(seed)
    B = float(cells)
    g = (np.arange(cells) + 0.5)
    seeds = np.stack(np.meshgrid(g, g, g, indexing="ij"), axis=-1).reshape(-1, 3)
    seeds = (seeds + rng.uniform(-0.5, 0.5, size=seeds.shape) * randomness) % B
    shifts = np.array([[i, j, k] for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)], dtype=float) * B
    tiled = (seeds[None, :, :] + shifts[:, None, :]).reshape(-1, 3)
    vor = Voronoi(tiled)
    edges: set[tuple[int, int]] = set()
    for ridge in vor.ridge_vertices:
        if -1 in ridge or len(ridge) < 2:
            continue
        for a, b in zip(ridge, ridge[1:] + ridge[:1]):
            edges.add((a, b) if a < b else (b, a))
    verts = vor.vertices
    step = 1.0 / (2.0 * n_per_cell)
    samples = []
    for a, b in edges:
        va, vb = verts[a], verts[b]
        mid = 0.5 * (va + vb)
        if np.any(mid < -0.5) or np.any(mid > B + 0.5):
            continue  # far images; their periodic copies are kept
        count = max(2, int(np.ceil(np.linalg.norm(vb - va) / step)) + 1)
        t = np.linspace(0.0, 1.0, count)[:, None]
        samples.append(va + t * (vb - va))
    pts_edges = np.vstack(samples) % B
    tree = cKDTree(pts_edges, boxsize=B)
    n = cells * n_per_cell
    c = (np.arange(n) + 0.5) / n_per_cell
    grid = np.stack(np.meshgrid(c, c, c, indexing="ij"), axis=-1).reshape(-1, 3)
    dist, _ = tree.query(grid, k=1, workers=-1)
    return dist.reshape(n, n, n).astype(np.float32)


def voronoi_rve(tau: float, cell_mm: float, randomness: float, seed: int, *, cells: int = 3, n_per_cell: int | None = None) -> RVE:
    cap = int((MAX_RVE_VOXELS ** (1.0 / 3.0)) / cells)
    n_per_cell = n_per_cell or min(cap, _cells_for_resolution(tau, lo=24, hi=cap))
    d = periodic_voronoi_distance(cells, randomness, seed, n_per_cell)
    return RVE(solid=d <= tau / 2.0, lengths_mm=(cells * cell_mm,) * 3, label=f"periodic foam {cells}^3 cells", note=f"{n_per_cell} voxels per cell")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def design_rves(spec, control_name: str, control: float, *, calibration=None) -> list[RVE]:
    """RVEs that represent the delivered design (two for graded designs)."""
    structure = spec.structure
    family = structure.family
    if family.is_sphere_lattice:
        return [sphere_lattice_rve(family, float(control), float(structure.pore_diameter_mm))]
    L0 = float(structure.unit_cell_size_mm)
    grading = spec.targets.porosity_grading
    if grading is not None and calibration is not None and control_name == "porosity_shift":
        ends = []
        for label, target in (("grading start", grading.start), ("grading end", grading.end)):
            local = float(calibration.parameter_for(np.clip(target + control, 0.001, 0.999)))
            ends.append((label, local, L0))
    elif structure.cell_size_grading is not None:
        g = structure.cell_size_grading
        ends = [("cell grading start", float(control), float(g.start)), ("cell grading end", float(control), float(g.end))]
    else:
        ends = [("uniform", float(control), L0)]
    out = []
    for label, local, cell in ends:
        if family.is_stochastic:
            rve = voronoi_rve(local, cell, structure.voronoi_randomness, spec.generation.deterministic_seed)
            rve.label = f"{label}: {rve.label}"
        else:
            rve = unit_cell_rve(family, structure.tpms_variant, local, cell, label=label)
        out.append(rve)
    return out
