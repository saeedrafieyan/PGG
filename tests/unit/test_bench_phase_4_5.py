"""Phase 4.5 AGE-Bench: prompt set, scoring, code whitelist, runner (no network)."""

from __future__ import annotations

import json

import pytest

from porous_designer.bench import metrics, runner
from porous_designer.bench.prompts import TIER_SIZES, Case, build_prompts


def test_prompt_set_is_reproducible_and_tiered():
    a, b = build_prompts(2026), build_prompts(2026)
    assert [c.text for c in a] == [c.text for c in b]
    assert len(a) == sum(TIER_SIZES.values()) >= 300
    assert len({c.id for c in a}) == len(a)
    assert {c.tier for c in a} == set(range(1, 8))
    assert all(c.expect_feasible is False for c in a if c.tier == 5)
    assert all(c.out_of_scope for c in a if c.tier == 6)
    assert all(c.application is not None or "spongy" in c.text or "insert" in c.text for c in a if c.tier == 3)


def test_scoring_counts_correct_wrong_missing_and_invented():
    case = Case("x", 1, "t", expected={"porosity": 0.7, "domain_dimensions_mm": [10.0, 10.0, 5.0], "family": "gyroid"}, forbidden=["cell_mm"])
    s = runner.score_extraction(case, {"porosity": 0.7000001, "domain_dimensions_mm": [10, 10, 6], "cell_mm": 2.0})
    assert s["correct"] == ["porosity"]
    assert s["wrong"][0]["field"] == "domain_dimensions_mm"
    assert s["missing"] == ["family"]
    assert s["invented"] == ["cell_mm"] and s["forbidden_violations"] == ["cell_mm"]
    assert runner.same(["stl", "3mf"], ["3mf", "stl"])


def test_code_whitelist():
    ok = "import numpy as np\ndef field(x, y, z):\n    return np.sin(x) * np.cos(y) + np.sin(y) * np.cos(z) + np.sin(z) * np.cos(x)\n"
    assert runner.check_code(ok) is None
    assert "import" in runner.check_code("import os\ndef field(x,y,z):\n    return x")
    assert runner.check_code("def field(x,y,z):\n    return open('f').read()") is not None
    assert runner.check_code("def field(x,y,z):\n    return x.__class__") is not None
    assert runner.check_code("def g(x):\n    return x") == "no function named field"
    assert "numpy function" in runner.check_code("import numpy as np\ndef field(x,y,z):\n    np.save('f', x)\n    return x")
    assert runner.check_code("import numpy as np\ndef field(x,y,z):\n    return np.ctypeslib")
    assert runner.check_code("def field(x,y,z):\n    x.tofile('f')\n    return x")


def test_runner_extract_and_summary(tmp_path):
    out = runner.run_bench("age", mode="extract", output=tmp_path / "age.jsonl", per_tier=3, resume=False, log=lambda m: None)
    rows = metrics.load_rows(out)
    assert len(rows) == 21
    s = metrics.summarise(rows)
    assert s["extraction_field_accuracy"] > 0.5
    assert s["hallucination_rate"] is not None
    assert "out_of_scope_flagged" in s and "application_accuracy" in s
    table = metrics.markdown_table({"age": s})
    assert table.startswith("| system")
    # resume skips finished prompts
    runner.run_bench("age", mode="extract", output=out, per_tier=3, resume=True, log=lambda m: None)
    assert len(out.read_text(encoding="utf-8").splitlines()) == 21


def test_llm_direct_scored_without_network(tmp_path, monkeypatch):
    reply = {"domain_shape": "box", "domain_dimensions_mm": [10, 10, 10], "family": "gyroid", "porosity": 0.7, "cell_mm": 2.0, "stated_by_user": ["domain_shape", "domain_dimensions_mm", "family", "porosity", "cell_mm"], "feasible": True, "reason": "ok"}
    monkeypatch.setattr(runner, "_llm_chat", lambda model, prompt: "Here you go: " + json.dumps(reply))
    out = runner.run_bench("llm_direct:test/model", mode="propose", output=tmp_path / "d.jsonl", per_tier=1, tiers=[1, 2], resume=False, log=lambda m: None)
    rows = metrics.load_rows(out)
    assert len(rows) == 2 and all(r["status"] == "proposed" for r in rows)
    assert all("predicted_feasible" in r for r in rows)
