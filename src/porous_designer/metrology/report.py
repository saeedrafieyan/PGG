"""Run the measurements for a generated part and derive validation checks.

Levels
------
``none``   nothing.
``basic``  as-built morphology of the part (pore / wall / throat sizes,
           closed pores, drainage curve, tortuosity, surface area, curvature)
           plus exact pore / wall sizes on the periodic RVE(s).
``full``   basic + permeability (lattice Boltzmann) and effective stiffness
           (FFT homogenisation) on the RVE(s).

Part-level measurements run on a central sub-volume when the grid is larger
than ``max_voxels``; the report says so.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from porous_designer.domain.enums import Severity, StructureFamily, ValidationStatus
from porous_designer.domain.validation import ValidationCheck
from porous_designer.metrology import morphology as mm
from porous_designer.metrology.rve import RVE, design_rves, measurement_grid

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


@dataclass
class MetrologyReport:
    level: str
    voxel_mm: float
    part: dict[str, Any] = field(default_factory=dict)
    rve: list[dict[str, Any]] = field(default_factory=list)
    timings_s: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"level": self.level, "voxel_mm": self.voxel_mm, "part": self.part, "rve": self.rve, "timings_s": self.timings_s, "notes": self.notes}

    # -- convenient headline values ------------------------------------------
    def rve_value(self, key: str, reducer=min) -> float | None:
        values = [r[key] for r in self.rve if r.get(key) is not None]
        return float(reducer(values)) if values else None

    def headline(self) -> dict[str, Any]:
        part = self.part
        out = {
            "pore_d50_mm": self.rve_value("pore_d50_mm", reducer=lambda v: float(np.mean(v))) or part.get("pore_size", {}).get("d50_mm"),
            "wall_d50_mm": self.rve_value("wall_d50_mm", reducer=lambda v: float(np.mean(v))) or part.get("wall_thickness", {}).get("d50_mm"),
            "wall_min_mm": self.rve_value("wall_d10_mm") or part.get("wall_thickness", {}).get("d10_mm"),
            "percolation_diameter_mm": part.get("percolation_diameter_min_mm"),
            "closed_void_fraction": part.get("closed_pores", {}).get("closed_void_fraction"),
            "specific_surface_per_mm": part.get("specific_surface_per_mm"),
            "tortuosity": part.get("tortuosity_mean"),
            "permeability_m2": self.rve_value("permeability_m2", reducer=lambda v: float(np.mean(v))),
            "youngs_relative": self.rve_value("youngs_relative_min"),
        }
        return {k: v for k, v in out.items() if v is not None}


def _time(timings: dict, key: str, t0: float) -> None:
    timings[key] = round(time.perf_counter() - t0, 3)


def _rve_measure(rve: RVE, *, level: str, anisotropic: bool, notes: list[str]) -> dict[str, Any]:
    out = rve.summary()
    h = rve.voxel_mm
    grid, gh = measurement_grid(rve.solid, h)
    out["measurement_grid"] = {"shape": list(grid.shape), "voxel_mm": gh}
    # Wrap-pad so sizes near the cell faces see their periodic neighbours.
    pad = tuple((n // 3, n // 3) for n in grid.shape)
    wrapped = np.pad(grid, pad, mode="wrap")
    centre = tuple(slice(p, p + n) for (p, _), n in zip(pad, grid.shape))
    for phase_name, phase in (("pore", ~wrapped), ("wall", wrapped)):
        size = mm.local_size(phase)[centre] * gh
        values = size[(~grid) if phase_name == "pore" else grid]
        if values.size:
            q = np.percentile(values, [5, 10, 50, 90])
            out[f"{phase_name}_d05_mm"], out[f"{phase_name}_d10_mm"], out[f"{phase_name}_d50_mm"], out[f"{phase_name}_d90_mm"] = (float(v) for v in q)
            out[f"{phase_name}_mean_mm"] = float(values.mean())
    if level == "full":
        from porous_designer.metrology.homogenization import effective_stiffness
        from porous_designer.metrology.lbm import permeability

        # Cubic lattices are isotropic in permeability; HCP is transversely isotropic (x = y).
        axes = (0, 2) if rve.note.startswith("hcp") else ((0, 1, 2) if anisotropic else (2,))
        perms = []
        # Flow and stiffness use the full RVE: narrow windows and thin ligaments
        # control them, and coarser grids bias both by ~10 %.
        flow_solid, flow_h = rve.solid, h
        for a in axes:
            try:
                perms.append(permeability(flow_solid, flow_h, a, max_seconds=60.0).to_dict())
            except Exception as exc:  # measurement must never break a run
                notes.append(f"permeability ({'xyz'[a]}) failed on {rve.label}: {exc}")
        if perms:
            out["permeability"] = perms
            out["permeability_m2"] = float(np.mean([p["permeability_m2"] for p in perms]))
            out["permeability_converged"] = all(p["converged"] for p in perms)
            if not out["permeability_converged"]:
                notes.append(f"permeability on {rve.label} stopped at the time budget; the value is a lower bound (very narrow windows converge slowly)")
        try:
            stiff = effective_stiffness(rve.solid).to_dict()
            out["stiffness"] = stiff
            out["youngs_relative_min"] = float(min(stiff["youngs_relative"]))
        except Exception as exc:
            notes.append(f"stiffness failed on {rve.label}: {exc}")
    return out


def measure_part(
    spec,
    *,
    level: str,
    solid: np.ndarray,
    inside: np.ndarray,
    voxel_mm: float,
    open_axes: tuple[str, ...],
    mesh=None,
    field: np.ndarray | None = None,
    domain_sdf: np.ndarray | None = None,
    domain_volume_mm3: float | None = None,
    control_name: str = "",
    control: float | None = None,
    calibration=None,
    max_voxels: int = 1_500_000,
) -> MetrologyReport:
    report = MetrologyReport(level=level, voxel_mm=voxel_mm)
    if level == "none":
        return report
    timings, notes, part = report.timings_s, report.notes, report.part
    solid = solid.astype(bool) & inside
    void = (~solid) & inside

    crop = mm.central_crop(solid.shape, max_voxels)
    if any(s.stop - s.start < n for s, n in zip(crop, solid.shape)):
        notes.append(f"Size distributions measured on the central {'x'.join(str(s.stop - s.start) for s in crop)}-voxel sub-volume.")
    t0 = time.perf_counter()
    part["pore_size"] = mm.size_distribution(void[crop], voxel_mm, "pore").to_dict()
    part["wall_thickness"] = mm.size_distribution(solid[crop], voxel_mm, "wall").to_dict()
    _time(timings, "size_distributions", t0)

    t0 = time.perf_counter()
    perc = {}
    tort = {}
    for name in open_axes:
        a = AXIS_INDEX[name]
        sub = mm.central_crop(solid.shape, max_voxels, keep_axis=a)
        perc[name] = mm.percolation_diameter(void[sub], a, voxel_mm)
        tort[name] = mm.geometric_tortuosity(void[sub], a)
    part["percolation_diameter_mm"] = perc
    part["percolation_diameter_min_mm"] = min(perc.values()) if perc else None
    part["tortuosity"] = tort
    finite = [v for v in tort.values() if v is not None]
    part["tortuosity_mean"] = float(np.mean(finite)) if finite else None
    _time(timings, "throats_and_tortuosity", t0)

    t0 = time.perf_counter()
    if open_axes:
        curve = mm.intrusion_curve(void[crop], tuple(AXIS_INDEX[a] for a in open_axes), voxel_mm)
        part["intrusion"] = curve.to_dict()
    part["closed_pores"] = mm.closed_pores(solid, voxel_mm, inside).to_dict()
    _time(timings, "intrusion_and_closed_pores", t0)

    if mesh is not None:
        area = float(mesh.area)
        vol = domain_volume_mm3 or float(inside.sum() * voxel_mm**3)
        part["surface_area_mm2"] = area
        part["specific_surface_per_mm"] = area / vol
        solid_vol = float(abs(mesh.volume))
        part["surface_per_solid_volume_per_mm"] = area / solid_vol if solid_vol > 0 else None
    if field is not None:
        t0 = time.perf_counter()
        interior = domain_sdf < -2.0 * voxel_mm if domain_sdf is not None else None
        curv = mm.field_curvature(field, voxel_mm, interior=interior)
        part["curvature"] = curv.to_dict() if curv else None
        _time(timings, "curvature", t0)

    if control is not None:
        t0 = time.perf_counter()
        try:
            rves = design_rves(spec, control_name, float(control), calibration=calibration)
        except Exception as exc:
            rves = []
            notes.append(f"RVE could not be built: {exc}")
        family = spec.structure.family
        anisotropic = family.is_stochastic or family == StructureFamily.HCP_SPHERICAL_PORES or spec.targets.porosity_grading is not None
        for rve in rves:
            report.rve.append(_rve_measure(rve, level=level, anisotropic=anisotropic, notes=notes))
        _time(timings, "rve", t0)
    return report


# ---------------------------------------------------------------------------
# Checks against the specification
# ---------------------------------------------------------------------------


def metrology_checks(spec, report: MetrologyReport, *, percolation_axes: tuple[str, ...]) -> list[ValidationCheck]:
    if report.level == "none":
        return []
    checks: list[ValidationCheck] = []
    h = report.voxel_mm
    head = report.headline()
    c = spec.constraints

    min_wall = c.minimum_wall_thickness_mm or spec.targets.wall_target_mm
    wall_min = head.get("wall_min_mm")  # 10th percentile (5th is dominated by voxel staircases on diagonal struts)
    if min_wall is not None and wall_min is not None:
        # Measured sizes carry about half a voxel of quantisation.
        ok = wall_min + 0.5 * h >= min_wall
        checks.append(
            ValidationCheck(
                name="minimum_wall_thickness",
                requested_value=f">= {min_wall}",
                achieved_value=round(wall_min, 4),
                units="mm",
                tolerance=round(0.5 * h, 4),
                status=ValidationStatus.PASS if ok else ValidationStatus.FAIL,
                severity=Severity.CRITICAL if not ok else Severity.INFO,
                method="10th percentile of the local wall/strut thickness (maximal inscribed sphere) on the design RVE",
                message="Thinnest walls meet the minimum." if ok else "The thinnest 10 % of the walls are below the requested minimum thickness.",
            )
        )
    min_throat = c.minimum_throat_size_mm or spec.targets.throat_target_mm
    perc = report.part.get("percolation_diameter_min_mm")
    if min_throat is not None and perc is not None and percolation_axes:
        ok = perc + 0.5 * h >= min_throat
        checks.append(
            ValidationCheck(
                name="minimum_throat_size",
                requested_value=f">= {min_throat}",
                achieved_value=round(perc, 4),
                units="mm",
                tolerance=round(0.5 * h, 4),
                status=ValidationStatus.PASS if ok else ValidationStatus.FAIL,
                severity=Severity.CRITICAL if not ok else Severity.INFO,
                method="largest sphere that crosses the part along each open axis (percolation diameter), minimum over axes",
                message="A sphere of the minimum throat size passes through the part." if ok else "No path through the part admits a sphere of the requested throat size.",
            )
        )
    pore_target = spec.targets.pore_size_target_mm
    pore = head.get("pore_d50_mm")
    if pore_target is not None and pore is not None:
        dev = abs(pore - pore_target) / pore_target
        ok = dev <= 0.2 or abs(pore - pore_target) <= h
        checks.append(
            ValidationCheck(
                name="pore_size_median",
                requested_value=pore_target,
                achieved_value=round(pore, 4),
                units="mm",
                tolerance="20 % or one voxel",
                status=ValidationStatus.PASS if ok else ValidationStatus.WARNING,
                severity=Severity.INFO if ok else Severity.WARNING,
                method="volume-weighted median of the maximal-inscribed-sphere pore size",
                message=f"Median pore size deviates by {dev:.0%} from the target.",
            )
        )
    closed = report.part.get("closed_pores", {})
    if closed and spec.constraints.require_open_pores and percolation_axes:
        frac = closed.get("closed_void_fraction", 0.0)
        ok = frac <= 0.01
        checks.append(
            ValidationCheck(
                name="closed_pores",
                requested_value="<= 0.01",
                achieved_value=round(frac, 5),
                units="fraction of void",
                tolerance=0.01,
                status=ValidationStatus.PASS if ok else ValidationStatus.WARNING,
                severity=Severity.INFO if ok else Severity.WARNING,
                method="void components without a path to the outside",
                message=f"{closed.get('count', 0)} closed pore(s); they trap resin or cells and cannot be seeded or washed." if not ok else "No significant closed pores.",
            )
        )
    return checks
