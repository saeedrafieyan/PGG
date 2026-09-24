"""Composition of lattice, domain, skin, and grading into one solid field.

``FieldModel`` is built once per specification and grid. It evaluates and
caches everything that does not depend on the tuned control parameter:

* the domain signed distance and inside mask,
* the optional skin field,
* the lattice distance ``D`` (cell units) and local cell size ``L``,
* the grading coordinate and target porosity field.

``field(control)`` then returns the final float32 field in millimetres
(negative = solid) with a few array operations, so porosity tuning costs
almost nothing per iteration. Sphere-pore lattices are the exception: their
control parameter (lattice spacing) moves the pore centres, so each
evaluation rebuilds a KD-tree.

Control parameters:

=====================  =====================================  ============
kind                   control                                decreasing?
=====================  =====================================  ============
sheet / strut / foam   tau = thickness / L                    yes
network TPMS           kappa = offset / L                     yes
any, graded porosity   porosity shift added to the target     no
sphere pores           lattice spacing (mm)                   yes
=====================  =====================================  ============
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any

import numpy as np

from porous_designer.domain.enums import DomainShape, TPMSVariant
from porous_designer.domain.specification import DesignSpecification
from porous_designer.implicit.backend import select_backend
from porous_designer.implicit.calibration import CalibrationCurve, calibration_for
from porous_designer.implicit.domain_sdf import GridGeometry, domain_extents, domain_sdf_grid, load_domain_mesh, skin_region_sdf
from porous_designer.implicit.grading import CellWarp, graded_value, normalized_coordinate
from porous_designer.implicit.lattice import lattice_kind, strut_lattice_distance, tpms_distance

SLAB_POINTS = 4_000_000
VORONOI_REACH_CELLS = 0.8


@dataclass
class ControlProblem:
    """What the tuner varies and how porosity responds."""

    name: str
    units: str
    lo: float
    hi: float
    decreasing: bool
    fixed: float | None = None
    target_porosity: float | None = None


@dataclass
class FieldModel:
    spec: DesignSpecification
    grid: GridGeometry
    kind: str
    domain_sdf: np.ndarray
    inside: np.ndarray
    skin: np.ndarray | None
    porous_region: np.ndarray  # inside the domain and outside the solid skin
    backend_reason: str
    base: np.ndarray | None = None  # D in cell units
    cell: Any = None  # scalar or float32 grid (mm)
    target_porosity_field: np.ndarray | None = None
    calibration: CalibrationCurve | None = None
    sphere_centers_cache: dict = dc_field(default_factory=dict)
    timings: dict[str, float] = dc_field(default_factory=dict)
    _volumes: tuple[float, float] | None = None

    # -- construction ----------------------------------------------------------
    @classmethod
    def build(cls, spec: DesignSpecification, voxel_mm: float, *, mesh=None) -> "FieldModel":
        import time

        t0 = time.perf_counter()
        extents = domain_extents(spec.domain)
        grid = GridGeometry.covering(extents, voxel_mm)
        if spec.domain.shape == DomainShape.MESH and mesh is None:
            mesh = load_domain_mesh(spec.domain)
        grading = spec.targets.porosity_grading
        depth = max(spec.domain.skin_thickness_mm or 0.0, (grading.depth_mm or 0.0) if grading is not None else 0.0)
        sdf = domain_sdf_grid(spec.domain, grid, mesh=mesh, exact_depth_mm=depth)
        inside = sdf <= 0.0
        skin = skin_region_sdf(spec.domain, grid, sdf)
        porous_region = inside if skin is None else inside & (skin > 0.0)
        if not porous_region.any():
            raise ValueError("The solid skin fills the whole domain; reduce skin_thickness_mm.")
        structure = spec.structure
        kind = lattice_kind(structure.family, structure.tpms_variant)
        backend = select_backend(spec.generation.compute_backend, grid.point_count)
        model = cls(spec=spec, grid=grid, kind=kind, domain_sdf=sdf, inside=inside, skin=skin, porous_region=porous_region, backend_reason=backend.reason)
        model.timings["domain_s"] = time.perf_counter() - t0
        if kind != "sphere":
            t1 = time.perf_counter()
            model._build_lattice(backend.ops, extents)
            model.timings["lattice_s"] = time.perf_counter() - t1
            model.calibration = calibration_for(
                structure.family,
                structure.tpms_variant,
                randomness=structure.voronoi_randomness,
                seed=spec.generation.deterministic_seed,
            )
            grading = spec.targets.porosity_grading
            if grading is not None:
                s = np.empty(grid.shape, dtype=np.float32)
                for x0, x1 in model._slabs():
                    pts = grid.slab_points(x0, x1)
                    s[x0:x1] = normalized_coordinate(grading, pts, extents, sdf[x0:x1])
                model.target_porosity_field = graded_value(grading, s)
        return model

    def _slabs(self):
        step = max(1, SLAB_POINTS // max(1, self.grid.shape[1] * self.grid.shape[2]))
        for x0 in range(0, self.grid.shape[0], step):
            yield x0, min(self.grid.shape[0], x0 + step)

    def _build_lattice(self, ops, extents) -> None:
        structure = self.spec.structure
        L0 = float(structure.unit_cell_size_mm)
        warp = CellWarp.from_spec(L0, structure.cell_size_grading, extents)
        base = np.empty(self.grid.shape, dtype=np.float32)
        cell = np.empty(self.grid.shape, dtype=np.float32) if not warp.uniform else L0
        if self.kind == "voronoi":
            from porous_designer.implicit.stochastic import voronoi_edge_distance, voronoi_network

            step = min(self.grid.voxel_mm / 2.0, L0 / 24.0)
            network = voronoi_network(extents, L0, structure.voronoi_randomness, self.spec.generation.deterministic_seed, sample_step_mm=step)
            for x0, x1 in self._slabs():
                pts = np.stack(self.grid.slab_points(x0, x1), axis=-1).reshape(-1, 3)
                d = voronoi_edge_distance(pts, network, reach_mm=VORONOI_REACH_CELLS * L0)
                base[x0:x1] = (d / L0).reshape(x1 - x0, self.grid.shape[1], self.grid.shape[2])
            self.base, self.cell = base, L0
            return
        for x0, x1 in self._slabs():
            X = [ops.asarray(c) for c in self.grid.slab_points(x0, x1)]
            if self.kind == "strut":
                d, L = strut_lattice_distance(ops, structure.family, warp, X)
            else:
                d, L = tpms_distance(ops, structure.family, warp, X, signed=self.kind == "tpms_network")
            base[x0:x1] = ops.to_numpy(d)
            if not warp.uniform:
                cell[x0:x1] = ops.to_numpy(L)
        self.base, self.cell = base, cell

    # -- control problem ---------------------------------------------------------
    def mean_target_porosity(self) -> float:
        if self.target_porosity_field is None:
            return float(self.spec.targets.porosity_target.target)
        return float(self.target_porosity_field[self.porous_region].mean())

    def control_problem(self) -> ControlProblem:
        structure = self.spec.structure
        if self.kind == "sphere":
            pore = float(structure.pore_diameter_mm)
            fixed = structure.lattice_spacing_mm if structure.lattice_spacing_mm else None
            return ControlProblem("lattice_spacing_mm", "mm", 0.5 * pore, 3.0 * pore, True, fixed=fixed, target_porosity=self.mean_target_porosity())
        if self.target_porosity_field is not None:
            return ControlProblem("porosity_shift", "fraction", -0.3, 0.3, False, target_porosity=self.mean_target_porosity())
        L0 = float(structure.unit_cell_size_mm)
        if self.kind == "tpms_network":
            fixed = structure.network_offset_mm / L0 if structure.network_offset_mm is not None else None
            return ControlProblem("kappa", "offset / cell", -0.6, 0.6, True, fixed=fixed, target_porosity=self.mean_target_porosity())
        fixed = structure.wall_thickness_mm / L0 if structure.wall_thickness_mm is not None else None
        return ControlProblem("tau", "thickness / cell", 0.002, 1.2, True, fixed=fixed, target_porosity=self.mean_target_porosity())

    def tight_interval(self, target: float, margin: float = 0.12) -> tuple[float, float] | None:
        """Bracket from the calibration curve (None for sphere lattices)."""
        if self.calibration is None or self.target_porosity_field is not None:
            return None
        hi = float(self.calibration.parameter_for(max(target - margin, 0.001)))
        lo = float(self.calibration.parameter_for(min(target + margin, 0.999)))
        problem = self.control_problem()
        lo, hi = max(problem.lo, lo), min(problem.hi, hi)
        return (lo, hi) if hi > lo else None

    # -- evaluation ----------------------------------------------------------------
    def _local_control(self, control: float):
        if self.target_porosity_field is not None:
            assert self.calibration is not None
            return self.calibration.parameter_for(np.clip(self.target_porosity_field + control, 0.001, 0.999))
        return np.float32(control)

    def lattice_field(self, control: float) -> np.ndarray:
        if self.kind == "sphere":
            return self._sphere_field(control)
        assert self.base is not None
        local = self._local_control(control)
        if self.kind == "tpms_network":
            return (self.cell * (self.base - local)).astype(np.float32, copy=False)
        return (self.cell * (self.base - local / 2.0)).astype(np.float32, copy=False)

    def _sphere_field(self, spacing: float) -> np.ndarray:
        from porous_designer.generators.sphere_lattices import LatticeType, filter_intersecting_centers, generate_sphere_centers
        from porous_designer.implicit.stochastic import sphere_pore_distance

        spec = self.spec
        pore_r = float(spec.structure.pore_diameter_mm) / 2.0
        key = round(float(spacing), 12)
        centers = self.sphere_centers_cache.get(key)
        if centers is None:
            lattice = LatticeType.from_family(spec.structure.family)
            bounds = self.grid.bounds_mm
            centers = generate_sphere_centers(bounds, spacing, pore_r, lattice)
            centers = filter_intersecting_centers(centers, pore_r, bounds)
            if spec.domain.shape == DomainShape.CYLINDER and not spec.constraints.require_open_pores:
                diameter, height = spec.domain.dimensions_mm
                R = diameter / 2.0
                radial = np.hypot(centers[:, 0] - R, centers[:, 1] - R)
                keep = (radial <= R - pore_r) & (centers[:, 2] >= pore_r) & (centers[:, 2] <= height - pore_r)
                centers = centers[keep]
            self.sphere_centers_cache = {key: centers}
        out = np.empty(self.grid.shape, dtype=np.float32)
        for x0, x1 in self._slabs():
            pts = np.stack(self.grid.slab_points(x0, x1), axis=-1).reshape(-1, 3)
            d = sphere_pore_distance(pts, centers, pore_r)
            out[x0:x1] = (-d).reshape(x1 - x0, self.grid.shape[1], self.grid.shape[2])
        return out

    def sphere_center_count(self) -> int:
        return int(next(iter(self.sphere_centers_cache.values()), np.zeros((0, 3))).shape[0])

    def field(self, control: float) -> np.ndarray:
        """Final solid field (mm, negative = solid): lattice within the domain, plus skin."""
        f = np.maximum(self.lattice_field(control), self.domain_sdf)
        if self.skin is not None:
            f = np.minimum(f, self.skin)
        return f

    def _occupancy(self, f: np.ndarray) -> np.ndarray:
        """Partial-volume solid fraction per voxel from a distance-like field.

        Counting voxel centres aliases badly when a periodic lattice lines up
        with the grid (whole planes of samples flip at once) and makes the
        porosity a staircase in the control parameter. The fraction of each
        voxel on the solid side of the (locally planar) surface is smooth and
        tracks the continuous geometry - and hence the mesh - closely.
        """
        return np.clip(0.5 - f / self.grid.voxel_mm, 0.0, 1.0)

    def _region_volumes(self) -> tuple[float, float]:
        """Partial-volume (domain, skin) sizes in voxels, cached."""
        if self._volumes is None:
            domain = float(self._occupancy(self.domain_sdf).sum(dtype=np.float64))
            skin = float(self._occupancy(self.skin).sum(dtype=np.float64)) if self.skin is not None else 0.0
            self._volumes = (domain, skin)
        return self._volumes

    def _lattice_occupancy(self, control: float) -> np.ndarray:
        """Partial-volume solid fraction of the lattice alone.

        Sheets, struts and foam edges are walls of thickness t around a
        mid-surface or axis at distance d; the fraction of a voxel (size h)
        inside is the overlap of [d - h/2, d + h/2] with [-t/2, t/2] divided
        by h. Unlike clip(0.5 - F/h) this stays right for walls thinner than
        a voxel (t/h, not ~1/2), which matters on coarse tuning grids. Struts
        are also thin across the second direction, hence the extra factor.
        """
        h = self.grid.voxel_mm
        if self.kind in ("sphere", "tpms_network") or self.base is None:
            return self._occupancy(self.lattice_field(control))
        dist = self.cell * self.base
        half = (self.cell * self._local_control(control) / 2.0).astype(np.float32)
        overlap = np.minimum(dist + h / 2.0, half) - np.maximum(dist - h / 2.0, -half)
        occ = np.clip(overlap / h, 0.0, 1.0)
        if self.kind in ("strut", "voronoi"):
            occ *= np.minimum(1.0, 2.0 * half / h)
        return occ.astype(np.float32, copy=False)

    def solid_occupancy(self, control: float) -> np.ndarray:
        """Partial-volume solid fraction of the final part (lattice in domain, plus skin)."""
        occ = self._lattice_occupancy(control) * self._occupancy(self.domain_sdf)
        if self.skin is not None:
            skin = self._occupancy(self.skin)
            occ = occ + skin - occ * skin
        return occ

    def porosity(self, control: float) -> float:
        """Porosity of the porous region (the domain minus any solid skin).

        The skin lies inside the domain, so the solid in the core is the total
        solid minus the skin, and the core volume is the domain minus the skin.
        """
        domain, skin = self._region_volumes()
        core = domain - skin
        if core <= 0:
            return 0.0
        solid = float(self.solid_occupancy(control).sum(dtype=np.float64)) - skin
        return float(min(1.0, max(0.0, 1.0 - solid / core)))

    def voxel_count_porosity(self, control: float) -> float:
        """Porosity from voxel-centre sampling (the binary voxel model)."""
        solid = (self.field(control) <= 0.0) & self.porous_region
        total = int(self.porous_region.sum())
        return float(1.0 - solid.sum() / total) if total else 0.0

    # -- reporting -------------------------------------------------------------
    def thickness_summary(self, control: float) -> dict[str, Any]:
        """Physical thickness (mm) implied by the tuned control parameter."""
        if self.kind == "sphere" or self.base is None:
            return {}
        if self.target_porosity_field is not None:
            assert self.calibration is not None
            local = self.calibration.parameter_for(np.clip(self.target_porosity_field + control, 0.001, 0.999))
            mm = (local * self.cell)[self.inside]
            key = "network_offset_mm" if self.kind == "tpms_network" else "wall_thickness_mm"
            return {f"{key}_min": float(mm.min()), f"{key}_max": float(mm.max()), f"{key}_mean": float(mm.mean())}
        cell = self.cell if np.isscalar(self.cell) else np.asarray(self.cell)[self.inside]
        mm = np.asarray(control * cell)
        key = "network_offset_mm" if self.kind == "tpms_network" else "wall_thickness_mm"
        if mm.ndim == 0:
            return {key: float(mm)}
        return {f"{key}_min": float(mm.min()), f"{key}_max": float(mm.max()), f"{key}_mean": float(mm.mean())}

    def porosity_profile(self, control: float, bins: int = 10) -> list[dict[str, float]] | None:
        """Achieved vs target porosity along the grading coordinate."""
        if self.target_porosity_field is None:
            return None
        solid = self.solid_occupancy(control)
        volume = self._occupancy(self.domain_sdf)
        if self.skin is not None:
            skin = self._occupancy(self.skin)
            solid, volume = solid - skin, volume - skin
        target = self.target_porosity_field
        grading = self.spec.targets.porosity_grading
        assert grading is not None
        s = np.clip((target - grading.start) / (grading.end - grading.start), 0.0, 1.0) if grading.end != grading.start else np.zeros_like(target)
        rows = []
        edges = np.linspace(0.0, 1.0, bins + 1)
        for lo, hi in zip(edges[:-1], edges[1:]):
            sel = self.porous_region & (s >= lo) & ((s < hi) if hi < 1.0 else (s <= hi))
            n = int(sel.sum())
            if n < 50:
                continue
            rows.append({
                "s_from": float(lo),
                "s_to": float(hi),
                "target": float(target[sel].mean()),
                "achieved": float(1.0 - solid[sel].sum(dtype=np.float64) / max(float(volume[sel].sum(dtype=np.float64)), 1e-9)),
                "voxels": n,
            })
        return rows


def tpms_reference_note(variant: TPMSVariant) -> str:
    if variant == TPMSVariant.SHEET:
        return "Solid where |f|/|grad f| <= t/2 (sheet of physical thickness t)."
    return "Solid where f/|grad f| <= c (network, offset c from the minimal surface)."


__all__ = ["ControlProblem", "FieldModel", "tpms_reference_note"]
