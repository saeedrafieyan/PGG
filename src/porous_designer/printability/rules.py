"""Process-specific printability rules.

Rules use the *measured* geometry (Phase 4.2 metrology), not the nominal
parameters, and a printer profile. Each rule becomes a validation check
named ``print_*``. A violated rule is a warning unless the specification sets
``manufacturing.enforce_printability``, in which case it fails the run.

FDM / bioprinting (extrusion): wall vs line width, vertical holes, islands,
    overhang area.
SLA / DLP: walls, holes, islands, overhangs, closed pores (trapped resin),
    resin drainage through the throats.
Volumetric: fits the vial, walls, holes, closed pores, wash-out through the
    throats, and the stray-dose risk of fine pores inside thick parts;
    overhangs are ignored.
SLS / LPBF: walls, holes, closed pores and powder removal; LPBF overhangs.

Minimal surfaces have non-positive Gaussian curvature, so the height function
on them has no local minima: TPMS sheets create no unsupported islands, which
is why they are regarded as self-supporting. The island count checks this.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from porous_designer.domain.enums import Severity, ValidationStatus
from porous_designer.domain.validation import ValidationCheck
from porous_designer.printability.profiles import PrinterProfile

LAYERED = {"fdm", "sla", "dlp", "bioprinting", "lpbf", "sls"}
EXTRUSION = {"fdm", "bioprinting"}


@dataclass
class PrintabilityReport:
    profile_id: str
    process: str
    enforced: bool
    checks: list[ValidationCheck] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def violations(self) -> list[ValidationCheck]:
        return [c for c in self.checks if c.status != ValidationStatus.PASS]

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "process": self.process,
            "enforced": self.enforced,
            "violations": len(self.violations),
            "metrics": self.metrics,
            "checks": [c.model_dump(mode="json") for c in self.checks],
        }


def layer_islands(solid: np.ndarray, voxel_mm: float, layer_mm: float | None, max_overhang_deg: float | None, *, min_area_mm2: float = 0.0) -> dict:
    """Solid regions that start in mid-air (nothing below them in the previous layer).

    A region in layer k counts as supported if it overlaps the previous
    layer grown by the self-supporting overhang allowance
    (layer height x tan(max overhang)). The first layer sits on the plate.
    """
    step = max(1, int(round((layer_mm or voxel_mm) / voxel_mm)))
    layers = solid[:, :, ::step]
    allowance = (layer_mm or voxel_mm) * math.tan(math.radians(max_overhang_deg or 45.0))
    grow = max(1, int(round(allowance / voxel_mm)))
    count = 0
    area_voxels = 0
    first = None
    structure = np.ones((3, 3), dtype=bool)
    start = next((k for k in range(layers.shape[2]) if layers[:, :, k].any()), None)
    if start is None:
        return {"island_count": 0, "island_area_mm2": 0.0, "lowest_island_z_mm": None}
    prev = layers[:, :, start]
    for k in range(start + 1, layers.shape[2]):
        cur = layers[:, :, k]
        if not cur.any():
            prev = cur
            continue
        support = ndimage.binary_dilation(prev, structure=structure, iterations=grow) if prev.any() else prev
        labels, n = ndimage.label(cur, structure=structure)
        supported = set(np.unique(labels[support & cur])) - {0}
        sizes = np.bincount(labels.ravel(), minlength=n + 1)
        # Specks of a few voxels are staircase artefacts of the voxel grid, not printable islands.
        min_voxels = max(4.0, min_area_mm2 / voxel_mm**2)
        unsupported = [i for i in range(1, n + 1) if i not in supported and sizes[i] >= min_voxels]
        if unsupported:
            count += len(unsupported)
            area_voxels += int(sum(sizes[i] for i in unsupported))
            if first is None:
                first = k * step * voxel_mm
        prev = cur
    return {"island_count": count, "island_area_mm2": float(area_voxels * voxel_mm**2), "lowest_island_z_mm": first}


def overhang_fraction(mesh, max_overhang_deg: float, layer_mm: float | None) -> float:
    """Share of the surface that faces down more steeply than the process allows."""
    normals = mesh.face_normals
    areas = mesh.area_faces
    centroids = mesh.triangles_center
    z0 = float(mesh.bounds[0][2])
    limit = -math.sin(math.radians(max_overhang_deg))
    down = (normals[:, 2] < limit) & (centroids[:, 2] > z0 + (layer_mm or 0.0) + 1e-6)
    total = float(areas.sum())
    return float(areas[down].sum() / total) if total > 0 else 0.0


def _check(name, requested, achieved, units, ok, message_ok, message_bad, method, enforced, *, soft=False) -> ValidationCheck:
    if ok:
        status, severity = ValidationStatus.PASS, Severity.INFO
    elif enforced and not soft:
        status, severity = ValidationStatus.FAIL, Severity.CRITICAL
    else:
        status, severity = ValidationStatus.WARNING, Severity.WARNING
    return ValidationCheck(
        name=name,
        requested_value=requested,
        achieved_value=achieved if not isinstance(achieved, float) else round(achieved, 4),
        units=units,
        status=status,
        severity=severity,
        method=method,
        message=message_ok if ok else message_bad,
    )


def evaluate_printability(spec, profile: PrinterProfile, *, metrology, mesh=None, solid: np.ndarray | None = None, voxel_mm: float | None = None, enforce: bool = False) -> PrintabilityReport:
    report = PrintabilityReport(profile_id=profile.id, process=profile.process, enforced=enforce)
    checks, metrics = report.checks, report.metrics
    head = metrology.headline() if metrology is not None else {}
    process = profile.process
    label = profile.display_name or profile.id

    # --- fit -----------------------------------------------------------------
    if mesh is not None:
        ext = [float(v) for v in mesh.extents]
        metrics["extents_mm"] = ext
        if profile.vial_diameter_mm:
            round_part = getattr(getattr(spec, "domain", None), "shape", None) in ("cylinder", "sphere")  # str enum
            radial = max(ext[0], ext[1]) if round_part else math.hypot(ext[0], ext[1])
            ok = radial <= profile.vial_diameter_mm and (profile.vial_height_mm is None or ext[2] <= profile.vial_height_mm)
            checks.append(_check("print_fits_vial", f"diagonal <= {profile.vial_diameter_mm}, height <= {profile.vial_height_mm}", f"{radial:.2f} / {ext[2]:.2f}", "mm", ok,
                                 "The part fits in the vial.", f"The part does not fit in the {profile.vial_diameter_mm} mm vial of {label}.", "bounding-box diagonal vs vial diameter", enforce))
        elif profile.build_volume_mm:
            bx, by, bz = profile.build_volume_mm
            ok = ext[2] <= bz and ((ext[0] <= bx and ext[1] <= by) or (ext[0] <= by and ext[1] <= bx))
            checks.append(_check("print_fits_build_volume", f"{bx} x {by} x {bz}", " x ".join(f"{v:.1f}" for v in ext), "mm", ok,
                                 "The part fits the build volume.", f"The part exceeds the build volume of {label}.", "bounding box vs build volume (Z up, X/Y may swap)", enforce))
        tris = len(mesh.faces)
        metrics["triangles"] = tris
        checks.append(_check("print_file_size", "<= 5,000,000 triangles", float(tris), "triangles", tris <= 5_000_000, "Mesh size is fine for slicers.",
                             "Very large mesh; slicers may be slow. Use 3MF or a coarser final resolution.", "triangle count", enforce, soft=True))

    # --- walls ----------------------------------------------------------------
    wall = head.get("wall_min_mm")
    if wall is not None:
        metrics["wall_min_mm"] = wall
        checks.append(_check("print_min_wall", f">= {profile.min_wall_mm}", wall, "mm", wall >= profile.min_wall_mm,
                             "Walls/struts are above the printer's minimum feature size.",
                             f"The thinnest walls ({wall:.3f} mm) are below the minimum feature of {label} ({profile.min_wall_mm} mm); they may not form or may break.",
                             "10th-percentile measured wall thickness vs profile minimum", enforce))
        if profile.recommended_wall_mm and wall < profile.recommended_wall_mm and wall >= profile.min_wall_mm:
            extra = " (single extrusion lines)" if process in EXTRUSION else ""
            checks.append(_check("print_robust_wall", f">= {profile.recommended_wall_mm}", wall, "mm", False, "",
                                 f"Walls are printable but thinner than the recommended {profile.recommended_wall_mm} mm{extra}; expect fragile features.",
                                 "measured wall vs recommended wall", enforce, soft=True))

    # --- holes / throats --------------------------------------------------------
    throat = head.get("percolation_diameter_mm")
    pore_d10 = metrology.rve_value("pore_d10_mm") if metrology is not None else None
    opening = throat if throat is not None else pore_d10
    if opening is not None:
        metrics["smallest_opening_mm"] = opening
        checks.append(_check("print_min_opening", f">= {profile.min_hole_mm}", opening, "mm", opening >= profile.min_hole_mm,
                             "Pore openings are above the printer's minimum hole size.",
                             f"Pore openings ({opening:.3f} mm) are below the minimum hole of {label} ({profile.min_hole_mm} mm); pores may close or fuse.",
                             "percolation (throat) diameter, else 10th-percentile pore size, vs profile minimum hole", enforce))

    # --- trapped material and drainage -----------------------------------------
    closed = metrology.part.get("closed_pores") if metrology is not None else None
    if profile.traps_material and closed:
        frac = float(closed.get("closed_void_fraction", 0.0))
        metrics["closed_void_fraction"] = frac
        what = "powder" if process in ("sls", "lpbf") else "uncured resin"
        checks.append(_check("print_closed_pores", "none (<= 0.001)", frac, "fraction of void", frac <= 1e-3,
                             f"No closed pores to trap {what}.", f"{closed.get('count', 0)} closed pore(s) will trap {what}; add openings or remove the full skin.",
                             "void components without a path to the outside", enforce))
    curve = metrology.part.get("intrusion") if metrology is not None else None
    if profile.min_drain_throat_mm and curve and curve.get("diameters_mm"):
        d = np.asarray(curve["diameters_mm"])
        f = np.asarray(curve["intruded_fraction"])
        reached = float(np.interp(profile.min_drain_throat_mm, d, f, right=0.0)) if profile.min_drain_throat_mm > d[0] else float(f[0])
        metrics["drainable_void_fraction"] = reached
        what = "powder removal" if process in ("sls", "lpbf") else ("wash-out" if process == "volumetric" else "resin drainage")
        checks.append(_check("print_drainage", f">= 0.95 of the void via throats >= {profile.min_drain_throat_mm} mm", reached, "fraction of void", reached >= 0.95,
                             f"The pores are open enough for {what}.",
                             f"Only {reached:.0%} of the pore space is reachable through throats of {profile.min_drain_throat_mm} mm; {what} will be incomplete.",
                             "simulated intrusion from the open faces", enforce))

    # --- layers: islands and overhangs -------------------------------------------
    if process in LAYERED and process != "sls" and solid is not None and voxel_mm:
        isl = layer_islands(solid, voxel_mm, profile.layer_height_mm, profile.max_overhang_deg, min_area_mm2=(profile.xy_resolution_mm or 0.0) ** 2)
        metrics.update(isl)
        lowest = isl["lowest_island_z_mm"]
        where = f" (lowest at z = {lowest:.2f} mm)" if lowest is not None else ""
        checks.append(_check("print_islands", 0.0, float(isl["island_count"]), "islands", isl["island_count"] == 0,
                             "Every layer region rests on the layer below (self-supporting).",
                             f"{isl['island_count']} region(s) start in mid-air{where}; they need supports, which cannot be removed from inside a lattice.",
                             "layer-by-layer connected components with the overhang allowance", enforce))
    if profile.max_overhang_deg is not None and mesh is not None and process in LAYERED:
        frac = overhang_fraction(mesh, profile.max_overhang_deg, profile.layer_height_mm)
        metrics["overhang_area_fraction"] = frac
        checks.append(_check("print_overhang_area", "<= 0.15", frac, "fraction of surface", frac <= 0.15,
                             "Little surface is overhanging beyond the process limit.",
                             f"{frac:.0%} of the surface overhangs more than {profile.max_overhang_deg} deg from vertical; expect sagging or rough down-skins.",
                             "area of down-facing triangles steeper than the limit", enforce, soft=True))

    # --- volumetric stray dose -----------------------------------------------------
    if process == "volumetric" and profile.stray_dose_pore_mm and mesh is not None:
        small = pore_d10 if pore_d10 is not None else head.get("pore_d50_mm")
        thick = float(min(mesh.extents))
        if small is not None:
            risk = small < profile.stray_dose_pore_mm and thick > (profile.stray_dose_thickness_mm or 0.0)
            checks.append(_check("print_stray_dose", f"pores >= {profile.stray_dose_pore_mm} mm or part <= {profile.stray_dose_thickness_mm} mm", small, "mm", not risk,
                                 "No stray-dose closure risk expected.",
                                 f"Fine pores ({small:.2f} mm) inside a {thick:.1f} mm thick part may cure shut from scattered light dose.",
                                 "risk rule: small pores deep inside the part", enforce, soft=True))

    # --- extrusion specifics ---------------------------------------------------------
    if process in EXTRUSION and profile.line_width_mm and opening is not None:
        ok = opening >= 1.5 * profile.line_width_mm
        checks.append(_check("print_pore_vs_line", f">= 1.5 x line width ({1.5 * profile.line_width_mm:.2f})", opening, "mm", ok,
                             "Pores are wide compared with the extruded line.",
                             "Pores are close to the extrusion width; neighbouring lines may merge and close them.", "opening vs line width", enforce, soft=True))
    return report
