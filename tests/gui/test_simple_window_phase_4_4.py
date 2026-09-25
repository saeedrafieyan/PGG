"""Phase 4.4 simple window: Describe -> Review -> Download without a child process."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from test_design_agent_phase_4_3 import FakeGenerator, synthetic_tables  # noqa: E402,F401  (autouse fixture)

from porous_designer.gui.simple_window import SimpleWindow  # noqa: E402
from porous_designer.services.design_session import run_approved_snapshot  # noqa: E402


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_simple_window_flow(app, tmp_path, monkeypatch):
    w = SimpleWindow(preview=False)
    assert not w.approve_button.isEnabled()
    w.request.setPlainText("gyroid scaffold 10 x 10 x 6 mm box with 70% porosity")
    idx = w.process.findData("sla")
    w.process.setCurrentIndex(idx)
    w.propose()
    assert w.session.state == "proposed"
    assert "Porosity" in w.card.toHtml()
    assert w.approve_button.isEnabled()
    assert not w.download_buttons["report"].isEnabled()

    snapshot = w.session.snapshot()
    snapshot["output_dir"] = str(tmp_path / "out")
    payload = run_approved_snapshot(snapshot, generate=FakeGenerator(tmp_path))
    w._done(payload)
    assert w.download_buttons["report"].isEnabled()
    assert "Measured" in w.card.toHtml()
    w.close()


def test_simple_window_infeasible(app, tmp_path):
    w = SimpleWindow(preview=False)
    w.request.setPlainText("gyroid scaffold 30 x 30 x 30 mm box with 90% porosity and 1 mm pore size, FDM printer")
    w.propose()
    assert w.session.state == "infeasible"
    assert not w.approve_button.isEnabled()
    assert "Try instead" in w.card.toHtml()
    w.close()
