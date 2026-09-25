"""Phase 4.3 design agent: planner provenance, feasibility, repair rules, checkpoints.

The property tables are replaced by a small synthetic table and generation by
a fake that writes a validation report, so the agent logic is tested in
isolation (the real kernel is covered by the integration tests).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import porous_designer.knowledge.feasibility as feas
import porous_designer.knowledge.property_tables as pt
from porous_designer.agentic.design_agent import DesignAgent


def _rows(scale_wall=1.0):
    rows = []
    for i in range(12):
        phi = round(0.35 + 0.05 * i, 2)
        rows.append(
            {
                "porosity": phi,
                "wall_d10_per_cell": 0.5 * (1 - phi) * scale_wall,
                "wall_d50_per_cell": 0.6 * (1 - phi) * scale_wall,
                "pore_d10_per_cell": 0.30 * phi,
                "pore_d50_per_cell": 0.45 * phi,
                "throat_per_cell": 0.35 * phi,
                "surface_per_cell_inv": 3.0,
                "permeability_per_cell2": 0.01 * phi**3,
                "youngs_relative": (1 - phi) ** 2,
                "control": 0.0,
            }
        )
    return rows


TABLES = {"families": {"gyroid:sheet": _rows(), "diamond:sheet": _rows(1.2), "strut_cubic": _rows(0.8)}}


@pytest.fixture(autouse=True)
def synthetic_tables(monkeypatch):
    monkeypatch.setattr(pt, "load_tables", lambda: TABLES)
    monkeypatch.setattr(feas, "load_tables", lambda: TABLES)


@dataclass
class FakeTuning:
    reachable: bool = True


@dataclass
class FakeResult:
    run_dir: Path
    success: bool
    measurements: dict
    messages: list = field(default_factory=list)
    tuning: FakeTuning = field(default_factory=FakeTuning)
    stl_path: Path | None = None
    threemf_path: Path | None = None
    step_path: Path | None = None
    final_mesh_porosity: float = 0.7


class FakeGenerator:
    """Walls pass once the cell reaches ``good_cell_mm``."""

    def __init__(self, tmp_path: Path, good_cell_mm: float = 0.0, min_wall: float = 0.3):
        self.tmp_path, self.good_cell, self.min_wall = tmp_path, good_cell_mm, min_wall
        self.specs = []

    def __call__(self, spec):
        self.specs.append(spec)
        run = self.tmp_path / f"run{len(self.specs)}"
        run.mkdir()
        cell = spec.structure.unit_cell_size_mm or 1.0
        wall = 0.5 * (1 - spec.targets.porosity_target.target) * cell
        ok = cell >= self.good_cell
        checks = [
            {"name": "porosity", "status": "pass", "achieved_value": 0.7, "requested_value": 0.7},
            {"name": "print_min_wall", "status": "pass" if ok else "warning", "achieved_value": round(wall if ok else wall * 0.8, 4), "requested_value": f">= {self.min_wall}"},
        ]
        (run / "validation_report.json").write_text(json.dumps({"checks": checks}), encoding="utf-8")
        return FakeResult(run, True, {"pore_d50_mm": 0.45 * 0.7 * cell, "wall_d50_mm": wall})


def agent(tmp_path, gen=None, **kw):
    return DesignAgent(output_dir=tmp_path / "out", generate=gen or FakeGenerator(tmp_path), auto_approve=True, **kw)


def test_planner_records_provenance_and_knowledge(tmp_path):
    a = agent(tmp_path)
    intent = a.plan("bone scaffold, gyroid, 10 x 10 x 6 mm box, printed on a resin printer", [])
    assert intent.values["family"].source == "user"
    assert intent.values["process"].value == "sla"
    assert intent.application == "bone"
    por = intent.values["porosity"]
    assert por.source == "knowledge_base" and por.citations
    assert intent.values["pore_mm"].source == "knowledge_base"


def test_user_values_are_never_replaced_by_knowledge(tmp_path):
    intent = agent(tmp_path).plan("bone scaffold gyroid 10 x 10 x 6 mm box with 60% porosity", [])
    assert intent.values["porosity"].value == pytest.approx(0.6)
    assert intent.values["porosity"].source == "user"


def test_designer_meets_printer_limits(tmp_path):
    gen = FakeGenerator(tmp_path)
    res = agent(tmp_path, gen, process="sla").run("gyroid scaffold 10 x 10 x 6 mm box with 70% porosity")
    assert res.status == "delivered"
    spec = gen.specs[0]
    wall = 0.5 * 0.3 * spec.structure.unit_cell_size_mm
    assert wall >= 0.3  # generic_msla minimum wall
    assert res.intent.values["cell_mm"].source == "designer"
    assert res.trace_path.exists()
    trace = json.loads(res.trace_path.read_text(encoding="utf-8"))
    roles = [s["role"] for s in trace["trace"]]
    assert roles[:2] == ["planner", "designer"] and "verifier" in roles


def test_infeasible_request_gives_numbers_and_alternatives(tmp_path):
    gen = FakeGenerator(tmp_path)
    res = agent(tmp_path, gen).run("gyroid scaffold 30 x 30 x 30 mm box with 90% porosity and 1 mm pore size, FDM printer")
    assert res.status == "infeasible"
    assert not gen.specs  # nothing generated
    assert "walls" in res.explanation and "mm" in res.explanation
    assert res.alternatives


def test_literature_pore_size_relaxed_with_disclosure(tmp_path):
    # Skin: literature pores 0.08 mm are not printable on FDM -> smallest printable pore, flagged.
    res = agent(tmp_path).run("dermal wound scaffold 20 x 20 x 20 mm box on a resin printer")
    pore = res.intent.values["pore_mm"]
    assert pore.source == "designer" and pore.requires_confirmation
    assert "literature" in pore.detail
    assert res.status.startswith("delivered")


def test_repairer_enlarges_designer_cell(tmp_path):
    gen = FakeGenerator(tmp_path, good_cell_mm=100.0)  # first run warns
    a = agent(tmp_path, gen, process="sla")
    a.max_iterations = 2
    first = {}

    def gen2(spec):
        r = gen(spec)
        first.setdefault("cell", spec.structure.unit_cell_size_mm)
        gen.good_cell = first["cell"] * 1.01
        return r

    a._generate = gen2
    res = a.run("gyroid scaffold 10 x 10 x 6 mm box with 70% porosity")
    assert len(gen.specs) == 2
    assert gen.specs[1].structure.unit_cell_size_mm > gen.specs[0].structure.unit_cell_size_mm
    assert res.iterations[0]["repairs"][0]["rule"] == "scale_length"
    assert res.status == "delivered"


def test_repairer_does_not_change_user_cell(tmp_path):
    gen = FakeGenerator(tmp_path, good_cell_mm=100.0)
    res = agent(tmp_path, gen, process="sla").run("gyroid scaffold 10 x 10 x 6 mm box with 70% porosity and 2.2 mm unit cell")
    assert all(s.structure.unit_cell_size_mm == 2.2 for s in gen.specs)
    assert res.status in ("needs_user", "delivered_with_warnings", "failed")
    joined = json.dumps(res.iterations)
    assert "2.2" in joined


def test_intent_checkpoint_rejection_generates_nothing(tmp_path):
    gen = FakeGenerator(tmp_path)
    a = DesignAgent(output_dir=tmp_path / "out", generate=gen, approve_intent=lambda *a: False)
    res = a.run("gyroid scaffold 10 x 10 x 6 mm box with 70% porosity")
    assert res.status == "rejected" and not gen.specs


def test_stiffness_target_sets_porosity(tmp_path):
    gen = FakeGenerator(tmp_path)
    res = agent(tmp_path, gen).run("gyroid scaffold 10 x 10 x 6 mm box with a relative stiffness of 0.09")
    assert res.intent.values["youngs_relative"].value == pytest.approx(0.09)
    assert gen.specs[0].targets.porosity_target.target == pytest.approx(0.7, abs=0.01)
    assert gen.specs[0].generation.metrology == "full"
