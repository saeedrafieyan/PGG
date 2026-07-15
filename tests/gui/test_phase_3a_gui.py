from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from porous_designer.agentic.contracts import FieldReviewDecision, ProviderMode
from porous_designer.agentic.credentials import CredentialLookupResult
from porous_designer.agentic.provider import MockAgentProvider
from porous_designer.agentic.provider_config import CredentialMode, ExternalCallMode, ProviderSettings
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
from porous_designer.gui.dialogs.provider_settings_dialog import ProviderSettingsDialog
from porous_designer.gui.dialogs.specification_review_dialog import SpecificationReviewDialog
from porous_designer.gui.main_window import MainWindow
from porous_designer.gui.models.run_history_model import RunHistoryStore
from porous_designer.gui.panels.structure_panel import StructurePanel
from porous_designer.gui.rendering import PRESETS, preset
from porous_designer.gui.reporting import generate_html_report
from porous_designer.gui.state_store import StateStore
from porous_designer.gui.workers.base_worker import ProcessWorker
from porous_designer.gui.workers.generation_worker import GenerationWorker
from porous_designer.gui.workers.preview_worker import PreviewWorker
from porous_designer.gui.workflow import ApplicationMode


def small_spec(tmp_path: Path, name: str = "gui_small") -> DesignSpecification:
    return DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[2.5, 2.5, 2.5]),
        structure=StructureSpec(family=StructureFamily.SC_SPHERICAL_PORES, pore_diameter_mm=0.8),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.45, tolerance=0.2)),
        constraints=ConstraintsSpec(require_open_pores=False, require_single_solid_component=False),
        generation=GenerationSpec(preview_resolution_mm=0.5, final_resolution_mm=0.5, maximum_memory_gb=4.0),
        export=ExportSpec(output_directory=str(tmp_path), output_name=name),
    )


def sleepy_job(payload: dict, result_queue, event_queue) -> None:
    time.sleep(payload["seconds"])
    result_queue.put({"kind": "result", "payload": {"done": True}})


def unexpected_exit_job(payload: dict, result_queue, event_queue) -> None:
    os._exit(payload.get("code", 7))


def failing_job(payload: dict, result_queue, event_queue) -> None:
    raise RuntimeError("intentional worker failure")


def test_importing_gui_app_does_not_create_qapplication():
    code = (
        "from PySide6.QtWidgets import QApplication; "
        "import porous_designer.gui.app; "
        "print(QApplication.instance()); print(len(QApplication.topLevelWidgets()))"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=Path.cwd(), capture_output=True, text=True, check=True)
    assert "None" in result.stdout
    assert result.stdout.strip().endswith("0")


def test_importing_worker_modules_does_not_create_top_level_widgets():
    code = (
        "from PySide6.QtWidgets import QApplication; "
        "import porous_designer.gui.workers.preview_worker; "
        "import porous_designer.gui.workers.generation_worker; "
        "print(QApplication.instance()); print(len(QApplication.topLevelWidgets()))"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=Path.cwd(), capture_output=True, text=True, check=True)
    assert "None" in result.stdout
    assert result.stdout.strip().endswith("0")


def test_application_launch(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "PGG, Porous Geometry Generation"
    assert window.generation_panel.final_button.isEnabled()
    assert window.application_mode == ApplicationMode.MANUAL_DESIGN


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
    before = len(QApplication.topLevelWidgets())
    estimate = window.controller.estimate()
    assert estimate
    assert estimate["voxel_count"] > 0
    assert window.feasibility_panel.status.text()
    assert len(QApplication.topLevelWidgets()) == before


def test_estimate_failure_restores_button_state(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)

    def fail(*args, **kwargs):
        raise RuntimeError("estimate failure")

    monkeypatch.setattr("porous_designer.gui.application_controller.estimate_resources", fail)
    monkeypatch.setattr(window.controller, "show_error", lambda *args, **kwargs: None)
    assert window.controller.estimate() is None
    assert window.generation_panel.estimate_button.isEnabled()


def test_preview_worker_generates_mesh(qtbot, tmp_path: Path):
    worker = PreviewWorker(small_spec(tmp_path, "preview_worker"))
    with qtbot.waitSignal(worker.result, timeout=30000) as blocker:
        worker.start()
    assert blocker.args[0]["stl_path"]
    assert Path(blocker.args[0]["stl_path"]).exists()
    assert isinstance(blocker.args[0]["stl_path"], str)
    assert worker.child_pid is not None


def test_cancel_preview_worker(qtbot):
    worker = ProcessWorker(sleepy_job, {"seconds": 5.0}, worker_type="sleepy")
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
    worker = ProcessWorker(sleepy_job, {"seconds": 5.0}, worker_type="sleepy")
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


def test_rendering_presets_are_available_and_distinct():
    assert {"Scientific", "High Contrast", "Light Background", "Wireframe", "Surface + Edges"} <= set(PRESETS)
    assert preset("Scientific").background_color != preset("Light Background").background_color
    assert preset("Scientific").mesh_color != "#add8e6"


def test_preview_panel_preset_controls_do_not_reload_geometry(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    panel = window.preview_panel
    before = panel._mesh_path
    panel.apply_preset("High Contrast")
    assert panel.settings.preset == "High Contrast"
    assert panel._mesh_path == before


def test_verbose_rendering_diagnostics_absent_from_preview_layout(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    panel_text = window.preview_panel.findChildren(QLabel)
    visible_text = "\n".join(label.text() for label in panel_text)
    assert "OpenGL renderer" not in visible_text
    assert "OpenGL extensions" not in visible_text
    assert not hasattr(window.preview_panel, "diagnostics")


def test_compact_preview_status_before_and_after_preview(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.preview_panel.status.text() == "No preview loaded"
    window.preview_panel.capabilities["fallback"] = False
    window.preview_panel.capabilities["warning"] = ""
    window.preview_panel._mesh_path = Path("runs/example_preview.stl")
    window.preview_panel._update_status()
    assert "PREVIEW" in window.preview_panel.status.text()
    assert "Not final validation" in window.preview_panel.status.text()
    assert window.preview_panel.settings.preset in window.preview_panel.status.text()


def test_final_artifact_status_is_not_called_preview(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.preview_panel.capabilities["fallback"] = False
    window.preview_panel._mesh_path = Path("runs/final_master.stl")
    window.preview_panel._artifact_state = "final"
    window.preview_panel._validation_status = "accepted"
    window.preview_panel._update_status()
    assert "FINAL ARTIFACT VIEW" in window.preview_panel.status.text()
    assert "PREVIEW" not in window.preview_panel.status.text()


def test_rendering_diagnostics_dialog_copy_save_refresh(qtbot, tmp_path: Path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window._show_diagnostics()
    dialog = window._diagnostics_dialog
    qtbot.addWidget(dialog)
    assert dialog.tabs.tabText(1) == "Rendering"
    assert dialog.tabs.tabText(2) == "Agent Provider"
    assert not dialog.extensions_group.isChecked()
    assert not dialog.extensions_text.isVisible()
    assert "Active preset" in dialog.rendering_summary.toPlainText()

    dialog.copy_rendering_diagnostics()
    assert "Active preset" in QApplication.clipboard().text()
    dialog.copy_provider_diagnostics()
    assert "external_access_enabled" in QApplication.clipboard().text()

    target = tmp_path / "diagnostics.txt"
    monkeypatch.setattr(
        "porous_designer.gui.dialogs.diagnostics_dialog.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(target), "Text (*.txt)"),
    )
    saved = dialog.save_diagnostics()
    assert saved == target
    assert "Rendering" in target.read_text(encoding="utf-8")
    dialog.refresh()
    assert "Active preset" in dialog.rendering_summary.toPlainText()


def test_phase_3a3_toolbar_labels_are_readable(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.preview_panel.reset_rendering_button.text() == "Reset Appearance"
    assert window.preview_panel.transparent.text() == "Transparent Exterior"


def test_screenshot_sidecar_created_in_fallback(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    with qtbot.waitSignal(window.preview_panel.screenshot_saved, timeout=5000) as blocker:
        window.preview_panel.save_screenshot()
    path = Path(blocker.args[0])
    assert path.exists()
    assert path.with_suffix(".json").exists()


def test_phase_3a2_visual_smoke_screenshots_are_nonuniform():
    from PIL import Image
    import numpy as np

    for image_path in (
        Path("docs/phase_3a2_after_gyroid_scientific.png"),
        Path("docs/phase_3a2_after_gyroid_light.png"),
    ):
        if not image_path.exists():
            pytest.skip(f"{image_path} has not been captured in this checkout")
        image = Image.open(image_path).convert("RGB")
        assert image.width >= 640
        assert image.height >= 360
        arr = np.asarray(image)
        luminance = arr.mean(axis=2)
        assert float(luminance.std()) > 15.0
        sample = arr.reshape(-1, 3)[:: max(1, arr.shape[0] * arr.shape[1] // 5000)]
        assert len(np.unique(sample, axis=0)) > 20


def test_preview_failure_is_reported(qtbot):
    worker = ProcessWorker(failing_job, {}, worker_type="failure")
    with qtbot.waitSignal(worker.error, timeout=10000) as blocker:
        worker.start()
    assert "intentional worker failure" in blocker.args[0]["message"]


def test_child_unexpected_exit_is_handled(qtbot):
    worker = ProcessWorker(unexpected_exit_job, {"code": 9}, worker_type="unexpected")
    with qtbot.waitSignal(worker.error, timeout=10000) as blocker:
        worker.start()
    assert blocker.args[0]["exit_code"] == 9


def test_main_gui_remains_responsive_during_preview(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)
    ticks = {"count": 0}
    from PySide6.QtCore import QTimer

    timer = QTimer()
    timer.setInterval(50)
    timer.timeout.connect(lambda: ticks.__setitem__("count", ticks["count"] + 1))
    timer.start()
    window.controller.state.set_specification(small_spec(tmp_path, "responsive_preview"))
    with qtbot.waitSignal(window.controller.run_completed, timeout=30000):
        window.controller.start_preview()
    timer.stop()
    assert ticks["count"] > 3


def test_repeated_estimate_clicks_create_no_widgets(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    before = len(QApplication.topLevelWidgets())
    for _ in range(3):
        window.controller.estimate()
    assert len(QApplication.topLevelWidgets()) == before


def test_repeated_preview_clicks_do_not_create_duplicate_windows(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.controller.state.set_specification(small_spec(tmp_path, "repeat_preview"))
    before = len(QApplication.topLevelWidgets())
    with qtbot.waitSignal(window.controller.run_completed, timeout=30000):
        window.controller.start_preview()
        window.controller.start_preview()
    assert len(QApplication.topLevelWidgets()) <= before


def test_closing_gui_terminates_active_worker(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    worker = ProcessWorker(sleepy_job, {"seconds": 5.0}, worker_type="sleepy", parent=window.controller)
    window.controller.worker = worker
    worker.start()
    qtbot.waitUntil(lambda: worker.child_pid is not None, timeout=5000)
    window.close()
    qtbot.waitUntil(lambda: not worker.is_running, timeout=10000)


def test_html_report_generation(qtbot, tmp_path: Path):
    worker = GenerationWorker(small_spec(tmp_path, "html_report"))
    with qtbot.waitSignal(worker.result, timeout=30000) as blocker:
        worker.start()
    report = generate_html_report(Path(blocker.args[0]["run_dir"]))
    assert report.exists()
    assert "PGG Run Report" in report.read_text(encoding="utf-8")


def test_agentic_panel_accepts_text_and_parses_structured_only(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._switch_to_agentic_design(confirm=False)
    panel = window.agentic_request_panel
    panel.request_text.setPlainText("Generate an 8 x 14 x 8 mm scaffold with hexagonal packing and 75-80% porosity.")
    window._parse_agentic_request(panel.request_text.toPlainText())
    assert "Structured-only" in panel.provider_label.text()
    assert panel.fields_model.rowCount() > 0
    assert panel.review_button.isEnabled()
    assert window.controller.worker is None


def test_agentic_privacy_notice_and_example(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert "External agent access is disabled" in window.agentic_request_panel.privacy_notice.text()
    window.agentic_request_panel.load_example()
    assert "scaffold" in window.agentic_request_panel.request_text.toPlainText().lower()


def test_specification_review_dialog_reject_and_edit(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    parsed = window.agentic.parse_request("Create a 4 x 4 x 4 mm HCP scaffold with 1 mm generating sphere diameter.", window.controller.specification)
    dialog = SpecificationReviewDialog(window.controller.specification, parsed)
    qtbot.addWidget(dialog)
    dialog.reject_all()
    assert all(decision.decision == "rejected" for decision in dialog.decisions())
    dialog.reset_decisions()
    row = next(i for i, item in enumerate(parsed.extracted_fields) if item.field_path == "structure.pore_diameter_mm")
    dialog.table.item(row, 2).setText("1.5")
    dialog._decision_widgets[row].setCurrentText("edited")
    edited = dialog.decisions()[row]
    assert edited.decision == "edited"
    assert edited.edited_value == 1.5


def test_agentic_approval_applies_fields_and_does_not_start_preview(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window._switch_to_agentic_design(confirm=False)
    window._parse_agentic_request("Create a 10 x 10 x 5 mm HCP scaffold with 1.2 mm generating sphere diameter and 72% porosity.")
    parsed = window.agentic.last_result
    assert parsed is not None

    monkeypatch.setattr(
        "porous_designer.gui.main_window.AmbiguityResolutionDialog.exec",
        lambda self: QDialog.Accepted,
    )
    monkeypatch.setattr(
        "porous_designer.gui.main_window.AmbiguityResolutionDialog.resolutions",
        lambda self: {item.identifier: item.recommended_choice for item in parsed.ambiguities},
    )
    monkeypatch.setattr(
        "porous_designer.gui.main_window.SpecificationReviewDialog.exec",
        lambda self: QDialog.Accepted,
    )
    monkeypatch.setattr(
        "porous_designer.gui.main_window.SpecificationReviewDialog.decisions",
        lambda self: [FieldReviewDecision(field_path=item.field_path, decision="accepted") for item in parsed.extracted_fields],
    )
    estimate_calls = {"count": 0}
    monkeypatch.setattr(window.controller, "estimate", lambda: estimate_calls.__setitem__("count", estimate_calls["count"] + 1) or {"status": "feasible"})
    window._review_agentic_specification()
    assert window.controller.specification.structure.family == StructureFamily.HCP_SPHERICAL_PORES
    assert window.structure_panel.pore_diameter.value() == pytest.approx(1.2)
    assert estimate_calls["count"] == 0
    assert not window.agentic_execution_authorized
    assert window.strategy_plan is None
    assert not window.generation_panel.preview_button.isEnabled()
    assert window.controller.worker is None


def test_agentic_approval_becomes_stale_after_manual_edit(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window._switch_to_agentic_design(confirm=False)
    window._parse_agentic_request("Create a 4 x 4 x 4 mm HCP scaffold with 1 mm generating sphere diameter.")
    parsed = window.agentic.last_result
    assert parsed is not None
    monkeypatch.setattr(window.controller, "estimate", lambda: {"status": "feasible"})
    approved, record = window.agentic.approve(
        window.controller.specification,
        [FieldReviewDecision(field_path=item.field_path, decision="accepted") for item in parsed.extracted_fields],
    )
    window._apply_specification_to_panels(approved)
    window.agentic.last_approval = record
    window.domain_panel.box_x.setValue(5.0)
    assert window.agentic.status.value == "Approval stale"


def test_provider_settings_default_deterministic_and_disabled(qtbot):
    dialog = ProviderSettingsDialog(ProviderSettings())
    qtbot.addWidget(dialog)
    assert not dialog.external_access.isChecked()
    assert dialog.provider.currentText() == "Deterministic only"
    assert dialog.model_category.text() == "None"
    assert "No external LLM is required" in dialog.privacy.text()


def test_provider_selector_model_category_and_missing_key(qtbot, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    dialog = ProviderSettingsDialog(ProviderSettings())
    qtbot.addWidget(dialog)
    dialog.provider.setCurrentText("OpenAI")
    assert dialog.model.currentText() == "gpt-5.6-luna"
    assert dialog.model_category.text() == "Low cost"
    assert "Stored key:" in dialog.key_source.text()


def test_provider_settings_secure_key_storage_and_delete(qtbot, monkeypatch):
    stored = {}

    def fake_store(provider, key):
        stored[provider] = key

    def fake_lookup(provider, mode):
        return CredentialLookupResult(provider in stored, mode.value, "sk-t...cret" if provider in stored else "", stored.get(provider), backend="FakeKeyring", message="Stored key: Available" if provider in stored else "Stored key: Not found")

    def fake_delete(provider):
        stored.pop(provider, None)

    monkeypatch.setattr("porous_designer.gui.dialogs.provider_settings_dialog.store_api_key", fake_store)
    monkeypatch.setattr("porous_designer.gui.dialogs.provider_settings_dialog.lookup_api_key", fake_lookup)
    monkeypatch.setattr("porous_designer.gui.dialogs.provider_settings_dialog.delete_api_key", fake_delete)
    dialog = ProviderSettingsDialog(ProviderSettings(credential_mode=CredentialMode.KEYRING))
    qtbot.addWidget(dialog)
    dialog.provider.setCurrentText("OpenAI")
    dialog.external_access.setChecked(True)
    dialog.api_key.setText("sk-test-secret")
    dialog._save_or_apply(close=False)
    assert stored["openai"] == "sk-test-secret"
    assert dialog.api_key.text() == ""
    assert "Stored key: Available" in dialog.key_source.text()
    dialog._delete_key()
    assert "openai" not in stored


def test_provider_dialog_cancel_discards_unsaved_key(qtbot):
    dialog = ProviderSettingsDialog(ProviderSettings(provider_mode=ProviderMode.OPENAI))
    qtbot.addWidget(dialog)
    dialog.provider.setCurrentText("OpenAI")
    dialog.api_key.setText("sk-unsaved-secret")
    dialog._cancel()
    assert dialog.api_key.text() == ""


def test_provider_connection_failure_display(qtbot):
    dialog = ProviderSettingsDialog(ProviderSettings())
    qtbot.addWidget(dialog)
    dialog.provider.setCurrentText("OpenAI")
    dialog.external_access.setChecked(True)
    dialog._test_connection()
    assert "ok" in dialog.payload_preview.toPlainText()


def test_provider_test_connection_enables_temporary_session_key(qtbot, monkeypatch):
    seen = {}

    class FakeOpenAIProvider:
        def __init__(self, settings):
            seen["external_access_enabled"] = settings.external_access_enabled
            seen["credential_mode"] = settings.credential_mode
            seen["model"] = settings.selected_model()

        def test_connection(self):
            return {"ok": True, "provider": "openai", "model": seen["model"], "latency_s": 0.01}

    monkeypatch.setattr("porous_designer.gui.dialogs.provider_settings_dialog.OpenAIProvider", FakeOpenAIProvider)
    dialog = ProviderSettingsDialog(ProviderSettings(provider_mode=ProviderMode.OPENAI, external_access_enabled=False))
    qtbot.addWidget(dialog)
    dialog.provider.setCurrentText("OpenAI")
    dialog.api_key.setText("sk-unsaved-session-secret")
    dialog._test_connection()
    assert seen["external_access_enabled"] is True
    assert seen["credential_mode"] == CredentialMode.SESSION
    assert "Connection result: successful" in dialog.payload_preview.toPlainText()
    assert "sk-unsaved-session-secret" not in dialog.payload_preview.toPlainText()


def test_agentic_call_decision_display_and_no_external_call(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._switch_to_agentic_design(confirm=False)
    window._parse_agentic_request("Create a 4 x 4 x 4 mm HCP scaffold with 70% porosity.")
    result = window.agentic.last_result
    assert result is not None
    assert result.provider_metadata["external_call_decision"]["decision_code"] in {"EXTERNAL_ACCESS_DISABLED", "NO_EXTERNAL_CALL_REQUIRED"}
    assert "Last decision:" in window.agentic_request_panel.provider_status.text()
    assert window.controller.worker is None


def test_provider_rebuild_and_deterministic_only_button(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    settings = ProviderSettings(external_access_enabled=True, external_call_mode=ExternalCallMode.WHEN_RECOMMENDED)
    settings.provider_mode = ProviderMode.OPENAI
    settings.bump_version()
    window._provider_settings_changed(settings)
    assert window.agentic.settings is settings
    assert "Provider: openai" in window.agentic_request_panel.provider_status.text()
    window._use_deterministic_only()
    assert "Provider: deterministic" in window.agentic_request_panel.provider_status.text()
    assert not window.provider_settings.external_access_enabled


def test_provider_diagnostics_redacts_key(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._last_provider_fallback = "authentication failed for sk-testSECRET123456"
    text = window._provider_diagnostics_text()
    assert "sk-testSECRET123456" not in text
    assert "[REDACTED]" in text


def approve_agentic_hcp(window: MainWindow, monkeypatch):
    window._switch_to_agentic_design(confirm=False)
    window._parse_agentic_request("Create a 4 x 4 x 4 mm HCP scaffold with 1 mm generating sphere diameter and 70% porosity.")
    parsed = window.agentic.last_result
    assert parsed is not None
    monkeypatch.setattr(
        "porous_designer.gui.main_window.SpecificationReviewDialog.exec",
        lambda self: QDialog.Accepted,
    )
    monkeypatch.setattr(
        "porous_designer.gui.main_window.SpecificationReviewDialog.decisions",
        lambda self: [FieldReviewDecision(field_path=item.field_path, decision="accepted") for item in parsed.extracted_fields],
    )
    window._review_agentic_specification()
    return parsed


def approve_agentic_hcp_plan(window: MainWindow, monkeypatch):
    parsed = approve_agentic_hcp(window, monkeypatch)
    window._generate_strategy_plan()
    window._approve_strategy_plan()
    return parsed


def test_phase_3b13_manual_and_agentic_modes_are_separate(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.application_mode == ApplicationMode.MANUAL_DESIGN
    assert window.agentic_group.isHidden()
    assert not window.domain_group.isHidden()
    assert window.generation_panel.preview_resolution.isEnabled()

    window._switch_to_agentic_design(confirm=False)
    assert window.application_mode == ApplicationMode.AGENTIC_DESIGN
    assert window.domain_group.isHidden()
    assert not window.agentic_group.isHidden()
    assert not window.agentic_summary_box.isHidden()
    assert not window.generation_panel.preview_resolution.isEnabled()


def test_phase_3b13_mode_persists_after_restart(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._switch_to_agentic_design(confirm=False)
    restarted = MainWindow()
    qtbot.addWidget(restarted)
    assert restarted.application_mode == ApplicationMode.AGENTIC_DESIGN
    assert restarted.domain_group.isHidden()


def test_phase_3b13_manual_mode_blocks_provider_parse(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._parse_agentic_request("Create a 4 x 4 x 4 mm HCP scaffold.")
    assert window.agentic.last_result is None
    assert "Switch to Agentic Design" in window.progress_label.text()


def test_phase_3b13_agentic_to_manual_creates_editable_copy(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    approve_agentic_hcp(window, monkeypatch)
    approval = window.agentic.last_approval
    assert approval is not None
    assert window.agentic_revision is not None
    assert window.agentic_revision.approval_status == "approved"

    window._switch_to_manual_design(confirm=False)
    assert window.application_mode == ApplicationMode.MANUAL_DESIGN
    assert window.manual_revision.origin == "derived_from_agentic_specification"
    assert window.agentic.last_approval is approval
    assert window.agentic_execution_authorized is False
    assert not window.domain_group.isHidden()
    assert window.domain_panel.box_x.isEnabled()


def test_phase_3b13_stale_agentic_approval_blocks_preview_and_final(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    approve_agentic_hcp_plan(window, monkeypatch)
    assert window.agentic_execution_authorized
    calls = {"preview": 0, "final": 0}
    monkeypatch.setattr(window.controller, "start_preview", lambda **kwargs: calls.__setitem__("preview", calls["preview"] + 1))
    monkeypatch.setattr(window.controller, "start_final", lambda *args, **kwargs: calls.__setitem__("final", calls["final"] + 1))
    window._request_agentic_changes()
    window._preview_requested()
    window._final_requested()
    assert calls == {"preview": 0, "final": 0}
    assert "Approval stale" in window.progress_label.text()


def test_phase_3b13_manual_generation_does_not_require_agentic_approval(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    calls = {"preview": 0}
    monkeypatch.setattr(window.controller, "start_preview", lambda **kwargs: calls.__setitem__("preview", calls["preview"] + 1))
    window._preview_requested()
    assert calls["preview"] == 1
    assert window._run_metadata(user_action="generate_preview")["approval_status"] == "not_required"


def test_phase_3b2_agentic_plan_section_hidden_before_approval(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._switch_to_agentic_design(confirm=False)
    assert window.strategy_plan_box.isHidden()


def test_phase_3b2_generate_strategy_plan_appears_after_approval(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    approve_agentic_hcp(window, monkeypatch)
    assert not window.strategy_plan_box.isHidden()
    assert window.strategy_plan_panel.generate_button.isEnabled()


def test_phase_3b2_plan_table_displays_steps(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    approve_agentic_hcp(window, monkeypatch)
    window._generate_strategy_plan()
    text = window.strategy_plan_panel.plan_text.toPlainText()
    assert "Estimate resources" in text
    assert "generate_preview" in text


def test_phase_3b2_unsupported_step_note_appears(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window._switch_to_agentic_design(confirm=False)
    window._parse_agentic_request("Create a 4 x 4 x 4 mm HCP scaffold with 1 mm generating sphere diameter and STEP-only output.")
    parsed = window.agentic.last_result
    assert parsed is not None
    monkeypatch.setattr("porous_designer.gui.main_window.SpecificationReviewDialog.exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(
        "porous_designer.gui.main_window.SpecificationReviewDialog.decisions",
        lambda self: [FieldReviewDecision(field_path=item.field_path, decision="accepted") for item in parsed.extracted_fields],
    )
    window._review_agentic_specification()
    window._generate_strategy_plan()
    assert "STEP" in window.strategy_plan_panel.plan_text.toPlainText()


def test_phase_3b2_approve_and_reject_plan(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    approve_agentic_hcp(window, monkeypatch)
    window._generate_strategy_plan()
    window._approve_strategy_plan()
    assert window.strategy_plan is not None
    assert window.strategy_plan.status == "approved"
    assert window.agentic_execution_authorized
    window._reject_strategy_plan()
    assert window.strategy_plan.status == "rejected"
    assert not window.agentic_execution_authorized


def test_phase_3b2_stale_plan_blocks_execution(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    approve_agentic_hcp_plan(window, monkeypatch)
    calls = {"preview": 0, "final": 0}
    monkeypatch.setattr(window.controller, "start_preview", lambda **kwargs: calls.__setitem__("preview", calls["preview"] + 1))
    monkeypatch.setattr(window.controller, "start_final", lambda *args, **kwargs: calls.__setitem__("final", calls["final"] + 1))
    window._request_agentic_changes()
    assert window.strategy_plan is not None
    assert window.strategy_plan.status == "stale"
    window._preview_requested()
    window._final_requested()
    assert calls == {"preview": 0, "final": 0}


def test_phase_3b2_manual_mode_does_not_show_agentic_plan_section(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.application_mode == ApplicationMode.MANUAL_DESIGN
    assert window.strategy_plan_box.isHidden()


def test_phase_3b2_plan_approval_required_before_agentic_final(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    approve_agentic_hcp(window, monkeypatch)
    calls = {"final": 0}
    monkeypatch.setattr(window.controller, "start_final", lambda *args, **kwargs: calls.__setitem__("final", calls["final"] + 1))
    window._final_requested()
    assert calls["final"] == 0
    assert "strategy plan" in window.progress_label.text().lower() or "Approval stale" in window.progress_label.text()


def test_phase_3b2_user_triggered_estimate_updates_plan_step(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    approve_agentic_hcp_plan(window, monkeypatch)
    monkeypatch.setattr(window.controller, "estimate", lambda: {"status": "feasible", "voxel_count": 125, "runtime_class": "small"})
    window._estimate_requested()
    assert window.strategy_plan_observations
    assert window.strategy_plan_observations[-1].tool_name == "estimate_resources"


def test_phase_3b2_user_triggered_preview_updates_plan_step(qtbot, monkeypatch, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    approve_agentic_hcp_plan(window, monkeypatch)
    payload = {"profile": "preview", "run_id": "preview-run", "run_dir": str(tmp_path), "stl_path": str(tmp_path / "preview.stl")}
    window._run_completed(payload)
    assert window.strategy_plan_observations
    assert window.strategy_plan_observations[-1].tool_name == "generate_preview"


def test_phase_3b2_no_automatic_preview_or_final_after_plan_approval(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    approve_agentic_hcp(window, monkeypatch)
    calls = {"preview": 0, "final": 0}
    monkeypatch.setattr(window.controller, "start_preview", lambda **kwargs: calls.__setitem__("preview", calls["preview"] + 1))
    monkeypatch.setattr(window.controller, "start_final", lambda *args, **kwargs: calls.__setitem__("final", calls["final"] + 1))
    window._generate_strategy_plan()
    window._approve_strategy_plan()
    assert calls == {"preview": 0, "final": 0}


def test_phase_3b2_provider_enhanced_wording_does_not_add_forbidden_tools(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    approve_agentic_hcp(window, monkeypatch)
    settings = ProviderSettings(external_access_enabled=True, provider_mode=ProviderMode.OPENAI)
    window.provider_settings = settings
    window.agentic.provider = MockAgentProvider(strategy_response={"summary": "Generate STEP and run FEA.", "tool_proposals": [{"tool_name": "fea"}]})
    window._generate_strategy_plan()
    assert window.strategy_plan is not None
    assert "Generate STEP" not in window.strategy_plan.summary
    assert not any(step.deterministic_tool == "fea" for step in window.strategy_plan.steps)


@pytest.mark.slow
def test_small_end_to_end_gui_generation(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.controller.state.set_specification(small_spec(tmp_path, "e2e_gui"))
    with qtbot.waitSignal(window.controller.run_completed, timeout=30000) as blocker:
        window.controller.start_preview()
    assert Path(blocker.args[0]["stl_path"]).exists()
