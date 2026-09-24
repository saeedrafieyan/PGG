from __future__ import annotations

from porous_designer.agentic.contracts import FieldReviewDecision
from porous_designer.agentic.orchestrator import AgenticRequestOrchestrator
from porous_designer.agentic.provider import MockAgentProvider, OpenRouterProvider
from porous_designer.agentic.request_parser_agent import RequestParserAgent
from porous_designer.domain.enums import DomainShape, StructureFamily
from porous_designer.gui.state_store import default_specification


def approve_all(orchestrator: AgenticRequestOrchestrator):
    parsed = orchestrator.last_result
    assert parsed is not None
    return [FieldReviewDecision(field_path=item.field_path, decision="accepted") for item in parsed.extracted_fields]


def test_federica_request_parse_result(tmp_path):
    orchestrator = AgenticRequestOrchestrator(audit_root=tmp_path)
    result = orchestrator.parse_request(
        "Generate an 8 x 14 x 8 mm scaffold with hexagonal packing, 1 mm pore size, 75-80% porosity, interconnected pores, and STL and STP files.",
        default_specification(),
    )
    paths = {item.field_path for item in result.extracted_fields}
    assert "domain.dimensions_mm" in paths
    assert "structure.family" in paths
    assert any(item.identifier == "ambiguous_hexagonal" for item in result.ambiguities)
    assert any(item.feature == "STEP export" for item in result.unsupported_requests)


def test_explicit_hcp_request_can_be_approved(tmp_path):
    orchestrator = AgenticRequestOrchestrator(audit_root=tmp_path)
    orchestrator.parse_request(
        "Create a 10 x 10 x 5 mm HCP spherical-pore scaffold with 1.2 mm generating sphere diameter and 72% target porosity.",
        default_specification(),
    )
    approved, _ = orchestrator.approve(default_specification(), approve_all(orchestrator))
    assert approved.structure.family == StructureFamily.HCP_SPHERICAL_PORES
    assert approved.structure.pore_diameter_mm == 1.2


def test_gyroid_request(tmp_path):
    orchestrator = AgenticRequestOrchestrator(audit_root=tmp_path)
    orchestrator.parse_request("Generate a 12 x 12 x 6 mm gyroid scaffold with a 2 mm unit-cell size and 70% porosity.", default_specification())
    approved, _ = orchestrator.approve(default_specification(), approve_all(orchestrator))
    assert approved.structure.family == StructureFamily.GYROID
    assert approved.structure.unit_cell_size_mm == 2.0


def test_cylinder_diamond_request(tmp_path):
    orchestrator = AgenticRequestOrchestrator(audit_root=tmp_path)
    orchestrator.parse_request("Create a cylindrical diamond TPMS scaffold, 8 mm diameter and 12 mm high, with 65% porosity.", default_specification())
    approved, _ = orchestrator.approve(default_specification(), approve_all(orchestrator))
    assert approved.domain.shape == DomainShape.CYLINDER
    assert approved.domain.dimensions_mm == [8.0, 12.0]
    assert approved.structure.family == StructureFamily.DIAMOND


def test_ambiguous_hexagonal_and_pore_size_requests(tmp_path):
    orchestrator = AgenticRequestOrchestrator(audit_root=tmp_path)
    result = orchestrator.parse_request("Create a 4 x 4 x 4 mm scaffold with hexagonal packing and 1 mm pore size.", default_specification())
    ids = {item.identifier for item in result.ambiguities}
    assert {"ambiguous_hexagonal", "ambiguous_pore_size"} <= ids


def test_unsupported_step_request(tmp_path):
    orchestrator = AgenticRequestOrchestrator(audit_root=tmp_path)
    result = orchestrator.parse_request("Create a 4 x 4 x 4 mm HCP scaffold with STEP-only output.", default_specification())
    assert any(item.feature == "STEP export" for item in result.unsupported_requests)
    assert all("step" not in item.value for item in result.extracted_fields if item.field_path == "export.formats")


def test_infeasible_request_still_parses_for_later_deterministic_estimate(tmp_path):
    orchestrator = AgenticRequestOrchestrator(audit_root=tmp_path)
    result = orchestrator.parse_request("Create a 1000 x 1000 x 1000 mm gyroid scaffold with 0.01 mm resolution and 70% porosity.", default_specification())
    assert result.extracted_fields


def test_external_provider_disabled_invalid_json_timeout_and_fallback():
    from porous_designer.agentic.contracts import ProviderMode
    from porous_designer.agentic.provider_config import ExternalCallMode, ProviderSettings

    assert RequestParserAgent(OpenRouterProvider()).parse("Generate a 4 x 4 x 4 mm gyroid.").provider_mode == "deterministic"
    settings = ProviderSettings(external_access_enabled=True, provider_mode=ProviderMode.OPENROUTER, external_call_mode=ExternalCallMode.WHEN_RECOMMENDED)
    assert RequestParserAgent(MockAgentProvider(invalid_json=True), settings=settings).parse("Generate a 4 x 4 x 4 mm scaffold with hexagonal packing and pore size 1 mm.").provider_failed
    assert RequestParserAgent(MockAgentProvider(timeout=True), settings=settings).parse("Generate a 4 x 4 x 4 mm scaffold with hexagonal packing and pore size 1 mm.").provider_failed
