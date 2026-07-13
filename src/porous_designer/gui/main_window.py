"""Main window for PGG, Porous Geometry Generation."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QGroupBox,
    QLabel,
    QMainWindow,
    QProgressBar,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from porous_designer.agentic.orchestrator import AgenticRequestOrchestrator
from porous_designer.agentic.provider_config import ProviderSettings
from porous_designer.agentic.provider_factory import provider_from_settings
from porous_designer.gui.application_controller import ApplicationController
from porous_designer.gui.dialogs.about_dialog import show_about
from porous_designer.gui.dialogs.ambiguity_resolution_dialog import AmbiguityResolutionDialog
from porous_designer.gui.dialogs.diagnostics_dialog import DiagnosticsDialog
from porous_designer.gui.dialogs.provider_settings_dialog import ProviderSettingsDialog
from porous_designer.gui.dialogs.run_details_dialog import RunDetailsDialog
from porous_designer.gui.dialogs.specification_review_dialog import SpecificationReviewDialog
from porous_designer.gui.diagnostics import gui_event, runtime_diagnostics
from porous_designer.gui.models.run_history_model import RunHistoryStore
from porous_designer.gui.panels.agentic_request_panel import AgenticRequestPanel
from porous_designer.gui.panels.domain_panel import DomainPanel
from porous_designer.gui.panels.feasibility_panel import FeasibilityPanel
from porous_designer.gui.panels.generation_panel import GenerationPanel
from porous_designer.gui.panels.logs_panel import LogsPanel
from porous_designer.gui.panels.manufacturing_panel import ManufacturingPanel
from porous_designer.gui.panels.preview_panel import PreviewPanel
from porous_designer.gui.panels.request_panel import RequestPanel
from porous_designer.gui.panels.run_history_panel import RunHistoryPanel
from porous_designer.gui.panels.structure_panel import StructurePanel
from porous_designer.gui.panels.targets_panel import TargetsPanel
from porous_designer.gui.panels.validation_panel import ValidationPanel
from porous_designer.gui.state_store import StateStore


def group(title: str, widget: QWidget) -> QGroupBox:
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.addWidget(widget)
    return box


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        gui_event("main_window_constructing")
        self.setWindowTitle("PGG, Porous Geometry Generation")
        self.setMinimumSize(1280, 820)
        self.state = StateStore(self)
        self.history_store = RunHistoryStore(Path("runs") / "pgg_run_history.sqlite")
        self.controller = ApplicationController(self.state, self.history_store, self)
        self.provider_settings = ProviderSettings()
        self.agentic = AgenticRequestOrchestrator(provider_from_settings(self.provider_settings), audit_root=Path("runs"), settings=self.provider_settings)
        self._applying_agentic_specification = False
        self._build_ui()
        self._connect()
        self._collect_and_validate()
        gui_event("main_window_constructed")

    def _build_ui(self) -> None:
        toolbar = QToolBar("PGG")
        self.addToolBar(toolbar)
        toolbar.addAction("About", lambda: show_about(self))
        toolbar.addAction("Diagnostics", self._show_diagnostics)
        toolbar.addAction("Agent Provider Settings", self._show_provider_settings)
        toolbar.addAction("Open Output Folder", self.controller.open_output_folder)

        self.request_panel = RequestPanel()
        self.agentic_request_panel = AgenticRequestPanel()
        self.domain_panel = DomainPanel()
        self.structure_panel = StructurePanel()
        self.targets_panel = TargetsPanel()
        self.manufacturing_panel = ManufacturingPanel()
        self.generation_panel = GenerationPanel()
        left = QWidget()
        left.setMinimumWidth(430)
        left_layout = QVBoxLayout(left)
        for title, panel in (
            ("Request", self.request_panel),
            ("Agentic Request", self.agentic_request_panel),
            ("Domain", self.domain_panel),
            ("Structure", self.structure_panel),
            ("Targets and Constraints", self.targets_panel),
            ("Manufacturing", self.manufacturing_panel),
            ("Generation", self.generation_panel),
        ):
            left_layout.addWidget(group(title, panel))
        left_layout.addStretch()
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(450)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setWidget(left)

        self.preview_panel = PreviewPanel()

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.feasibility_panel = FeasibilityPanel()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("Ready")
        self.validation_panel = ValidationPanel()
        right_layout.addWidget(group("Feasibility", self.feasibility_panel))
        right_layout.addWidget(self.progress_label)
        right_layout.addWidget(self.progress_bar)
        right_layout.addWidget(self.validation_panel)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_scroll)
        splitter.addWidget(self.preview_panel)
        splitter.addWidget(right)
        splitter.setSizes([460, 620, 420])
        self.setCentralWidget(splitter)

        self.bottom_tabs = QTabWidget()
        self.logs_panel = LogsPanel()
        self.history_panel = RunHistoryPanel(self.history_store)
        self.tuning_text = QLabel("Tuning history appears after a run is opened.")
        self.sensitivity_text = QLabel("Sensitivity data appears after a sensitivity run.")
        self.bottom_tabs.addTab(self.history_panel, "Run History")
        self.bottom_tabs.addTab(self.logs_panel, "Logs")
        self.bottom_tabs.addTab(self.tuning_text, "Tuning History")
        self.bottom_tabs.addTab(self.sensitivity_text, "Sensitivity Data")
        dock = QDockWidget("Run Data", self)
        dock.setWidget(self.bottom_tabs)
        dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.history_panel.refresh(Path("runs"))

    def _connect(self) -> None:
        for panel in (self.request_panel, self.domain_panel, self.structure_panel, self.targets_panel, self.manufacturing_panel, self.generation_panel):
            panel.changed.connect(self._collect_and_validate)
            panel.changed.connect(self._mark_agentic_approval_stale)
        self.agentic_request_panel.parse_requested.connect(self._parse_agentic_request)
        self.agentic_request_panel.review_requested.connect(self._review_agentic_specification)
        self.request_panel.load_requested.connect(lambda: self.controller.load_specification(self))
        self.request_panel.save_requested.connect(lambda: self.controller.save_specification(self))
        self.request_panel.report_requested.connect(lambda: self.controller.export_report(self))
        self.generation_panel.estimate_requested.connect(self.controller.estimate)
        self.generation_panel.preview_requested.connect(self.controller.start_preview)
        self.generation_panel.final_requested.connect(lambda: self.controller.start_final(self))
        self.generation_panel.cancel_requested.connect(self.controller.cancel)
        self.controller.estimate_changed.connect(self.feasibility_panel.set_estimate)
        self.controller.estimate_changed.connect(self._estimate_changed)
        self.controller.validation_changed.connect(self.validation_panel.set_report)
        self.controller.preview_mesh_ready.connect(self.preview_panel.load_mesh)
        self.preview_panel.diagnostics_requested.connect(self._show_diagnostics)
        self.controller.run_completed.connect(self._run_completed)
        self.controller.log.connect(self.logs_panel.add_log)
        self.controller.busy_changed.connect(self._busy_changed)
        self.controller.issues_changed.connect(self._issues_changed)
        self.history_panel.open_run_requested.connect(self._open_run)
        self.history_panel.duplicate_requested.connect(self.controller.duplicate_run_specification)

    def _field_values(self) -> dict:
        data = {}
        for panel in (self.request_panel, self.domain_panel, self.structure_panel, self.targets_panel, self.generation_panel):
            data.update(panel.values())
        return data

    def _collect_and_validate(self) -> None:
        valid = self.controller.update_specification_from_fields(self._field_values())
        self.generation_panel.set_generation_enabled(valid)

    def _parse_agentic_request(self, request: str) -> None:
        request = request.strip()
        if not request:
            self.agentic_request_panel.set_result(None, "Request not parsed", self.agentic.provider_status)
            return
        gui_event("agentic_parse_requested", character_count=len(request))
        self.agentic_request_panel.set_busy(True)
        try:
            result = self.agentic.parse_request(request, self.controller.specification)
            self.agentic_request_panel.set_result(result, self.agentic.status.value, self.agentic.provider_status)
            self.log_panel_message("INFO", f"Agent-assisted request parsed with {len(result.extracted_fields)} proposed fields.")
        except Exception as exc:
            gui_event("agentic_parse_failed", error=str(exc))
            self.agentic_request_panel.set_result(None, "Parser failed", str(exc))
            self.controller.show_error("SPEC_INVALID", "Agent-assisted request parsing failed.", repr(exc))
        finally:
            self.agentic_request_panel.set_busy(False)

    def _review_agentic_specification(self) -> None:
        parsed = self.agentic.last_result
        if parsed is None:
            return
        mandatory = [item for item in parsed.ambiguities if item.mandatory and not item.resolved_choice]
        if mandatory:
            ambiguity_dialog = AmbiguityResolutionDialog(mandatory, self)
            if ambiguity_dialog.exec() == QDialog.Accepted:
                resolutions = ambiguity_dialog.resolutions()
                for item in parsed.ambiguities:
                    if item.identifier in resolutions:
                        item.resolved_choice = resolutions[item.identifier]
            else:
                return
        dialog = SpecificationReviewDialog(self.controller.specification, parsed, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            approved, record = self.agentic.approve(self.controller.specification, dialog.decisions())
            self._apply_specification_to_panels(approved)
            self.state.set_specification(approved)
            self._collect_and_validate()
            self.agentic_request_panel.set_result(parsed, self.agentic.status.value, self.agentic.provider_status)
            self.progress_label.setText("Human approved agent-assisted specification. Feasibility estimate running.")
            self.controller.estimate()
            gui_event("agentic_specification_approved", approval_id=record.approval_id)
        except Exception as exc:
            gui_event("agentic_approval_failed", error=str(exc))
            self.controller.show_error("SPEC_INVALID", "Approved agentic specification is invalid.", repr(exc))

    def _apply_specification_to_panels(self, spec) -> None:
        self._applying_agentic_specification = True
        try:
            self.request_panel.output_name.setText(spec.export.output_name)
            self.request_panel.output_directory.setText(spec.export.output_directory)
            self.request_panel.notes.setPlainText(spec.source_text)
            self.domain_panel.shape.setCurrentText(spec.domain.shape.value)
            if spec.domain.shape.value == "box":
                self.domain_panel.box_x.setValue(spec.domain.dimensions_mm[0])
                self.domain_panel.box_y.setValue(spec.domain.dimensions_mm[1])
                self.domain_panel.box_z.setValue(spec.domain.dimensions_mm[2])
            else:
                self.domain_panel.cyl_diameter.setValue(spec.domain.dimensions_mm[0])
                self.domain_panel.cyl_height.setValue(spec.domain.dimensions_mm[1])
            label = next((name for name, value in self.structure_panel.FAMILY_LABELS.items() if value == spec.structure.family.value), "SC")
            self.structure_panel.family.setCurrentText(label)
            if spec.structure.pore_diameter_mm is not None:
                self.structure_panel.pore_diameter.setValue(spec.structure.pore_diameter_mm)
            if spec.structure.unit_cell_size_mm is not None:
                self.structure_panel.unit_cell.setValue(spec.structure.unit_cell_size_mm)
            self.targets_panel.porosity.setValue(spec.targets.porosity_target.target)
            self.targets_panel.tolerance.setValue(spec.targets.porosity_target.tolerance)
            self.targets_panel.require_open.setChecked(spec.constraints.require_open_pores)
            self.targets_panel.single_solid.setChecked(spec.constraints.require_single_solid_component)
            self.generation_panel.preview_resolution.setValue(spec.generation.preview_resolution_mm)
            self.generation_panel.final_resolution.setValue(spec.generation.final_resolution_mm)
            self.generation_panel.reference_resolution.setValue(spec.generation.reference_resolution_mm)
            self.generation_panel.maximum_memory.setValue(spec.generation.maximum_memory_gb)
            self.generation_panel.maximum_runtime.setValue(spec.generation.maximum_runtime_s)
            self.manufacturing_panel.process.setText(spec.manufacturing.process)
            self.manufacturing_panel.printer.setText(spec.manufacturing.printer_profile)
            self.manufacturing_panel.minimum_feature.setValue(spec.manufacturing.minimum_printable_feature_mm)
        finally:
            self._applying_agentic_specification = False

    def _mark_agentic_approval_stale(self) -> None:
        if self._applying_agentic_specification:
            return
        if self.agentic.last_approval is not None:
            self.agentic.mark_approval_stale()
            self.agentic_request_panel.set_result(self.agentic.last_result, self.agentic.status.value, self.agentic.provider_status)

    def log_panel_message(self, level: str, message: str) -> None:
        self.logs_panel.add_log(level, message)

    def _issues_changed(self, issues) -> None:
        critical = [i for i in issues if getattr(i, "status", "") == "invalid"]
        self.progress_label.setText(critical[0].message if critical else "Specification ready")

    def _busy_changed(self, busy: bool) -> None:
        gui_event("busy_changed", busy=busy)
        self.progress_bar.setVisible(busy)
        self.generation_panel.set_busy(busy)
        self.progress_label.setText("Background operation running" if busy else "Ready")

    def _estimate_changed(self, estimate: dict) -> None:
        final_allowed = estimate.get("status") != "infeasible"
        self.generation_panel.set_generation_enabled(not self.controller.spec_model.has_invalid_fields, final_allowed)

    def _run_completed(self, payload: dict) -> None:
        gui_event("run_completed_ui", run_id=payload.get("run_id"), profile=payload.get("profile"))
        self.history_panel.refresh(Path("runs"))
        self.progress_label.setText(f"Run {payload.get('run_id')} completed")
        run_dir = Path(payload["run_dir"])
        tuning = run_dir / "tuning_history.csv"
        if tuning.exists():
            self.tuning_text.setText(tuning.read_text(encoding="utf-8")[:4000])

    def _open_run(self, run_dir: str) -> None:
        self.controller.last_run_dir = Path(run_dir)
        val = Path(run_dir) / "validation_report.json"
        if val.exists():
            self.validation_panel.set_report(json.loads(val.read_text(encoding="utf-8")))
        bb = Path(run_dir) / "blackboard.json"
        if bb.exists():
            data = json.loads(bb.read_text(encoding="utf-8"))
            stl = data.get("artifacts", {}).get("stl") or data.get("artifacts", {}).get("master_stl")
            artifact_state = "final" if data.get("artifacts", {}).get("master_stl") else "preview"
            self.preview_panel.load_mesh(stl, artifact_state=artifact_state, validation_status=str(data.get("status", "unknown")))
        self._run_details_dialog = RunDetailsDialog(run_dir, self)
        self._run_details_dialog.show()

    def _show_diagnostics(self) -> None:
        self._diagnostics_dialog = DiagnosticsDialog(runtime_diagnostics, self.preview_panel.rendering_diagnostics, self)
        self._diagnostics_dialog.show()
        self._diagnostics_dialog.raise_()
        self._diagnostics_dialog.activateWindow()

    def _show_provider_settings(self) -> None:
        dialog = ProviderSettingsDialog(self.provider_settings, self)
        dialog.settings_changed.connect(self._provider_settings_changed)
        dialog.exec()

    def _provider_settings_changed(self, settings: ProviderSettings) -> None:
        self.provider_settings = settings
        self.agentic.settings = settings
        self.agentic.provider = provider_from_settings(settings)
        self.agentic_request_panel.set_result(self.agentic.last_result, self.agentic.status.value, self.agentic.provider_status)

    def closeEvent(self, event) -> None:
        gui_event("main_window_close_requested")
        if self.controller.worker and self.controller.worker.is_running:
            self.controller.worker.cancel()
        self.preview_panel.close_viewer()
        gui_event("main_window_closed")
        super().closeEvent(event)
