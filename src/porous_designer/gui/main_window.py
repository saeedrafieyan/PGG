"""Main window for PGG, Porous Geometry Generation."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

from porous_designer.gui.application_controller import ApplicationController
from porous_designer.gui.dialogs.about_dialog import show_about
from porous_designer.gui.dialogs.diagnostics_dialog import DiagnosticsDialog
from porous_designer.gui.dialogs.run_details_dialog import RunDetailsDialog
from porous_designer.gui.diagnostics import gui_event, runtime_diagnostics
from porous_designer.gui.models.run_history_model import RunHistoryStore
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
        self._build_ui()
        self._connect()
        self._collect_and_validate()
        gui_event("main_window_constructed")

    def _build_ui(self) -> None:
        toolbar = QToolBar("PGG")
        self.addToolBar(toolbar)
        toolbar.addAction("About", lambda: show_about(self))
        toolbar.addAction("Diagnostics", self._show_diagnostics)
        toolbar.addAction("Open Output Folder", self.controller.open_output_folder)

        self.request_panel = RequestPanel()
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

    def closeEvent(self, event) -> None:
        gui_event("main_window_close_requested")
        if self.controller.worker and self.controller.worker.is_running:
            self.controller.worker.cancel()
        self.preview_panel.close_viewer()
        gui_event("main_window_closed")
        super().closeEvent(event)
