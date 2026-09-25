"""Phase 4.3 design agent end to end with the real kernel and property tables."""

from __future__ import annotations

import json

import pytest

from porous_designer.agentic.design_agent import DesignAgent
from porous_designer.knowledge.property_tables import DATA_FILE, properties_at
from porous_designer.domain.enums import StructureFamily, TPMSVariant

pytestmark = pytest.mark.skipif(not DATA_FILE.exists(), reason="property tables not built (porous-designer build-property-tables)")


def test_property_tables_are_consistent():
    p70 = properties_at(StructureFamily.GYROID, TPMSVariant.SHEET, 0.7)
    p80 = properties_at(StructureFamily.GYROID, TPMSVariant.SHEET, 0.8)
    assert p70 and p80
    assert p80.wall_d10_per_cell < p70.wall_d10_per_cell  # thinner walls at higher porosity
    assert p80.pore_d50_per_cell > p70.pore_d50_per_cell
    if "youngs_relative" in p70.values:
        assert p80.youngs_relative < p70.youngs_relative


def test_agent_designs_generates_and_verifies(tmp_path):
    agent = DesignAgent(output_dir=tmp_path, auto_approve=True, max_iterations=2, voxel_budget=3_000_000)
    res = agent.run("gyroid scaffold 12 x 12 x 10 mm box with 70% porosity, printed on a resin printer")
    assert res.status in ("delivered", "delivered_with_warnings"), res.explanation
    spec = res.specification
    assert spec.manufacturing.printer_profile == "generic_msla"
    pred = res.design_info["design_point"]
    m = res.generation.measurements
    # the table prediction and the measurement of the generated part agree to within a voxel or so
    h = spec.generation.final_resolution_mm
    assert abs(m["wall_min_mm"] - pred["wall_mm"]) <= max(0.35 * pred["wall_mm"], 1.5 * h)
    assert abs(res.generation.final_mesh_porosity - 0.7) < 0.03
    trace = json.loads(res.trace_path.read_text(encoding="utf-8"))
    assert [s["role"] for s in trace["trace"]][:2] == ["planner", "designer"]


def test_agent_refuses_infeasible_before_generating(tmp_path):
    calls = []
    agent = DesignAgent(output_dir=tmp_path, auto_approve=True, generate=lambda spec: calls.append(spec))
    res = agent.run("gyroid scaffold 10 x 10 x 10 mm box with 85% porosity and 0.15 mm pore size on an FDM printer")
    assert res.status == "infeasible" and not calls
    assert "mm" in res.explanation
