"""Voxel morphology of a generated part.

Sizes are measured with morphological openings by spheres ("continuous
pore-size distribution", Münch & Holzer, J. Am. Ceram. Soc. 2008): the local
size of a point is the diameter of the largest sphere that fits inside the
phase and contains the point. Applied to the void it gives the pore-size
distribution, applied to the solid the wall/strut-thickness distribution
(the "local thickness" of Hildebrand & Rüegsegger, J. Microsc. 1997).

Throats are measured by simulated intrusion: spheres enter from the open
faces and may only pass openings at least as wide as themselves, as in
mercury-intrusion porosimetry. The largest sphere that crosses the part is the
percolation (critical) diameter.

Resolution: voxel-centre distances are converted to boundary distances with a
half-voxel offset; sizes carry about +/- half a voxel of quantisation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
from scipy import ndimage

AXES = ("x", "y", "z")


def radius_levels(max_radius_vox: float, *, ratio: float = 1.12, min_step: float = 0.5, start: float = 0.75) -> np.ndarray:
    """Sphere radii (voxels) to test: dense at small sizes, geometric above."""
    levels = []
    r = start
    while r <= max_radius_vox + 1e-9:
        levels.append(r)
        r = max(r + min_step, r * ratio)
    return np.asarray(levels or [start], dtype=np.float64)


def snapped_levels(dt: np.ndarray, *, ratio: float = 1.04) -> np.ndarray:
    """Radii (voxels) at the distance values that occur in ``dt``.

    Only these values change the opening, so snapping to them avoids the
    quantisation of a fixed geometric ladder; values closer than ``ratio``
    are thinned for speed. A radius r stands for a sphere of boundary radius r
    (centre-to-centre distance r + 0.25).
    """
    values = np.unique(dt[dt > 0])
    if values.size == 0:
        return np.asarray([0.75])
    keep = [values[0]]
    for v in values[1:]:
        if v >= keep[-1] * ratio:
            keep.append(v)
    if keep[-1] != values[-1]:
        keep.append(values[-1])
    return np.asarray(keep, dtype=np.float64) - 0.25


# ---------------------------------------------------------------------------
# Size distributions
# ---------------------------------------------------------------------------


@dataclass
class SizeDistribution:
    phase: str  # "pore" or "wall"
    method: str
    voxel_mm: float
    mean_mm: float
    d05_mm: float
    d10_mm: float
    d50_mm: float
    d90_mm: float
    max_mm: float
    bin_edges_mm: list[float] = field(default_factory=list)
    volume_fraction: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _dilate_within(seeds: np.ndarray, radius: float) -> np.ndarray:
    """Voxels within ``radius`` (voxels) of any seed, computed on the seeds' bounding box."""
    out = np.zeros(seeds.shape, dtype=bool)
    idx = np.argwhere(seeds)
    if len(idx) == 0:
        return out
    pad = int(np.ceil(radius)) + 1
    lo = np.maximum(idx.min(axis=0) - pad, 0)
    hi = np.minimum(idx.max(axis=0) + pad + 1, seeds.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    sub = seeds[box]
    out[box] = ndimage.distance_transform_edt(~sub) <= radius
    return out


def local_size(phase: np.ndarray, *, levels: np.ndarray | None = None) -> np.ndarray:
    """Local size (sphere diameter, voxels) of every phase voxel; 0 elsewhere."""
    phase = phase.astype(bool)
    size = np.zeros(phase.shape, dtype=np.float32)
    if not phase.any():
        return size
    dt = ndimage.distance_transform_edt(phase).astype(np.float32)
    # dt - 0.25 turns centre-to-centre distance into an unbiased boundary distance.
    levels = snapped_levels(dt) if levels is None else levels
    for r in levels:
        seeds = dt >= r + 0.25 - 1e-6
        if not seeds.any():
            break
        # Every voxel centre closer than dt to a seed lies in the phase.
        covered = _dilate_within(seeds, r + 0.25 - 1e-3) & phase
        size[covered] = 2.0 * r
    return size


def size_distribution(phase: np.ndarray, voxel_mm: float, name: str, *, levels: np.ndarray | None = None) -> SizeDistribution:
    size = local_size(phase, levels=levels)
    values = size[phase.astype(bool)] * voxel_mm
    if values.size == 0:
        return SizeDistribution(name, "sphere opening", voxel_mm, 0, 0, 0, 0, 0, 0)
    edges = np.unique(np.concatenate([[0.0], np.unique(values) + 1e-9]))
    hist, _ = np.histogram(values, bins=edges)
    q = np.percentile(values, [5, 10, 50, 90])
    return SizeDistribution(
        phase=name,
        method="maximal inscribed sphere (morphological opening)",
        voxel_mm=voxel_mm,
        mean_mm=float(values.mean()),
        d05_mm=float(q[0]),
        d10_mm=float(q[1]),
        d50_mm=float(q[2]),
        d90_mm=float(q[3]),
        max_mm=float(values.max()),
        bin_edges_mm=[float(e) for e in edges],
        volume_fraction=[float(h) for h in hist / values.size],
    )


# ---------------------------------------------------------------------------
# Throats: percolation diameter and intrusion
# ---------------------------------------------------------------------------


def _padded(void: np.ndarray, open_axes: tuple[int, ...], pad: int) -> tuple[np.ndarray, list[tuple[slice, ...]]]:
    """Void padded with open reservoirs on the open axes and walls elsewhere."""
    shape = np.array(void.shape) + 2 * pad
    grid = np.zeros(tuple(shape), dtype=bool)
    inner = tuple(slice(pad, pad + n) for n in void.shape)
    grid[inner] = void
    reservoirs = []
    for axis in open_axes:
        for side in (0, 1):
            sl = [slice(pad, pad + n) for n in void.shape]
            sl[axis] = slice(0, pad) if side == 0 else slice(pad + void.shape[axis], shape[axis])
            grid[tuple(sl)] = True
            reservoirs.append(tuple(sl))
    return grid, reservoirs


def percolation_diameter(void: np.ndarray, axis: int, voxel_mm: float) -> float:
    """Diameter (mm) of the largest sphere that can pass through along ``axis``.

    The part sits between two open reservoirs; the lateral sides are walls, as
    in a flow chamber. 0 means no connected path.
    """
    void = void.astype(bool)
    if not void.any():
        return 0.0
    dt0 = ndimage.distance_transform_edt(void)
    pad = int(np.ceil(dt0.max())) + 2
    grid, reservoirs = _padded(void, (axis,), pad)
    dt = ndimage.distance_transform_edt(grid)
    levels = snapped_levels(dt0, ratio=1.0)

    def passes(r: float) -> bool:
        labels, _ = ndimage.label(dt >= r + 0.25 - 1e-6)
        a = set(np.unique(labels[reservoirs[0]])) - {0}
        b = set(np.unique(labels[reservoirs[1]])) - {0}
        return bool(a & b)

    lo, hi = -1, len(levels)
    while hi - lo > 1:  # passes() is monotone in r
        mid = (lo + hi) // 2
        if passes(levels[mid]):
            lo = mid
        else:
            hi = mid
    return 0.0 if lo < 0 else float(2.0 * levels[lo] * voxel_mm)


@dataclass
class IntrusionCurve:
    open_axes: list[str]
    diameters_mm: list[float]
    intruded_fraction: list[float]  # void fraction reached by spheres >= diameter
    median_throat_mm: float  # diameter at which half the void is intruded
    method: str = "simulated intrusion from the open faces (sphere opening restricted to connected paths)"

    def fraction_reached(self, diameter_mm: float) -> float:
        """Void fraction reachable from outside by spheres of this diameter."""
        d = np.asarray(self.diameters_mm)
        f = np.asarray(self.intruded_fraction)
        if len(d) == 0:
            return 0.0
        if diameter_mm <= d[0]:
            return float(f[0])
        return float(np.interp(diameter_mm, d, f, right=0.0))

    def to_dict(self) -> dict:
        return asdict(self)


def intrusion_curve(void: np.ndarray, open_axes: tuple[int, ...], voxel_mm: float, *, levels: np.ndarray | None = None) -> IntrusionCurve:
    void = void.astype(bool)
    total = int(void.sum())
    if total == 0 or not open_axes:
        return IntrusionCurve([AXES[a] for a in open_axes], [], [], 0.0)
    dt0 = ndimage.distance_transform_edt(void)
    pad = int(np.ceil(dt0.max())) + 2
    grid, reservoirs = _padded(void, open_axes, pad)
    dt = ndimage.distance_transform_edt(grid)
    inner = tuple(slice(pad, pad + n) for n in void.shape)
    # 6 % radius steps: the curve feeds drainage fractions, not a fine histogram.
    levels = snapped_levels(dt0, ratio=1.06) if levels is None else levels
    diameters, fractions = [], []
    for r in levels:
        seeds = dt >= r + 0.25 - 1e-6
        labels, _ = ndimage.label(seeds)
        connected = set()
        for res in reservoirs:
            connected |= set(np.unique(labels[res]))
        connected.discard(0)
        if not connected:
            diameters.append(2.0 * r * voxel_mm)
            fractions.append(0.0)
            break
        reached_seeds = np.isin(labels, list(connected))
        reached = _dilate_within(reached_seeds, r + 0.25 - 1e-3)[inner] & void
        diameters.append(2.0 * r * voxel_mm)
        fractions.append(float(reached.sum() / total))
    # Larger spheres can never reach more; digitised balls wobble slightly.
    f = np.minimum.accumulate(np.asarray(fractions))
    d = np.asarray(diameters)
    median = float(np.interp(0.5, f[::-1], d[::-1])) if f.max() >= 0.5 else 0.0
    return IntrusionCurve([AXES[a] for a in open_axes], [float(x) for x in d], [float(x) for x in f], median)


# ---------------------------------------------------------------------------
# Closed pores, tortuosity
# ---------------------------------------------------------------------------


@dataclass
class ClosedPores:
    count: int
    closed_void_fraction: float  # of all void inside the domain
    largest_volume_mm3: float
    largest_equivalent_diameter_mm: float

    def to_dict(self) -> dict:
        return asdict(self)


def closed_pores(solid: np.ndarray, voxel_mm: float, domain: np.ndarray | None = None) -> ClosedPores:
    """Void pockets with no path to the outside (they trap resin and cells).

    Everything that is not solid - inside or outside the domain - is fluid;
    fluid connected to the grid border is open. The closed fraction is taken
    relative to the void inside ``domain`` (the whole grid if None).
    """
    solid = solid.astype(bool)
    fluid = np.pad(~solid, 1, constant_values=True)
    labels, count = ndimage.label(fluid)
    border = labels[0, 0, 0]
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    sizes[0] = 0
    sizes[border] = 0
    closed_volume = int(sizes.sum())
    largest = int(sizes.max()) if count else 0
    void_in_domain = int(((~solid) & domain).sum()) if domain is not None else int((~solid).sum())
    vol = largest * voxel_mm**3
    return ClosedPores(
        count=int(np.count_nonzero(sizes)),
        closed_void_fraction=float(closed_volume / max(void_in_domain, 1)),
        largest_volume_mm3=float(vol),
        largest_equivalent_diameter_mm=float((6.0 * vol / np.pi) ** (1.0 / 3.0)) if vol > 0 else 0.0,
    )


def geometric_tortuosity(void: np.ndarray, axis: int) -> float | None:
    """Mean shortest void path length across the part divided by its thickness.

    Paths use 26-connected steps (lengths 1, sqrt2, sqrt3) through void voxels
    from the inlet face to the outlet face. None if the void does not percolate.
    """
    from skimage.graph import MCP_Geometric

    void = np.moveaxis(void.astype(bool), axis, 0)
    if void.shape[0] < 3 or not void[0].any() or not void[-1].any():
        return None
    costs = np.where(void, 1.0, np.inf)
    mcp = MCP_Geometric(costs, fully_connected=True)
    starts = [(0, int(i), int(j)) for i, j in np.argwhere(void[0])]
    cumulative, _ = mcp.find_costs(starts)
    end = cumulative[-1][void[-1]]
    end = end[np.isfinite(end)]
    if end.size == 0:
        return None
    return float(end.mean() / (void.shape[0] - 1))


# ---------------------------------------------------------------------------
# Curvature of the continuous field
# ---------------------------------------------------------------------------


@dataclass
class CurvatureSummary:
    sample_count: int
    mean_curvature_mean_per_mm: float
    mean_curvature_abs_median_per_mm: float
    mean_curvature_p10_per_mm: float
    mean_curvature_p90_per_mm: float
    gaussian_curvature_mean_per_mm2: float
    saddle_fraction: float  # share of the surface with K < 0 (hyperbolic, as on TPMS)
    method: str = "level-set curvature of the continuous field (central differences, surface band)"

    def to_dict(self) -> dict:
        return asdict(self)


def field_curvature(field: np.ndarray, voxel_mm: float, *, interior: np.ndarray | None = None, max_samples: int = 2_000_000, seed: int = 0) -> CurvatureSummary | None:
    """Mean (H) and Gaussian (K) curvature on the zero level set of ``field``.

    Sign convention: the field is negative inside the solid, so a convex
    solid bump has H > 0 (a sphere of radius R: H = 1/R, K = 1/R^2).
    ``interior`` restricts samples (e.g. away from the domain cut, where the
    field has a kink).
    """
    f = field.astype(np.float64, copy=False)
    band = np.abs(f) < 0.5 * voxel_mm
    band[[0, -1], :, :] = False
    band[:, [0, -1], :] = False
    band[:, :, [0, -1]] = False
    if interior is not None:
        band &= interior
    idx = np.argwhere(band)
    if len(idx) < 10:
        return None
    if len(idx) > max_samples:
        idx = idx[np.random.default_rng(seed).choice(len(idx), max_samples, replace=False)]
    i, j, k = idx.T
    h = voxel_mm

    def v(di, dj, dk):
        return f[i + di, j + dj, k + dk]

    c = v(0, 0, 0)
    fx = (v(1, 0, 0) - v(-1, 0, 0)) / (2 * h)
    fy = (v(0, 1, 0) - v(0, -1, 0)) / (2 * h)
    fz = (v(0, 0, 1) - v(0, 0, -1)) / (2 * h)
    fxx = (v(1, 0, 0) - 2 * c + v(-1, 0, 0)) / h**2
    fyy = (v(0, 1, 0) - 2 * c + v(0, -1, 0)) / h**2
    fzz = (v(0, 0, 1) - 2 * c + v(0, 0, -1)) / h**2
    fxy = (v(1, 1, 0) - v(1, -1, 0) - v(-1, 1, 0) + v(-1, -1, 0)) / (4 * h**2)
    fxz = (v(1, 0, 1) - v(1, 0, -1) - v(-1, 0, 1) + v(-1, 0, -1)) / (4 * h**2)
    fyz = (v(0, 1, 1) - v(0, 1, -1) - v(0, -1, 1) + v(0, -1, -1)) / (4 * h**2)
    g2 = fx**2 + fy**2 + fz**2
    ok = g2 > 1e-12
    g = np.sqrt(g2[ok])
    fx, fy, fz, fxx, fyy, fzz, fxy, fxz, fyz = (a[ok] for a in (fx, fy, fz, fxx, fyy, fzz, fxy, fxz, fyz))
    H = ((fyy + fzz) * fx**2 + (fxx + fzz) * fy**2 + (fxx + fyy) * fz**2 - 2 * (fx * fy * fxy + fx * fz * fxz + fy * fz * fyz)) / (2 * g**3)
    K = (
        fx**2 * (fyy * fzz - fyz**2)
        + fy**2 * (fxx * fzz - fxz**2)
        + fz**2 * (fxx * fyy - fxy**2)
        + 2 * fx * fy * (fxz * fyz - fxy * fzz)
        + 2 * fy * fz * (fxy * fxz - fyz * fxx)
        + 2 * fx * fz * (fxy * fyz - fxz * fyy)
    ) / g**4
    finite = np.isfinite(H) & np.isfinite(K)
    H, K = H[finite], K[finite]
    if H.size == 0:
        return None
    return CurvatureSummary(
        sample_count=int(H.size),
        mean_curvature_mean_per_mm=float(H.mean()),
        mean_curvature_abs_median_per_mm=float(np.median(np.abs(H))),
        mean_curvature_p10_per_mm=float(np.percentile(H, 10)),
        mean_curvature_p90_per_mm=float(np.percentile(H, 90)),
        gaussian_curvature_mean_per_mm2=float(K.mean()),
        saddle_fraction=float((K < 0).mean()),
    )


def central_crop(shape: tuple[int, ...], max_voxels: int, keep_axis: int | None = None) -> tuple[slice, ...]:
    """Central sub-block with at most ``max_voxels`` voxels (optionally full along one axis)."""
    shape = np.asarray(shape)
    if shape.prod() <= max_voxels:
        return tuple(slice(0, int(n)) for n in shape)
    free = [a for a in range(3) if a != keep_axis]
    fixed = shape[keep_axis] if keep_axis is not None else 1
    budget = max_voxels / fixed
    scale = (budget / np.prod(shape[free])) ** (1.0 / len(free)) if keep_axis is not None else (max_voxels / shape.prod()) ** (1.0 / 3.0)
    out = []
    for a in range(3):
        n = int(shape[a])
        m = n if a == keep_axis else max(8, min(n, int(n * scale)))
        start = (n - m) // 2
        out.append(slice(start, start + m))
    return tuple(out)
