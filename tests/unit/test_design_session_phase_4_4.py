"""Phase 4.4 service layer and web API (synthetic tables, fake generator)."""

from __future__ import annotations

import time

import pytest

from porous_designer.services.design_session import DesignSession, proposal_card

from test_design_agent_phase_4_3 import FakeGenerator, synthetic_tables  # noqa: F401  (autouse fixture)


def test_session_describe_review_download(tmp_path):
    gen = FakeGenerator(tmp_path)
    s = DesignSession(output_dir=tmp_path / "out", generate=gen)
    card = s.propose("bone scaffold, gyroid, 10 x 10 x 6 mm box", process="sla")
    assert s.state == "proposed" and not gen.specs
    labels = {n["label"]: n for n in card["numbers"]}
    assert labels["Porosity"]["source"] == "from the literature"
    assert labels["Architecture"]["source"] == "from your request"
    assert card["citations"] and card["predicted"]
    result = s.approve()
    assert s.state == "done" and len(gen.specs) == 1
    assert result["status"] == "delivered"
    files = s.files()
    assert {"report", "trace"} <= set(files)
    text = files["report"].read_text(encoding="utf-8")
    assert "Design intent" in text and "References" in text


def test_session_infeasible_card_has_alternatives(tmp_path):
    s = DesignSession(output_dir=tmp_path / "out", generate=FakeGenerator(tmp_path))
    card = s.propose("gyroid scaffold 30 x 30 x 30 mm box with 90% porosity and 1 mm pore size, FDM printer")
    assert s.state == "infeasible"
    assert card["explanation"] and card["alternatives"]
    with pytest.raises(RuntimeError):
        s.approve()


def test_web_api_round_trip(tmp_path):
    pytest.importorskip("starlette")
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    from porous_designer.api.server import SessionStore, create_app

    store = SessionStore(output_dir=tmp_path / "out", generate=FakeGenerator(tmp_path))
    client = TestClient(create_app(store))
    assert "AGE Designer" in client.get("/").text
    assert any(p["id"] == "generic_msla" for p in client.get("/api/printers").json())
    r = client.post("/api/sessions", json={"text": "gyroid scaffold 10 x 10 x 6 mm box with 70% porosity", "process": "sla"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert r.json()["proposal"]["status"] == "proposed"
    assert client.post(f"/api/sessions/{sid}/approve").status_code == 202
    for _ in range(100):
        d = client.get(f"/api/sessions/{sid}").json()
        if d["state"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert d["state"] == "done", d
    assert "report" in d["files"]
    rep = client.get(f"/api/sessions/{sid}/files/report")
    assert rep.status_code == 200 and "AGE design report" in rep.text
    assert client.post(f"/api/sessions/{sid}/approve").status_code == 409
    assert client.post("/api/sessions", json={"text": ""}).status_code == 400
