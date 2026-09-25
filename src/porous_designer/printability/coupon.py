"""Calibration coupon: measure a printer's real limits instead of guessing them.

The coupon has feature ladders around the profile's expected limits:

* walls  - thin fins of increasing thickness,
* pins   - posts of increasing diameter,
* holes  - tubes with increasing bore (vertical holes),
* gaps   - block pairs with increasing slot width,
* cubes  - gyroid cubes with three fixed wall thicknesses (weigh them to
  check porosity: porosity = 1 - mass / (density x volume)).

Every feature is an exact watertight primitive standing on (and slightly
overlapping) a base plate; slicers merge overlapping bodies. For vial-based
volumetric printers every row is a separate small coupon that fits the vial.

``calibrate_profile`` reads the filled-in measurement sheet: a limit is the
smallest nominal size that printed correctly *and above which everything also
printed*, so one lucky feature does not count.
"""

from __future__ import annotations

import csv
import datetime as _dt
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from porous_designer.printability.profiles import PrinterProfile, user_profile_dir

SHEET_COLUMNS = ["feature_id", "row", "type", "nominal_mm", "printed_ok", "measured_mm", "notes"]


def ladder(limit: float, *, low: float = 0.5, high: float = 3.0, count: int = 8, floor: float = 0.02) -> list[float]:
    values = np.geomspace(max(limit * low, floor), limit * high, count)
    step = 0.01 if limit < 1.0 else 0.05
    return sorted({round(round(float(v) / step) * step, 3) for v in values})


@dataclass
class Coupon:
    profile_id: str
    rows: dict[str, list[trimesh.Trimesh]] = field(default_factory=dict)
    sheet: list[dict] = field(default_factory=list)
    base_thickness_mm: float = 1.0

    def row_mesh(self, row: str) -> trimesh.Trimesh:
        return trimesh.util.concatenate(self.rows[row])

    def combined(self) -> trimesh.Trimesh:
        return trimesh.util.concatenate([m for parts in self.rows.values() for m in parts])


def _plate(x0: float, x1: float, y0: float, y1: float, t: float) -> trimesh.Trimesh:
    m = trimesh.creation.box(extents=[x1 - x0, y1 - y0, t])
    m.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, t / 2])
    return m


def _box(cx: float, cy: float, sx: float, sy: float, z0: float, z1: float) -> trimesh.Trimesh:
    m = trimesh.creation.box(extents=[sx, sy, z1 - z0])
    m.apply_translation([cx, cy, (z0 + z1) / 2])
    return m


def _gyroid_cube(size: float, cell: float, wall: float, voxel: float) -> trimesh.Trimesh:
    from porous_designer.domain.enums import DomainShape, StructureFamily
    from porous_designer.domain.specification import DesignSpecification, DomainSpec, GenerationSpec, PorosityTarget, StructureSpec, TargetsSpec
    from porous_designer.implicit.field import FieldModel
    from porous_designer.implicit.meshing import field_to_mesh

    spec = DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[size, size, size]),
        structure=StructureSpec(family=StructureFamily.GYROID, unit_cell_size_mm=cell, wall_thickness_mm=wall),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.5)),
        generation=GenerationSpec(compute_backend="cpu"),
    )
    model = FieldModel.build(spec, voxel)
    control = model.control_problem().fixed
    mesh = field_to_mesh(model.field(control), voxel, origin_mm=model.grid.origin_mm).mesh
    mesh.metadata["age_design_porosity"] = model.porosity(control)
    return mesh


def make_coupon(profile: PrinterProfile, *, height_mm: float = 4.0) -> Coupon:
    coupon = Coupon(profile_id=profile.id)
    base = coupon.base_thickness_mm
    overlap = 0.2
    z0, z1 = base - overlap, base + height_mm
    vial = profile.vial_diameter_mm is not None
    max_row_length = 0.8 * profile.vial_diameter_mm if vial else None

    def fit(make, pitch_of) -> list[float]:
        """Fewest-thinning ladder whose row still fits the vial (at least 4 sizes)."""
        values = make(8)
        if max_row_length is None:
            return values
        for count in range(8, 3, -1):
            values = make(count)
            if sum(pitch_of(v) for v in values) + 2.0 <= max_row_length:
                break
        return values

    specs = {
        "walls": lambda n: ladder(profile.min_wall_mm, count=n),
        "pins": lambda n: ladder(profile.min_wall_mm, low=0.75, high=4.0, count=n),
        "holes": lambda n: ladder(profile.min_hole_mm, count=n),
        "gaps": lambda n: ladder(profile.min_gap_mm or profile.min_hole_mm, count=n),
    }
    row_depth = 5.0
    y = 0.0
    fid = 0
    for row, make in specs.items():
        if row == "walls":
            pitch = lambda v: max(1.5, 3 * v)  # noqa: E731
        elif row == "pins":
            pitch = lambda v: max(1.5, 3 * v)  # noqa: E731
        elif row == "holes":
            wall = max(0.5 if vial else 1.0, 2 * profile.min_wall_mm)
            pitch = lambda v, wall=wall: v + 2 * wall + 1.0  # noqa: E731
        else:
            pitch = lambda v: v + (2.0 if vial else 3.0)  # noqa: E731
        values = fit(make, pitch)
        parts = []
        x = 1.0
        cy = y + row_depth / 2
        for v in values:
            p = pitch(v)
            cx = x + p / 2
            fid += 1
            if row == "walls":
                parts.append(_box(cx, cy, v, row_depth - 1.0, z0, z1))
            elif row == "pins":
                m = trimesh.creation.cylinder(radius=v / 2, height=z1 - z0, sections=max(32, int(v * 40)))
                m.apply_translation([cx, cy, (z0 + z1) / 2])
                parts.append(m)
            elif row == "holes":
                m = trimesh.creation.annulus(r_min=v / 2, r_max=v / 2 + wall, height=z1 - z0 - 1.0, sections=max(48, int(v * 60)))
                m.apply_translation([cx, cy, (z0 + z1 - 1.0) / 2])
                parts.append(m)
            else:
                block = 1.0 if vial else 1.5
                parts.append(_box(cx - v / 2 - block / 2, cy, block, row_depth - 1.0, z0, z1 - 1.0))
                parts.append(_box(cx + v / 2 + block / 2, cy, block, row_depth - 1.0, z0, z1 - 1.0))
            coupon.sheet.append({"feature_id": f"{row[0].upper()}{len([r for r in coupon.sheet if r['row'] == row]) + 1}", "row": row, "type": row[:-1], "nominal_mm": v, "printed_ok": "", "measured_mm": "", "notes": ""})
            x += p
        length = x + 1.0
        plate = _plate(0.0, length, y, y + row_depth, base)
        if row == "walls":
            # Orientation marker: a notch-free corner block marks feature 1.
            parts.append(_box(0.5, y + 0.5, 0.8, 0.8, z0, base + 1.5))
        coupon.rows[row] = [plate] + parts
        y += row_depth + (0.0 if vial else 1.0)
        if vial:
            y = 0.0  # every row is its own coupon

    # Gyroid cubes (not for tiny vials: they would not fit together with a plate).
    cube = 6.0 if not vial else min(6.0, 0.5 * profile.vial_diameter_mm)
    walls = [round(f * profile.min_wall_mm, 3) for f in (1.5, 2.0, 3.0)]
    cell = float(np.clip(8.0 * profile.min_wall_mm, 1.5, 4.0))
    voxel = max(0.02, min(walls) / 5.0)
    parts = []
    xs = 1.0
    for i, w in enumerate(walls):
        if vial and i > 0:
            break
        m = _gyroid_cube(cube, cell, w, voxel)
        m.apply_translation([xs, y + 0.5, base - overlap])
        parts.append(m)
        coupon.sheet.append({"feature_id": f"C{i + 1}", "row": "cubes", "type": "gyroid_cube", "nominal_mm": w, "printed_ok": "", "measured_mm": "",
                             "notes": f"design porosity {m.metadata['age_design_porosity']:.3f}; {cube} mm cube, cell {cell} mm; weigh for porosity"})
        xs += cube + 2.0
    coupon.rows["cubes"] = [_plate(0.0, xs - 1.0, y, y + cube + 1.0, base)] + parts
    return coupon


def write_coupon(coupon: Coupon, out_dir: str | Path, profile: PrinterProfile) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    if profile.vial_diameter_mm is None:
        path = out / f"coupon_{coupon.profile_id}.stl"
        coupon.combined().export(path)
        files["coupon"] = path
    for row in coupon.rows:
        path = out / f"coupon_{coupon.profile_id}_{row}.stl"
        coupon.row_mesh(row).export(path)
        files[row] = path
    sheet = out / f"coupon_{coupon.profile_id}_measurements.csv"
    with sheet.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        for row in coupon.sheet:
            writer.writerow(row)
    files["sheet"] = sheet
    readme = out / "README.txt"
    readme.write_text(
        f"AGE calibration coupon for {profile.display_name or profile.id}\n\n"
        "1. Print the coupon (rows are left to right from the corner marker: feature 1 is the smallest).\n"
        "2. For every feature fill in printed_ok = yes / no in the CSV:\n"
        "   walls/pins: complete, standing, not broken; holes: open all the way through;\n"
        "   gaps: slot open (not fused); cubes: printed without collapse.\n"
        "   Optionally enter measured_mm (calipers or microscope) and, for cubes, the porosity from\n"
        "   mass: porosity = 1 - mass / (material density x cube volume) in notes.\n"
        "3. Run:  porous-designer calibrate --profile "
        f"{profile.id} --measurements {sheet.name} --name <your_printer_name>\n",
        encoding="utf-8",
    )
    files["readme"] = readme
    return files


def _limit(rows: list[dict]) -> float | None:
    """Smallest nominal size that printed, with every larger size printed too."""
    ordered = sorted(rows, key=lambda r: float(r["nominal_mm"]))
    ok = [str(r.get("printed_ok", "")).strip().lower() in ("yes", "y", "1", "true", "ok") for r in ordered]
    if not any(ok):
        return None
    for i in range(len(ordered)):
        if all(ok[i:]):
            return float(ordered[i]["nominal_mm"])
    return None


def _bias(rows: list[dict]) -> float | None:
    diffs = []
    for r in rows:
        try:
            diffs.append(float(r["measured_mm"]) - float(r["nominal_mm"]))
        except (TypeError, ValueError, KeyError):
            continue
    return float(np.median(diffs)) if diffs else None


def calibrate_profile(base: PrinterProfile, sheet_path: str | Path, name: str, *, save: bool = True) -> PrinterProfile:
    with Path(sheet_path).open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    by_row: dict[str, list[dict]] = {}
    for r in rows:
        by_row.setdefault(r["row"], []).append(r)
    results = {row: {"limit_mm": _limit(items), "bias_mm": _bias(items), "tested": [float(i["nominal_mm"]) for i in items]} for row, items in by_row.items() if row != "cubes"}
    profile = base.model_copy(deep=True)
    profile.id = name
    profile.display_name = f"{name} (calibrated from {base.id})"
    profile.source = f"Calibration coupon {Path(sheet_path).name}, {_dt.date.today().isoformat()}"
    wall = results.get("walls", {}).get("limit_mm")
    pin = results.get("pins", {}).get("limit_mm")
    hole = results.get("holes", {}).get("limit_mm")
    gap = results.get("gaps", {}).get("limit_mm")
    if wall is not None or pin is not None:
        profile.min_wall_mm = max(v for v in (wall, pin) if v is not None)
        profile.recommended_wall_mm = round(1.5 * profile.min_wall_mm, 3)
    if hole is not None:
        profile.min_hole_mm = hole
        if profile.min_drain_throat_mm is not None:
            profile.min_drain_throat_mm = hole  # measured open bore is the drainage limit
    if gap is not None:
        profile.min_gap_mm = gap
    profile.calibrated = True
    profile.calibration = {"base_profile": base.id, "results": results, "cubes": by_row.get("cubes", [])}
    if save:
        profile.save(user_profile_dir() / f"{name}.yaml")
    return profile
