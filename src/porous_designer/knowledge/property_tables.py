"""Structure-property maps measured on periodic cells.

For every family (and TPMS variant) the periodic RVE is built at a ladder of
porosities with cell size 1, and measured with the Phase 4.2 tools. All
lengths are therefore *per unit cell size* (sphere lattices: per pore
diameter), so for any design

    wall  = wall_d10_per_cell  * L        pore = pore_d50_per_cell * L
    throat = throat_per_cell   * L        k    = permeability_per_cell2 * L^2
    E*/Es  = youngs_relative (size independent)

The tables are generated once (``porous-designer build-property-tables``)
and shipped as ``knowledge/data/property_tables.json``; the agent
interpolates them in porosity. They are also a results figure: property
maps of 23 architectures from one consistent solver chain.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from porous_designer.domain.enums import StructureFamily, TPMSVariant

DATA_FILE = Path(__file__).resolve().parent / "data" / "property_tables.json"
POROSITIES = [round(0.35 + 0.05 * i, 2) for i in range(12)]  # 0.35 ... 0.90
SPHERE_SPACING_RATIOS = [round(v, 3) for v in np.linspace(0.72, 0.98, 10)]  # s / d (s < d: overlapping, open pores)
MAX_SPHERE_POROSITY = 0.96  # above this the walls between overlapping spheres vanish
FIELDS = (
    "porosity",
    "wall_d10_per_cell",
    "wall_d50_per_cell",
    "pore_d10_per_cell",
    "pore_d50_per_cell",
    "throat_per_cell",
    "surface_per_cell_inv",
    "permeability_per_cell2",
    "youngs_relative",
    "control",
)


def table_key(family: StructureFamily, variant: TPMSVariant | str = TPMSVariant.SHEET) -> str:
    variant = TPMSVariant(variant)
    return f"{family.value}:{variant.value}" if family.is_tpms else family.value


def all_keys() -> list[tuple[StructureFamily, TPMSVariant]]:
    keys = []
    for family in StructureFamily:
        if family.is_tpms:
            keys += [(family, TPMSVariant.SHEET), (family, TPMSVariant.NETWORK)]
        else:
            keys.append((family, TPMSVariant.SHEET))
    return keys


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def _surface_area_voxels(solid: np.ndarray) -> float:
    """Surface area (in voxel face units) of a periodic binary phase, corrected for staircase."""
    faces = 0
    for axis in range(3):
        faces += int(np.count_nonzero(solid != np.roll(solid, 1, axis=axis)))
    return faces * (2.0 / 3.0)  # Cauchy-Crofton correction for voxel face counts of isotropic surfaces


def _measure(rve, *, with_physics: bool, reference_mm: float = 1.0) -> dict:
    """Measure an RVE; lengths are divided by ``reference_mm`` (cell size or pore diameter)."""
    from porous_designer.metrology import morphology as mm
    from porous_designer.metrology.report import _rve_measure

    out = _rve_measure(rve, level="basic", anisotropic=False, notes=[])
    h = rve.voxel_mm
    cell = reference_mm
    tiled = np.tile(rve.solid, (2, 2, 2))
    throat = mm.percolation_diameter(~tiled, 2, h)
    row = {
        "porosity": rve.porosity,
        "wall_d10_per_cell": out.get("wall_d10_mm", 0.0) / cell,
        "wall_d50_per_cell": out.get("wall_d50_mm", 0.0) / cell,
        "pore_d10_per_cell": out.get("pore_d10_mm", 0.0) / cell,
        "pore_d50_per_cell": out.get("pore_d50_mm", 0.0) / cell,
        "throat_per_cell": throat / cell,
        "surface_per_cell_inv": _surface_area_voxels(rve.solid) * h * h / float(np.prod(rve.lengths_mm)) * cell,
    }
    if with_physics:
        from porous_designer.metrology.homogenization import effective_stiffness
        from porous_designer.metrology.lbm import permeability

        k = permeability(rve.solid, h, 2, max_seconds=30.0)
        row["permeability_per_cell2"] = k.permeability_mm2 / cell**2
        row["youngs_relative"] = float(min(effective_stiffness(rve.solid, tol=1e-4).youngs_relative))
    return row


def build_family_table(family: StructureFamily, variant: TPMSVariant, *, with_physics: bool = True, n: int = 48) -> list[dict]:
    from porous_designer.implicit.calibration import calibration_for
    from porous_designer.metrology.rve import sphere_lattice_rve, unit_cell_rve, voronoi_rve

    rows = []
    if family.is_sphere_lattice:
        for ratio in SPHERE_SPACING_RATIOS:
            # Pore diameter 1: every length is per generating-sphere diameter.
            rve = sphere_lattice_rve(family, ratio, 1.0, voxel_mm=ratio / 48.0)
            row = _measure(rve, with_physics=with_physics, reference_mm=1.0)
            row["control"] = ratio
            if row["porosity"] <= MAX_SPHERE_POROSITY:
                rows.append(row)
        return sorted(rows, key=lambda r: r["porosity"])
    calibration = calibration_for(family, variant)
    lo, hi = calibration.porosity_range
    for phi in POROSITIES:
        if not (lo + 0.01 < phi < hi - 0.01):
            continue
        control = float(calibration.parameter_for(phi))
        if family.is_stochastic:
            rve = voronoi_rve(control, 1.0, 1.0, 42, cells=3, n_per_cell=24)
        else:
            rve = unit_cell_rve(family, variant, control, 1.0, n=n)
        row = _measure(rve, with_physics=with_physics, reference_mm=1.0)
        row["control"] = control
        rows.append(row)
    return rows


def build_tables(path: Path = DATA_FILE, *, with_physics: bool = True, log=print) -> dict:
    tables = {"version": 1, "porosities": POROSITIES, "note": "lengths per unit cell (sphere lattices: per pore diameter)", "families": {}}
    for family, variant in all_keys():
        t0 = time.perf_counter()
        rows = build_family_table(family, variant, with_physics=with_physics)
        tables["families"][table_key(family, variant)] = rows
        log(f"{table_key(family, variant):28s} {len(rows):2d} rows  {time.perf_counter() - t0:6.1f} s")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tables, indent=1), encoding="utf-8")
    load_tables.cache_clear()
    return tables


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_tables() -> dict:
    if not DATA_FILE.exists():
        return {"families": {}}
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


@dataclass
class FamilyProperties:
    family: StructureFamily
    variant: TPMSVariant
    porosity: float
    values: dict
    extrapolated: bool

    def __getattr__(self, name):
        try:
            return self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def properties_at(family: StructureFamily, variant: TPMSVariant | str, porosity: float) -> FamilyProperties | None:
    rows = load_tables().get("families", {}).get(table_key(family, variant))
    if not rows:
        return None
    phis = np.array([r["porosity"] for r in rows])
    order = np.argsort(phis)
    phis = phis[order]
    rows = [rows[i] for i in order]
    extrapolated = not (phis[0] <= porosity <= phis[-1])
    values = {}
    for key in FIELDS:
        ys = np.array([r.get(key, np.nan) for r in rows], dtype=float)
        ok = np.isfinite(ys)
        if ok.sum() == 0:
            continue
        if key == "permeability_per_cell2" and np.all(ys[ok] > 0):
            values[key] = float(np.exp(np.interp(porosity, phis[ok], np.log(ys[ok]))))
        else:
            values[key] = float(np.interp(porosity, phis[ok], ys[ok]))
    values["porosity"] = float(porosity)
    return FamilyProperties(StructureFamily(family), TPMSVariant(variant), float(porosity), values, extrapolated)


def porosity_range(family: StructureFamily, variant: TPMSVariant | str) -> tuple[float, float] | None:
    rows = load_tables().get("families", {}).get(table_key(family, variant))
    if not rows:
        return None
    phis = [r["porosity"] for r in rows]
    return float(min(phis)), float(max(phis))
