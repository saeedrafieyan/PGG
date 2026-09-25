"""Printer / process profiles.

Built-in profiles (``printability/profiles/*.yaml``) hold generic starting
values for each process. User profiles live in ``<AGE data root>/printers``
(for example produced by ``porous-designer calibrate`` from a printed
calibration coupon) and take precedence over built-ins with the same id.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from porous_designer.paths import data_root

BUILTIN_DIR = Path(__file__).resolve().parent / "profiles"

# Default profile for each process code used by the agent layer.
PROCESS_DEFAULTS = {
    "fdm": "generic_fdm_0.4",
    "sla": "generic_msla",
    "dlp": "generic_dlp",
    "volumetric": "generic_volumetric_tomographic",
    "bioprinting": "generic_extrusion_bioprinting",
    "sls": "generic_sls",
    "lpbf": "generic_lpbf",
    "two_photon": None,
}


class PrinterProfile(BaseModel):
    id: str
    process: str
    display_name: str = ""
    source: str = ""
    layer_height_mm: float | None = None
    xy_resolution_mm: float | None = None
    nozzle_diameter_mm: float | None = None
    line_width_mm: float | None = None
    min_wall_mm: float = Field(gt=0)
    recommended_wall_mm: float | None = None
    min_hole_mm: float = Field(gt=0)
    min_gap_mm: float | None = None
    min_drain_throat_mm: float | None = None
    max_overhang_deg: float | None = None
    build_volume_mm: list[float] | None = None
    vial_diameter_mm: float | None = None
    vial_height_mm: float | None = None
    stray_dose_pore_mm: float | None = None
    stray_dose_thickness_mm: float | None = None
    traps_material: bool = False
    calibrated: bool = False
    calibration: dict = Field(default_factory=dict)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
        return path


def user_profile_dir() -> Path:
    return data_root() / "printers"


def _load_dir(directory: Path) -> dict[str, PrinterProfile]:
    out: dict[str, PrinterProfile] = {}
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.yaml")):
        try:
            profile = PrinterProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except Exception:
            continue  # a broken user file must not hide the others
        out[profile.id] = profile
    return out


def all_profiles() -> dict[str, PrinterProfile]:
    profiles = _load_dir(BUILTIN_DIR)
    profiles.update(_load_dir(user_profile_dir()))
    return profiles


def get_profile(profile_id: str) -> PrinterProfile:
    profiles = all_profiles()
    if profile_id not in profiles:
        raise KeyError(f"Unknown printer profile {profile_id!r}; known: {', '.join(sorted(profiles))}")
    return profiles[profile_id]


def profile_for(process: str | None, printer_profile: str | None) -> PrinterProfile | None:
    """Resolve the profile for a specification's manufacturing section.

    An explicit profile id wins; otherwise the generic profile of the
    process. The legacy default ``generic_fdm`` only counts when the process
    is FDM, so specifications without a process are not judged as FDM parts.
    """
    profiles = all_profiles()
    process = (process or "unknown").strip().lower()
    if printer_profile and printer_profile in profiles and not (printer_profile == "generic_fdm_0.4" and process not in ("fdm", "unknown")):
        return profiles[printer_profile]
    if printer_profile == "generic_fdm" and process == "fdm":
        return profiles.get("generic_fdm_0.4")
    default = PROCESS_DEFAULTS.get(process)
    return profiles.get(default) if default else None
