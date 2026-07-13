from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from porous_designer.domain.enums import DomainShape, StructureFamily
from porous_designer.domain.specification import (
    ConstraintsSpec,
    DesignSpecification,
    DomainSpec,
    ExportSpec,
    GenerationSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
)
from porous_designer.gui.dialogs.error_dialog import ErrorDialog
from porous_designer.gui.main_window import MainWindow
from porous_designer.gui.models.run_history_model import RunHistoryStore
from porous_designer.gui.panels.structure_panel import StructurePanel
from porous_designer.gui.reporting import generate_html_report
from porous_designer.gui.state_store import StateStore
from porous_designer.gui.workers.base_worker import ProcessWorker
from porous_designer.gui.workers.generation_worker import GenerationWorker
from porous_designer.gui.workers.preview_worker import PreviewWorker


def small_spec(tmp_path: Path, name: str = "gui_small") -> DesignSpecification:
    return DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[2.5, 2.5, 2.5]),
        structure=StructureSpec(family=StructureFamily.SC_SPHERICAL_PORES, pore_diameter_mm=0.8),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.45, tolerance=0.2)),
        constraints=ConstraintsSpec(require_open_pores=False, require_single_solid_component=False),
        generation=GenerationSpec(preview_resolution_mm=0.5, final_resolution_mm=0.5, maximum_memory_gb=4.0),
        export=ExportSpec(output_directory=str(tmp_path), output_name=name),
    )


def sleepy_worker(seconds: float) -> dict:
    time.sleep(seconds)
    return {"done": True}


def test_application_launch(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "PGG, Porous Geometry Generation"
    assert window.generation_panel.final_button.isEnabled()


def test_specification_field_binding_and_domain_switch(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.domain_panel.shape.setCurrentText("cylinder")
    window.domain_panel.cyl_diameter.setValue(5.0)
    window._collect_and_validate()
    spec = window.controller.specification
    assert spec.domain.shape == DomainShape.CYLINDER
    assert spec.domain.dimensions_mm == [5.0, 6.0]


def test_sphere_tpms_field_switching(qtbot):
    panel = StructurePanel()
    qtbot.addWidget(panel)
    assert panel.stack.currentIndex() == 0
    panel.family.setCurrentText("Gyroid")
    assert panel.stack.currentIndex() == 1


def test_invalid_field_disables_generation(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.structure_panel.pore_diameter.setValue(99.0)
    window._collect_and_validate()
    assert not window.generation_panel.preview_button.isEnabled()


def test_load_and_save_specification(tmp_path: Path):
    store = StateStore()
    spec = small_spec(tmp_path)
    path = tmp_path / "spec.yaml"
    store.set_specification(spec)
    store.save_specification(path)
    loaded = store.load_specification(path)
    assert loaded.export.output_name == "gui_small"


def test_estimate_resources(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.controller.state.set_specification(small_spec(tmp_path))
    estimate = window.controller.estimate()
    assert estimate
    assert estimate["voxel_count"] > 0


def test_preview_worker_generates_mesh(qtbot, tmp_path: Path):
    worker = PreviewWorker(small_spec(tmp_path, "preview_worker"))
    with qtbot.waitSignal(worker.result, timeout=30000) as blocker:
        worker.start()
    assert blocker.args[0]["stl_path"]
    assert Path(blocker.args[0]["stl_path"]).exists()


def test_cancel_preview_worker(qtbot):
    worker = ProcessWorker(sleepy_worker, (5.0,))
    with qtbot.waitSignal(worker.cancelled, timeout=10000):
        worker.start()
        qtbot.wait(250)
        worker.cancel()


def test_final_generation_worker_small_fixture(qtbot, tmp_path: Path):
    worker = GenerationWorker(small_spec(tmp_path, "final_worker"))
    with qtbot.waitSignal(worker.result, timeout=30000) as blocker:
        worker.start()
    payload = blocker.args[0]
    assert Path(payload["run_dir"]).exists()
    assert payload["profile"] == "final"


def test_cancel_final_generation_worker(qtbot):
    worker = ProcessWorker(sleepy_worker, (5.0,))
    with qtbot.waitSignal(worker.cancelled, timeout=10000):
        worker.start()
        qtbot.wait(250)
        worker.cancel()


def test_validation_table_population(qtbot, tmp_path: Path):
    worker = GenerationWorker(small_spec(tmp_path, "validation_table"))
    with qtbot.waitSignal(worker.result, timeout=30000) as blocker:
        worker.start()
    report = json.loads(Path(blocker.args[0]["validation_report_path"]).read_text(encoding="utf-8"))
    window = MainWindow()
    qtbot.addWidget(window)
    window.validation_panel.set_report(report)
    assert window.validation_panel.model.rowCount() > 0


def test_run_history_loading(tmp_path: Path, qtbot):
    worker = GenerationWorker(small_spec(tmp_path, "history"))
    with qtbot.waitSignal(worker.result, timeout=30000) as blocker:
        worker.start()
    store = RunHistoryStore(tmp_path / "history.sqlite")
    records = store.scan_runs(tmp_path)
    assert records
    assert records[0].output_folder == blocker.args[0]["run_dir"]


def test_open_previous_run_and_duplicate(qtbot, tmp_path: Path):
    worker = GenerationWorker(small_spec(tmp_path, "open_previous"))
    with qtbot.waitSignal(worker.result, timeout=30000) as blocker:
        worker.start()
    window = MainWindow()
    qtbot.addWidget(window)
    run_dir = blocker.args[0]["run_dir"]
    window._open_run(run_dir)
    window.controller.duplicate_run_specification(run_dir)
    assert window.controller.specification.export.output_name == "open_previous"


def test_error_dialog_and_step_disabled(qtbot):
    dialog = ErrorDialog("SPEC_INVALID", "bad field", "details")
    qtbot.addWidget(dialog)
    assert "PGG Error" in dialog.windowTitle()
    window = MainWindow()
    qtbot.addWidget(window)
    assert not window.generation_panel.step_disabled.isEnabled()
    assert "STEP disabled" in window.generation_panel.step_disabled.text()


def test_html_report_generation(qtbot, tmp_path: Path):
    worker = GenerationWorker(small_spec(tmp_path, "html_report"))
    with qtbot.waitSignal(worker.result, timeout=30000) as blocker:
        worker.start()
    report = generate_html_report(Path(blocker.args[0]["run_dir"]))
    assert report.exists()
    assert "PGG Run Report" in report.read_text(encoding="utf-8")


@pytest.mark.slow
def test_small_end_to_end_gui_generation(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.controller.state.set_specification(small_spec(tmp_path, "e2e_gui"))
    with qtbot.waitSignal(window.controller.run_completed, timeout=30000) as blocker:
        window.controller.start_preview()
    assert Path(blocker.args[0]["stl_path"]).exists()
