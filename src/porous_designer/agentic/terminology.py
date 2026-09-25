"""Controlled terminology and aliases (Phase 4.1 vocabulary)."""

from __future__ import annotations

from dataclasses import dataclass
import re

from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily, TPMSVariant


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
    "schwarz p": StructureFamily.PRIMITIVE,
    "schwarz primitive": StructureFamily.PRIMITIVE,
    "schwarz d": StructureFamily.DIAMOND,
    "schwarz diamond": StructureFamily.DIAMOND,
    "schwarz-d": StructureFamily.DIAMOND,
    "schwarz-p": StructureFamily.PRIMITIVE,
    "schwartz p": StructureFamily.PRIMITIVE,
    "schwartz d": StructureFamily.DIAMOND,
    "iwp": StructureFamily.IWP,
    "i-wp": StructureFamily.IWP,
    "i wp": StructureFamily.IWP,
    "schoen iwp": StructureFamily.IWP,
    "schoen i-wp": StructureFamily.IWP,
    "neovius": StructureFamily.NEOVIUS,
    "fischer-koch": StructureFamily.FISCHER_KOCH_S,
    "fischer koch": StructureFamily.FISCHER_KOCH_S,
    "fischer-koch s": StructureFamily.FISCHER_KOCH_S,
    "fischer koch s": StructureFamily.FISCHER_KOCH_S,
    "lidinoid": StructureFamily.LIDINOID,
    # Strut (beam) lattices. "bcc"/"simple cubic" alone stay the sphere-pore
    # families; the longer strut phrases win by longest-match.
    "cubic strut": StructureFamily.STRUT_CUBIC,
    "cubic struts": StructureFamily.STRUT_CUBIC,
    "cubic truss": StructureFamily.STRUT_CUBIC,
    "simple cubic strut": StructureFamily.STRUT_CUBIC,
    "simple cubic struts": StructureFamily.STRUT_CUBIC,
    "grid lattice": StructureFamily.STRUT_CUBIC,
    "bcc strut": StructureFamily.STRUT_BCC,
    "bcc struts": StructureFamily.STRUT_BCC,
    "bcc truss": StructureFamily.STRUT_BCC,
    "bcc beam": StructureFamily.STRUT_BCC,
    "body-centred cubic strut": StructureFamily.STRUT_BCC,
    "body-centered cubic strut": StructureFamily.STRUT_BCC,
    "bcc lattice": StructureFamily.STRUT_BCC,
    "bcc strut lattice": StructureFamily.STRUT_BCC,
    "body-centred cubic lattice": StructureFamily.STRUT_BCC,
    "body-centered cubic lattice": StructureFamily.STRUT_BCC,
    "body centred cubic lattice": StructureFamily.STRUT_BCC,
    "body centered cubic lattice": StructureFamily.STRUT_BCC,
    "simple cubic lattice": StructureFamily.STRUT_CUBIC,
    "cubic lattice": StructureFamily.STRUT_CUBIC,
    "octet": StructureFamily.STRUT_OCTET,
    "octet truss": StructureFamily.STRUT_OCTET,
    "octet-truss": StructureFamily.STRUT_OCTET,
    "octet lattice": StructureFamily.STRUT_OCTET,
    "kelvin": StructureFamily.STRUT_KELVIN,
    "kelvin cell": StructureFamily.STRUT_KELVIN,
    "kelvin foam": StructureFamily.STRUT_KELVIN,
    "tetrakaidecahedron": StructureFamily.STRUT_KELVIN,
    "tetrakaidecahedral": StructureFamily.STRUT_KELVIN,
    "truncated octahedron": StructureFamily.STRUT_KELVIN,
    "voronoi": StructureFamily.VORONOI_FOAM,
    "voronoi foam": StructureFamily.VORONOI_FOAM,
    "voronoi lattice": StructureFamily.VORONOI_FOAM,
    "stochastic foam": StructureFamily.VORONOI_FOAM,
    "stochastic lattice": StructureFamily.VORONOI_FOAM,
    "random foam": StructureFamily.VORONOI_FOAM,
    "trabecular": StructureFamily.VORONOI_FOAM,
}

# Sheet vs network (skeletal) TPMS. Only meaningful for TPMS families.
TPMS_VARIANT_ALIASES: dict[str, TPMSVariant] = {
    "sheet": TPMSVariant.SHEET,
    "sheet-based": TPMSVariant.SHEET,
    "sheet based": TPMSVariant.SHEET,
    "sheet tpms": TPMSVariant.SHEET,
    "network": TPMSVariant.NETWORK,
    "network-based": TPMSVariant.NETWORK,
    "network based": TPMSVariant.NETWORK,
    "skeletal": TPMSVariant.NETWORK,
    "solid network": TPMSVariant.NETWORK,
    "strut-based tpms": TPMSVariant.NETWORK,
}

DOMAIN_ALIASES: dict[str, DomainShape] = {
    "box": DomainShape.BOX,
    "cuboid": DomainShape.BOX,
    "rectangular prism": DomainShape.BOX,
    "cylinder": DomainShape.CYLINDER,
    "cylindrical": DomainShape.CYLINDER,
    "disc": DomainShape.CYLINDER,
    "disk": DomainShape.CYLINDER,
    "sphere": DomainShape.SPHERE,
    "spherical": DomainShape.SPHERE,
    "ball": DomainShape.SPHERE,
    "bead": DomainShape.SPHERE,
}

EXPORT_ALIASES: dict[str, ExportFormat] = {
    "stl": ExportFormat.STL,
    "step": ExportFormat.STEP,
    "stp": ExportFormat.STEP,
    "3mf": ExportFormat.THREE_MF,
}

# Canonical manufacturing-process codes. Values are plain strings because
# ManufacturingSpec.process is free text; these are the only codes the agent
# layer proposes.
PROCESS_ALIASES: dict[str, str] = {
    "fdm": "fdm",
    "fff": "fdm",
    "fused deposition": "fdm",
    "fused deposition modeling": "fdm",
    "fused deposition modelling": "fdm",
    "fused filament": "fdm",
    "fused filament fabrication": "fdm",
    "sla": "sla",
    "stereolithography": "sla",
    "msla": "sla",
    "dlp": "dlp",
    "digital light processing": "dlp",
    "volumetric": "volumetric",
    "volumetric printing": "volumetric",
    "volumetric printer": "volumetric",
    "volumetric additive manufacturing": "volumetric",
    "tomographic": "volumetric",
    "tomographic printing": "volumetric",
    "xolography": "volumetric",
    "sls": "sls",
    "selective laser sintering": "sls",
    "lpbf": "lpbf",
    "l-pbf": "lpbf",
    "slm": "lpbf",
    "dmls": "lpbf",
    "laser powder bed fusion": "lpbf",
    "powder bed fusion": "lpbf",
    "bioprinting": "bioprinting",
    "bioprinter": "bioprinting",
    "bioprinted": "bioprinting",
    "two-photon": "two_photon",
    "two photon": "two_photon",
    "2pp": "two_photon",
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
        "Spatial period of TPMS, strut-lattice structures and mean seed spacing of Voronoi foams.",
        ("unit cell", "unit-cell", "cell size"),
    ),
    "step": Term(
        "STEP exchange format",
        "STEP and STP refer to the same STEP exchange format family; AGE writes a faceted STEP solid.",
        ("step", "stp"),
    ),
}


# "0,5 mm" -> "0.5 mm" (decimal comma), but "4,4,4" and "1, 2" are left as
# separators. Must run before commas are turned into spaces.
_DECIMAL_COMMA = re.compile(r"(?<![\d,])(\d+),(\d+)(?![\d,])")


def normalize_text(text: str) -> str:
    return (
        _DECIMAL_COMMA.sub(r"\1.\2", text.lower())
        .replace("×", " x ")
        .replace("–", "-")
        .replace("—", "-")
        .replace("‑", "-")
        .replace(",", " ")
    )


# Phrases where "sphere" describes the pores, not the part.
_PORE_SPHERE_PHRASES = re.compile(
    r"(?:spherical|sphere)[\s_-]*(?:pores?|voids?|cavit(?:y|ies)|holes?)|(?:generating\s+)?sphere\s+(?:diameter|size|radius)|pore\s+spheres?"
)


def mask_pore_phrases(text: str) -> str:
    """Blank out pore descriptions so domain-shape matching ignores them."""
    return _PORE_SPHERE_PHRASES.sub(lambda m: " " * len(m.group(0)), normalize_text(text))


def tpms_variant_near(text: str, family_phrase: str) -> tuple[str, TPMSVariant] | None:
    """Sheet/network word next to the TPMS name ("network gyroid", "gyroid
    sheet", "sheet-based TPMS"). A distant "network" usually means the pore
    network, so only a neighbouring word (one filler word allowed) counts."""
    normalized = normalize_text(text)
    names = rf"(?:{re.escape(family_phrase)}|tpms)"
    for alias in sorted(TPMS_VARIANT_ALIASES, key=len, reverse=True):
        a = re.escape(alias)
        pattern = rf"(?<![a-z0-9])(?:{a}[\s-]+(?:[a-z]+[\s-]+)?{names}|{names}[\s-]+(?:[a-z]+[\s-]+)?{a})(?![a-z0-9])"
        match = re.search(pattern, normalized)
        if match and "pore network" not in match.group(0):
            return match.group(0), TPMS_VARIANT_ALIASES[alias]
    return None


def match_alias(text: str, aliases: dict[str, object]) -> tuple[str, object] | None:
    normalized = normalize_text(text)
    for alias in sorted(aliases, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        if re.search(pattern, normalized):
            return alias, aliases[alias]
    return None
