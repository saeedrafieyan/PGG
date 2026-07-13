"""Controlled terminology and aliases for Phase 3B.1."""

from __future__ import annotations

from dataclasses import dataclass
import re

from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily


@dataclass(frozen=True)
class Term:
    canonical: str
    definition: str
    aliases: tuple[str, ...]


STRUCTURE_ALIASES: dict[str, StructureFamily] = {
    "sc": StructureFamily.SC_SPHERICAL_PORES,
    "simple cubic": StructureFamily.SC_SPHERICAL_PORES,
    "bcc": StructureFamily.BCC_SPHERICAL_PORES,
    "body-centered cubic": StructureFamily.BCC_SPHERICAL_PORES,
    "body centred cubic": StructureFamily.BCC_SPHERICAL_PORES,
    "body centered cubic": StructureFamily.BCC_SPHERICAL_PORES,
    "body centred": StructureFamily.BCC_SPHERICAL_PORES,
    "fcc": StructureFamily.FCC_SPHERICAL_PORES,
    "face-centered cubic": StructureFamily.FCC_SPHERICAL_PORES,
    "face centred cubic": StructureFamily.FCC_SPHERICAL_PORES,
    "face centered cubic": StructureFamily.FCC_SPHERICAL_PORES,
    "hcp": StructureFamily.HCP_SPHERICAL_PORES,
    "hexagonal close-packed": StructureFamily.HCP_SPHERICAL_PORES,
    "hexagonal close packed": StructureFamily.HCP_SPHERICAL_PORES,
    "gyroid": StructureFamily.GYROID,
    "diamond": StructureFamily.DIAMOND,
    "diamond tpms": StructureFamily.DIAMOND,
    "primitive": StructureFamily.PRIMITIVE,
    "primitive tpms": StructureFamily.PRIMITIVE,
}

DOMAIN_ALIASES: dict[str, DomainShape] = {
    "box": DomainShape.BOX,
    "cuboid": DomainShape.BOX,
    "rectangular prism": DomainShape.BOX,
    "cylinder": DomainShape.CYLINDER,
    "cylindrical": DomainShape.CYLINDER,
}

EXPORT_ALIASES: dict[str, ExportFormat] = {
    "stl": ExportFormat.STL,
    "step": ExportFormat.STEP,
    "stp": ExportFormat.STEP,
}

TERMINOLOGY: dict[str, Term] = {
    "generating_sphere_diameter": Term(
        "generating sphere diameter",
        "Input sphere diameter used by sphere-pore generators before clipping.",
        ("pore diameter", "sphere diameter", "generating sphere diameter"),
    ),
    "equivalent_pore_diameter": Term(
        "equivalent pore diameter",
        "Measured pore diameter inferred from generated geometry; not identical to the input sphere diameter.",
        ("equivalent pore diameter", "measured pore diameter"),
    ),
    "throat_diameter": Term(
        "throat diameter",
        "Measured opening between pores; not the same as generating sphere diameter.",
        ("throat", "throat size", "throat diameter", "pore opening"),
    ),
    "unit_cell_size": Term(
        "unit-cell size",
        "Spatial period for TPMS structures.",
        ("unit cell", "unit-cell", "cell size"),
    ),
    "step": Term(
        "STEP exchange format",
        "STEP and STP refer to the same STEP exchange format family.",
        ("step", "stp"),
    ),
}


def normalize_text(text: str) -> str:
    return (
        text.lower()
        .replace("×", " x ")
        .replace("–", "-")
        .replace("—", "-")
        .replace("‑", "-")
        .replace(",", " ")
    )


def match_alias(text: str, aliases: dict[str, object]) -> tuple[str, object] | None:
    normalized = normalize_text(text)
    for alias in sorted(aliases, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        if re.search(pattern, normalized):
            return alias, aliases[alias]
    return None
