"""Phase 4.1: agent-layer vocabulary for the new families, domains and formats."""

from __future__ import annotations

import pytest

from porous_designer.agentic.deterministic_parser import DeterministicRequestParser
from porous_designer.agentic.grounding import (
    EXPORTABLE_FORMATS,
    TEXT_DOMAIN_SHAPES,
    GroundedExtraction,
    grounded_extraction_schema,
    verify_grounded_extraction,
)
from porous_designer.agentic.terminology import mask_pore_phrases, tpms_variant_near


def parse(text: str) -> dict:
    return {f.field_path: f.value for f in DeterministicRequestParser().parse(text).extracted_fields}


def verify(request: str, **fields):
    return verify_grounded_extraction(request, GroundedExtraction.model_validate(fields))


def accepted(report) -> dict:
    return {f.field_path: f for f in report.fields}


@pytest.mark.parametrize(
    "phrase,family",
    [
        ("I-WP", "iwp"),
        ("Schoen IWP", "iwp"),
        ("Neovius", "neovius"),
        ("Fischer-Koch S", "fischer_koch_s"),
        ("lidinoid", "lidinoid"),
        ("octet truss", "strut_octet"),
        ("Kelvin cell", "strut_kelvin"),
        ("tetrakaidecahedron", "strut_kelvin"),
        ("BCC struts", "strut_bcc"),
        ("simple cubic struts", "strut_cubic"),
        ("Voronoi foam", "voronoi_foam"),
        ("trabecular", "voronoi_foam"),
        ("BCC", "bcc_spherical_pores"),
        ("simple cubic", "sc_spherical_pores"),
    ],
)
def test_family_aliases(phrase, family):
    assert parse(f"a 10 x 10 x 5 mm {phrase} scaffold")["structure.family"] == family


def test_network_and_sheet_variants_need_to_be_adjacent():
    assert parse("10x10x10 mm network gyroid, 2 mm unit cell")["structure.tpms_variant"] == "network"
    assert parse("10x10x10 mm sheet-based diamond TPMS")["structure.tpms_variant"] == "sheet"
    # "pore network" describes connectivity, not the TPMS variant.
    assert "structure.tpms_variant" not in parse("20x20x20 mm gyroid with an interconnected pore network")
    assert tpms_variant_near("a skeletal gyroid", "gyroid")[1].value == "network"
    assert tpms_variant_near("gyroid pore network", "gyroid") is None


def test_sphere_domain_and_pore_phrase_masking():
    fields = parse("A 12 mm sphere filled with octet truss, 3 mm unit cell")
    assert fields["domain.shape"] == "sphere" and fields["domain.dimensions_mm"] == [12.0]
    fields = parse("gyroid ball 20 mm in diameter")
    assert fields["domain.shape"] == "sphere" and fields["domain.dimensions_mm"] == [20.0]
    fields = parse("bcc spherical pores 10x10x10 mm, 1 mm pore diameter")
    assert fields["domain.shape"] == "box"
    fields = parse("fcc with 1.2 mm sphere diameter 10x10x10 mm")
    assert fields["domain.shape"] == "box" and fields["structure.pore_diameter_mm"] == 1.2
    assert "sphere" not in mask_pore_phrases("hcp spherical pores and generating sphere diameter")


def test_all_export_formats_are_extracted():
    assert parse("4x4x4 mm gyroid, export STL, 3MF and STP")["export.formats"] == ["3mf", "step", "stl"]


def test_schema_offers_new_vocabulary_but_not_mesh_domains():
    schema = grounded_extraction_schema()
    props = schema["properties"]
    families = props["structure_family"]["properties"]["value"]["enum"]
    assert {"iwp", "strut_octet", "voronoi_foam"} <= set(families)
    shapes = props["domain_shape"]["properties"]["value"]["enum"]
    assert "mesh" not in shapes and "sphere" in shapes
    assert props["export_formats"]["properties"]["values"]["items"]["enum"] == list(EXPORTABLE_FORMATS)
    assert set(TEXT_DOMAIN_SHAPES) == {"box", "cylinder", "sphere"}
    assert "sphere_diameter" in props and "tpms_variant" in props


def test_grounded_sphere_domain():
    report = verify("a 15 mm sphere", sphere_diameter={"value": 15, "unit": "mm", "quote": "15 mm sphere"})
    fields = accepted(report)
    assert fields["domain.shape"].value == "sphere"
    assert fields["domain.dimensions_mm"].value == [15.0]


def test_grounded_domain_rejects_spherical_pores_as_shape():
    report = verify("bcc spherical pores", domain_shape={"value": "sphere", "quote": "spherical pores"})
    fields = accepted(report)
    # Nothing in the masked quote names a shape: kept only as an interpreted value that needs confirmation.
    assert "domain.shape" not in fields or fields["domain.shape"].requires_confirmation


def test_grounded_mesh_domain_is_not_allowed_from_text():
    report = verify("fill the wound scan", domain_shape={"value": "mesh", "quote": "wound scan"})
    assert "domain.shape" not in accepted(report)
    assert report.rejected and report.rejected[0].field_path == "domain.shape"


def test_grounded_tpms_variant():
    report = verify(
        "a network gyroid",
        structure_family={"value": "gyroid", "quote": "network gyroid"},
        tpms_variant={"value": "network", "quote": "network gyroid"},
    )
    fields = accepted(report)
    assert fields["structure.tpms_variant"].value == "network" and not fields["structure.tpms_variant"].requires_confirmation
    wrong = verify(
        "a sheet gyroid",
        structure_family={"value": "gyroid", "quote": "sheet gyroid"},
        tpms_variant={"value": "network", "quote": "sheet gyroid"},
    )
    assert "structure.tpms_variant" not in accepted(wrong)
    loose = verify(
        "gyroid with a pore network",
        structure_family={"value": "gyroid", "quote": "gyroid"},
        tpms_variant={"value": "network", "quote": "pore network"},
    )
    assert accepted(loose)["structure.tpms_variant"].requires_confirmation
    # A variant for a non-TPMS family is ignored.
    struts = verify(
        "octet truss network",
        structure_family={"value": "strut_octet", "quote": "octet truss"},
        tpms_variant={"value": "network", "quote": "truss network"},
    )
    assert "structure.tpms_variant" not in accepted(struts)


def test_grounded_new_families_verify_against_quote():
    report = verify("Kelvin cell lattice", structure_family={"value": "strut_kelvin", "quote": "Kelvin cell"})
    assert accepted(report)["structure.family"].value == "strut_kelvin"
    report = verify("Kelvin cell lattice", structure_family={"value": "strut_octet", "quote": "Kelvin cell"})
    assert "structure.family" not in accepted(report)
