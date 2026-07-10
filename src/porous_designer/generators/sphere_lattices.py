"""Sphere-pore lattice center generation.

Coordinate convention
---------------------
- Domain box occupies [0, Lx] × [0, Ly] × [0, Lz] mm with origin at the corner.
- All lattice generators accept ``box = (Lx, Ly, Lz)`` and nearest-neighbour spacing ``s``.
- Centers are generated on a padded grid ``[-margin, L+margin]`` then filtered to those
  whose generating sphere can intersect the closed box domain.
- Points are returned in deterministic lexicographic order (x, then y, then z).
- Duplicate centers (within 1 nm) are removed deterministically.

Lattice definitions (nearest-neighbour spacing = s)
----------------------------------------------------
SC  : simple cubic, spacing s along X, Y, Z.
BCC : conventional cubic cell edge a = 2s/√3, basis (0,0,0) and (½,½,½).
FCC : conventional cubic cell edge a = s√2, face-centred basis.
HCP : ABAB stacking; in-plane spacing a = s, layer height c = a√(2/3).
      Even layers (kz even): origin offset (0, 0).
      Odd layers (kz odd): offset (a/2, a/(2√3)).
      Rows alternate with shift a/2 along X.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Sequence

import numpy as np

from porous_designer.domain.enums import DomainShape, StructureFamily
from porous_designer.domain.specification import DesignSpecification
from porous_designer.generators.base import GeneratedField, ParameterDefinition, PorousGenerator
from porous_designer.geometry.domains import DomainGrid

_DEDUP_TOL = 1e-9


class LatticeType(str, Enum):
    SC = "sc"
    BCC = "bcc"
    FCC = "fcc"
    HCP = "hcp"

    @classmethod
    def from_family(cls, family: StructureFamily) -> LatticeType:
        mapping = {
            StructureFamily.SC_SPHERICAL_PORES: cls.SC,
            StructureFamily.BCC_SPHERICAL_PORES: cls.BCC,
            StructureFamily.FCC_SPHERICAL_PORES: cls.FCC,
            StructureFamily.HCP_SPHERICAL_PORES: cls.HCP,
        }
        if family not in mapping:
            raise ValueError(f"Not a sphere lattice family: {family}")
        return mapping[family]


def _grid_range(lo: float, hi: float, step: float, phase: float = 0.0) -> list[float]:
    i0 = math.floor((lo - phase) / step) - 1
    i1 = math.ceil((hi - phase) / step) + 1
    return [phase + i * step for i in range(i0, i1 + 1)]


def _deduplicate_points(pts: np.ndarray) -> np.ndarray:
    if len(pts) == 0:
        return pts.reshape(0, 3)
    order = np.lexsort((pts[:, 2], pts[:, 1], pts[:, 0]))
    pts = pts[order]
    keep = [0]
    for i in range(1, len(pts)):
        if np.linalg.norm(pts[i] - pts[keep[-1]]) > _DEDUP_TOL:
            keep.append(i)
    return pts[keep]


def centers_sc(box: Sequence[float], spacing: float, margin: float) -> np.ndarray:
    lx, ly, lz = box
    xs = _grid_range(-margin, lx + margin, spacing)
    ys = _grid_range(-margin, ly + margin, spacing)
    zs = _grid_range(-margin, lz + margin, spacing)
    pts = np.array([(x, y, z) for x in xs for y in ys for z in zs], dtype=np.float64)
    return _deduplicate_points(pts)


def _cell_lattice(
    box: Sequence[float],
    cell_edge: float,
    basis: list[tuple[float, float, float]],
    margin: float,
) -> np.ndarray:
    lx, ly, lz = box
    xs = _grid_range(-margin, lx + margin, cell_edge)
    ys = _grid_range(-margin, ly + margin, cell_edge)
    zs = _grid_range(-margin, lz + margin, cell_edge)
    pts = []
    for x in xs:
        for y in ys:
            for z in zs:
                for bx, by, bz in basis:
                    pts.append((x + bx * cell_edge, y + by * cell_edge, z + bz * cell_edge))
    return _deduplicate_points(np.array(pts, dtype=np.float64))


def centers_bcc(box: Sequence[float], spacing: float, margin: float) -> np.ndarray:
    a = 2.0 * spacing / math.sqrt(3.0)
    return _cell_lattice(box, a, [(0, 0, 0), (0.5, 0.5, 0.5)], margin)


def centers_fcc(box: Sequence[float], spacing: float, margin: float) -> np.ndarray:
    a = spacing * math.sqrt(2.0)
    basis = [(0, 0, 0), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)]
    return _cell_lattice(box, a, basis, margin)


def centers_hcp(box: Sequence[float], spacing: float, margin: float) -> np.ndarray:
    """HCP with ABAB stacking; in-plane spacing a = spacing, c-layer = a√(2/3)."""
    a = spacing
    c_layer = a * math.sqrt(2.0 / 3.0)
    dy = a * math.sqrt(3.0) / 2.0
    off = (a / 2.0, a / (2.0 * math.sqrt(3.0)))
    lx, ly, lz = box
    pts: list[tuple[float, float, float]] = []
    z0, z1 = -margin, lz + margin
    y0, y1 = -margin, ly + margin
    x0, x1 = -margin, lx + margin
    kz = 0
    z = z0
    while z <= z1:
        ox, oy = (0.0, 0.0) if kz % 2 == 0 else off
        j = int(math.floor((y0 - oy) / dy)) - 1
        y = oy + j * dy
        while y <= y1:
            rx = ox + (a / 2.0 if (j % 2) else 0.0)
            i = int(math.floor((x0 - rx) / a)) - 1
            x = rx + i * a
            while x <= x1:
                pts.append((x, y, z))
                i += 1
                x = rx + i * a
            j += 1
            y = oy + j * dy
        kz += 1
        z = z0 + kz * c_layer
    return _deduplicate_points(np.array(pts, dtype=np.float64))


_GENERATORS = {
    LatticeType.SC: centers_sc,
    LatticeType.BCC: centers_bcc,
    LatticeType.FCC: centers_fcc,
    LatticeType.HCP: centers_hcp,
}


def generate_sphere_centers(
    box: Sequence[float],
    spacing: float,
    margin: float,
    lattice: LatticeType,
) -> np.ndarray:
    """Generate padded, deduplicated sphere centers for the given lattice."""
    return _GENERATORS[lattice](box, spacing, margin)


def sphere_intersects_box(
    center: Sequence[float],
    radius: float,
    box: Sequence[float],
) -> bool:
    """True if a sphere at ``center`` with ``radius`` intersects the closed box [0,L]."""
    cx, cy, cz = center
    lx, ly, lz = box
    dx = max(0.0, -cx, cx - lx)
    dy = max(0.0, -cy, cy - ly)
    dz = max(0.0, -cz, cz - lz)
    return dx * dx + dy * dy + dz * dz < radius * radius


def filter_intersecting_centers(
    centers: np.ndarray,
    radius: float,
    box: Sequence[float],
) -> np.ndarray:
    """Keep only centers whose generating sphere intersects the domain box."""
    if len(centers) == 0:
        return centers.reshape(0, 3)
    mask = [sphere_intersects_box(c, radius, box) for c in centers]
    filtered = centers[np.array(mask)]
    return _deduplicate_points(filtered)


def nearest_neighbor_distances(centers: np.ndarray, k: int = 2) -> np.ndarray:
    """Return k-nearest distances for each center (includes self at index 0)."""
    if len(centers) < 2:
        return np.array([])
    from scipy.spatial import cKDTree

    tree = cKDTree(centers)
    d, _ = tree.query(centers, k=min(k, len(centers)))
    if d.ndim == 1:
        return d
    return d[:, 1] if k >= 2 else d


class SphereLatticeGenerator(PorousGenerator):
    """Adapter from sphere-center lattices to the unified generator interface."""

    control_parameter = "lattice_spacing_mm"
    monotonic_decreasing = True
    parameter_definitions = (
        ParameterDefinition(
            "pore_diameter_mm",
            "mm",
            "Generating sphere diameter before clipping and overlap.",
        ),
        ParameterDefinition(
            "lattice_spacing_mm",
            "mm",
            "Nearest-neighbor sphere-center spacing tuned to control porosity.",
        ),
    )
    known_limitations = (
        "Throat size is not explicitly measured in Phase 2B.",
        "Porosity is computed inside the finite clipped domain.",
    )

    def __init__(self, family: StructureFamily) -> None:
        if not family.is_sphere_lattice:
            raise ValueError(f"Not a sphere lattice family: {family.value}")
        self.family = family
        self.lattice = LatticeType.from_family(family)

    def default_search_interval(self, spec: DesignSpecification) -> tuple[float, float]:
        pore = spec.structure.pore_diameter_mm
        if pore is None:
            raise ValueError(f"{self.family.value} requires pore_diameter_mm")
        return (0.5 * pore, 3.0 * pore)

    def generate_voxels(
        self,
        spec: DesignSpecification,
        domain_grid: DomainGrid,
        control_parameter: float,
    ) -> GeneratedField:
        from porous_designer.geometry.voxel import sphere_solid_grid

        pore = spec.structure.pore_diameter_mm
        if pore is None:
            raise ValueError(f"{self.family.value} requires pore_diameter_mm")
        center_predicate = None
        if spec.domain.shape == DomainShape.CYLINDER and not spec.constraints.require_open_pores:
            radius = pore / 2.0
            diameter, height = spec.domain.dimensions_mm
            domain_radius = diameter / 2.0
            cx0 = cy0 = domain_radius

            def center_predicate(c: np.ndarray) -> bool:
                radial = math.hypot(float(c[0]) - cx0, float(c[1]) - cy0)
                return radial <= domain_radius - radius and radius <= float(c[2]) <= height - radius

        grid, center_count = sphere_solid_grid(
            domain_grid.bounds_mm,
            domain_grid.voxel_mm,
            pore / 2.0,
            control_parameter,
            self.lattice,
            domain_mask=domain_grid.mask,
            return_center_count=True,
            center_predicate=center_predicate,
        )
        return GeneratedField(
            solid_grid=grid,
            control_parameter=control_parameter,
            generator_metrics={
                "sphere_center_count": center_count,
                "lattice": self.lattice.value,
            },
        )
