"""Closed-form feasibility of design targets from the property tables.

With lengths per cell size from ``property_tables`` a design point
(family, porosity phi, cell size L) has

    wall(phi, L)   = w(phi) L          pore(phi, L) = p(phi) L
    throat(phi, L) = t(phi) L          k(phi, L)    = kappa(phi) L^2

so the requirement "walls >= w_min (printer) and median pore = d" can only
hold if  d >= w_min * p(phi) / w(phi): the smallest printable pore at that
porosity. Lower porosity (thicker walls per cell), a family with a smaller
pore-to-wall ratio, or a printer with a smaller minimum feature move the
limit. This module evaluates design points, explains violations with
numbers, and proposes the nearest feasible alternatives.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from porous_designer.domain.enums import StructureFamily, TPMSVariant
from porous_designer.knowledge.property_tables import load_tables, porosity_range, properties_at, table_key


@dataclass
class DesignPoint:
    family: str
    variant: str
    porosity: float
    cell_mm: float  # unit cell size (sphere lattices: pore diameter)
    wall_mm: float | None = None
    pore_mm: float | None = None
    throat_mm: float | None = None
    permeability_m2: float | None = None
    youngs_relative: float | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def feasible(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict:
        d = asdict(self)
        d["feasible"] = self.feasible
        return d


@dataclass
class Requirements:
    porosity: float | None = None
    pore_mm: float | None = None
    min_wall_mm: float | None = None  # max(user minimum, printer minimum)
    min_opening_mm: float | None = None  # max(user throat minimum, printer minimum hole)
    permeability_m2: float | None = None
    youngs_relative: float | None = None
    max_cell_mm: float | None = None  # at least two cells across the part
    min_resolvable_mm: float | None = None  # smallest feature the voxel grid can resolve (1.5 voxels at the finest affordable grid)

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


def evaluate(family: StructureFamily, variant: TPMSVariant, porosity: float, cell_mm: float, req: Requirements) -> DesignPoint:
    props = properties_at(family, variant, porosity)
    point = DesignPoint(family.value, TPMSVariant(variant).value, float(porosity), float(cell_mm))
    if props is None:
        point.issues.append("no property table for this family")
        return point
    point.wall_mm = props.wall_d10_per_cell * cell_mm
    point.pore_mm = props.pore_d50_per_cell * cell_mm
    point.throat_mm = props.throat_per_cell * cell_mm
    if "permeability_per_cell2" in props.values:
        point.permeability_m2 = props.permeability_per_cell2 * cell_mm**2 * 1e-6
    if "youngs_relative" in props.values:
        point.youngs_relative = props.youngs_relative
    if props.extrapolated:
        rng = porosity_range(family, variant)
        point.issues.append(f"porosity {porosity:.0%} is outside the tabulated range {rng[0]:.0%}-{rng[1]:.0%} of {table_key(family, variant)}")
    if req.min_wall_mm and point.wall_mm < req.min_wall_mm:
        point.issues.append(f"walls {point.wall_mm:.3f} mm < required {req.min_wall_mm:.3f} mm")
    if req.min_opening_mm and point.throat_mm < req.min_opening_mm:
        point.issues.append(f"pore openings {point.throat_mm:.3f} mm < required {req.min_opening_mm:.3f} mm")
    if req.pore_mm and abs(point.pore_mm - req.pore_mm) > 0.2 * req.pore_mm:
        point.issues.append(f"median pore {point.pore_mm:.3f} mm differs from the target {req.pore_mm:.3f} mm")
    if req.min_resolvable_mm:
        if point.wall_mm < req.min_resolvable_mm:
            point.issues.append(f"walls {point.wall_mm:.3f} mm are below the {req.min_resolvable_mm:.3f} mm the voxel grid can resolve within the memory budget")
        if point.throat_mm < req.min_resolvable_mm:
            point.issues.append(f"pore openings {point.throat_mm:.3f} mm are below the {req.min_resolvable_mm:.3f} mm the voxel grid can resolve within the memory budget")
    if req.max_cell_mm and cell_mm > req.max_cell_mm:
        point.issues.append(f"cell {cell_mm:.2f} mm leaves fewer than two cells across the part (max {req.max_cell_mm:.2f} mm)")
    if req.permeability_m2 and point.permeability_m2 and not (0.7 <= point.permeability_m2 / req.permeability_m2 <= 1.4):
        point.issues.append(f"permeability {point.permeability_m2:.2e} m2 vs target {req.permeability_m2:.2e} m2")
    if req.youngs_relative and point.youngs_relative and abs(point.youngs_relative - req.youngs_relative) > 0.2 * req.youngs_relative:
        point.issues.append(f"relative stiffness {point.youngs_relative:.3f} vs target {req.youngs_relative:.3f}")
    return point


def cell_for_targets(family: StructureFamily, variant: TPMSVariant, porosity: float, req: Requirements) -> tuple[float | None, str]:
    """Cell size that meets the size targets at this porosity (and why)."""
    props = properties_at(family, variant, porosity)
    if props is None:
        return None, "no property table"
    if req.pore_mm:
        return req.pore_mm / props.pore_d50_per_cell, f"median pore {req.pore_mm:.3f} mm / pore-per-cell {props.pore_d50_per_cell:.3f}"
    if req.permeability_m2 and props.values.get("permeability_per_cell2"):
        cell = float(np.sqrt(req.permeability_m2 * 1e6 / props.permeability_per_cell2))
        return cell, f"sqrt(permeability / permeability-per-cell^2 {props.permeability_per_cell2:.2e})"
    # No size target: the smallest cell that satisfies the printer, else None.
    lower = []
    if req.min_wall_mm:
        lower.append(req.min_wall_mm / max(props.wall_d10_per_cell, 1e-6))
    if req.min_opening_mm:
        lower.append(req.min_opening_mm / max(props.throat_per_cell, 1e-6))
    if req.min_resolvable_mm:
        lower.append(req.min_resolvable_mm / max(min(props.wall_d10_per_cell, props.throat_per_cell), 1e-6))
    if lower:
        need = max(lower)
        cell = 1.25 * need
        if req.max_cell_mm and cell > req.max_cell_mm >= need:
            return req.max_cell_mm, "smallest cell meeting the printer's minimum wall and hole (margin limited by the part size)"
        return cell, "smallest cell meeting the printer's minimum wall and hole, with 25 % margin"
    return None, "no size target"


def porosity_for_stiffness(family: StructureFamily, variant: TPMSVariant, youngs_relative: float) -> float | None:
    rows = load_tables().get("families", {}).get(table_key(family, variant)) or []
    pts = sorted((r["porosity"], r.get("youngs_relative")) for r in rows if r.get("youngs_relative"))
    if len(pts) < 2:
        return None
    phis = np.array([p for p, _ in pts])
    es = np.array([e for _, e in pts])
    if not (es.min() <= youngs_relative <= es.max()):
        return None
    order = np.argsort(es)
    return float(np.interp(youngs_relative, es[order], phis[order]))


def smallest_printable_pore(family: StructureFamily, variant: TPMSVariant, porosity: float, min_wall_mm: float) -> float | None:
    props = properties_at(family, variant, porosity)
    if props is None or props.wall_d10_per_cell <= 0:
        return None
    return min_wall_mm * props.pore_d50_per_cell / props.wall_d10_per_cell


def max_porosity_for(family: StructureFamily, variant: TPMSVariant, cell_mm: float, min_wall_mm: float) -> float | None:
    """Highest tabulated porosity whose walls still reach ``min_wall_mm`` at this cell size."""
    rows = load_tables().get("families", {}).get(table_key(family, variant)) or []
    ok = [r["porosity"] for r in rows if r["wall_d10_per_cell"] * cell_mm >= min_wall_mm]
    if not ok:
        return None
    lo, hi = max(ok), min([r["porosity"] for r in rows if r["porosity"] > max(ok)], default=max(ok))
    # refine between the last passing and first failing row
    for phi in np.linspace(lo, hi, 11)[::-1]:
        p = properties_at(family, variant, float(phi))
        if p is not None and p.wall_d10_per_cell * cell_mm >= min_wall_mm:
            return float(phi)
    return float(lo)


@dataclass
class Alternative:
    description: str
    change: dict
    point: DesignPoint

    def to_dict(self) -> dict:
        return {"description": self.description, "change": self.change, "point": self.point.to_dict()}


def nearest_alternatives(family: StructureFamily, variant: TPMSVariant, req: Requirements, *, candidates: list[tuple[StructureFamily, TPMSVariant]] | None = None, printers: list | None = None) -> list[Alternative]:
    """Feasible designs closest to the request, each changing one thing."""
    out: list[Alternative] = []
    phi = req.porosity or 0.7
    wmin = req.min_wall_mm
    # 1. keep family and porosity: larger pores
    if req.pore_mm and wmin:
        d = smallest_printable_pore(family, variant, phi, wmin)
        if d is not None and d > req.pore_mm:
            d *= 1.05
            cell, _ = cell_for_targets(family, variant, phi, Requirements(pore_mm=d))
            point = evaluate(family, variant, phi, cell, Requirements(pore_mm=d, min_wall_mm=wmin, min_opening_mm=req.min_opening_mm, max_cell_mm=req.max_cell_mm))
            if point.feasible:
                out.append(Alternative(f"keep {phi:.0%} porosity, enlarge the pores to {d:.3f} mm", {"pore_mm": round(d, 4)}, point))
    # 2. keep family and pore size: lower porosity
    if req.pore_mm and wmin:
        for trial in np.arange(phi - 0.05, 0.34, -0.05):
            cell, _ = cell_for_targets(family, variant, float(trial), Requirements(pore_mm=req.pore_mm))
            if cell is None:
                break
            point = evaluate(family, variant, float(trial), cell, Requirements(pore_mm=req.pore_mm, min_wall_mm=wmin, min_opening_mm=req.min_opening_mm, max_cell_mm=req.max_cell_mm))
            if point.feasible:
                out.append(Alternative(f"keep {req.pore_mm:.3f} mm pores, lower the porosity to {trial:.0%}", {"porosity": round(float(trial), 3)}, point))
                break
    # 3. another family at the same targets
    for fam, var in candidates or []:
        if (fam, var) == (family, variant) or porosity_range(fam, var) is None:
            continue
        cell, _ = cell_for_targets(fam, var, phi, req)
        if cell is None:
            continue
        point = evaluate(fam, var, phi, cell, req)
        if point.feasible:
            out.append(Alternative(f"use {table_key(fam, var)} instead", {"family": fam.value, "tpms_variant": var.value}, point))
    # 4. another printer
    for profile in printers or []:
        r2 = Requirements(**{**req.to_dict(), "min_wall_mm": profile.min_wall_mm, "min_opening_mm": max(profile.min_hole_mm, req.min_opening_mm or 0.0)})
        cell, _ = cell_for_targets(family, variant, phi, r2)
        if cell is None:
            continue
        point = evaluate(family, variant, phi, cell, r2)
        if point.feasible:
            out.append(Alternative(f"print on {profile.display_name or profile.id}", {"printer_profile": profile.id}, point))
    return out
