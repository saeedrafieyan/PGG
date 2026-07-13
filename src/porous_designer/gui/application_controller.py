"""Application controller connecting GUI widgets to deterministic services."""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from porous_designer.domain.enums import FeasibilityStatus
from porous_designer.domain.specification import DesignSpecification
from porous_designer.gui.dialogs.error_dialog import ErrorDialog
from porous_designer.gui.dialogs.resource_warning_dialog import ResourceWarningDialog
from porous_designer.gui.diagnostics import gui_event
from porous_designer.gui.models.run_history_model import RunHistoryStore
from porous_designer.gui.models.specification_model import FieldIssue, SpecificationModel
from porous_designer.gui.reporting import generate_html_report
from porous_designer.gui.state_store import StateStore
from porous_designer.gui.workers.generation_worker import GenerationWorker
from porous_designer.gui.workers.preview_worker import PreviewWorker
from porous_designer.services.resource_estimation import estimate_resources


class ApplicationController(QObject):
    specification_changed = Signal(object)
    issues_changed = Signal(list)
    estimate_changed = Signal(dict)
    validation_changed = Signal(object)
    preview_mesh_ready = Signal(str)
    run_completed = Signal(dict)
    log = Signal(str, str)
    busy_changed = Signal(bool)

    def __init__(self, state: StateStore, history: RunHistoryStore, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.history = history
        self.spec_model = SpecificationModel(state.specification, self)
        self.worker: PreviewWorker | GenerationWorker | None = None
        self.last_estimate: dict | None = None
        self.last_run_dir: Path | None = None
        self.spec_model.changed.connect(self._specification_updated)
        self.spec_model.validation_changed.connect(self.issues_changed)
        gui_event("controller_constructed")

    @property
    def specification(self) -> DesignSpecification:
        return self.state.specification

    def update_specification_from_fields(self, data: dict) -> bool:
        spec = self.spec_model.update_from_fields(data)
        if spec is None:
            self.busy_changed.emit(False)
            return False
        self.state.set_specification(spec)
        return not self.spec_model.has_invalid_fields

    def _specification_updated(self, spec: DesignSpecification) -> None:
        self.specification_changed.emit(spec)

    def estimate(self) -> dict | None:
        gui_event("estimate_clicked")
        try:
            spec = self.state.specification
            estimate = estimate_resources(spec, spec.generation.final_resolution_mm).to_dict()
            self.last_estimate = estimate
            self.estimate_changed.emit(estimate)
            self.log.emit("INFO", f"Resource estimate: {estimate['status']} ({estimate['runtime_class']}).")
            gui_event("estimate_completed", status=estimate.get("status"), voxel_count=estimate.get("voxel_count"))
            return estimate
        except Exception as exc:
            gui_event("estimate_failed", error=str(exc))
            self.show_error("SPEC_INVALID", str(exc), repr(exc))
            return None

    def start_preview(self) -> None:
        gui_event("preview_clicked", active_worker=bool(self.worker and self.worker.is_running))
        if self.worker and self.worker.is_running:
            return
        self._start_worker(PreviewWorker(self.state.specification, self), "preview")

    def start_final(self, parent=None) -> None:
        gui_event("final_clicked")
        estimate = self.estimate()
        if not estimate:
            return
        if estimate["status"] == FeasibilityStatus.INFEASIBLE.value:
            self.show_error("MEMORY_ESTIMATE_EXCEEDED", estimate.get("message", ""), json.dumps(estimate, indent=2))
            return
        if estimate["status"] == FeasibilityStatus.CONDITIONALLY_FEASIBLE.value:
            if ResourceWarningDialog(estimate, parent).exec() != QDialog.Accepted:
                self.log.emit("WARNING", "Final generation cancelled before launch after resource warning.")
                return
        self._start_worker(GenerationWorker(self.state.specification, self), "final")

    def _start_worker(self, worker, label: str) -> None:
        self.worker = worker
        self.busy_changed.emit(True)
        self.log.emit("INFO", f"Starting {label} generation in a child process.")
        gui_event("worker_attached", worker_type=label)
        worker.progress.connect(lambda p: self.log.emit("INFO", f"{p.get('stage')}: {p.get('message')}"))
        worker.result.connect(self._worker_result)
        worker.error.connect(lambda e: self.show_error("SPEC_INVALID", e.get("message", ""), e.get("technical_details", "")))
        worker.cancelled.connect(lambda c: self.log.emit("WARNING", c.get("message", "Cancelled.")))
        worker.finished.connect(lambda: self.busy_changed.emit(False))
        worker.start()

    def cancel(self) -> None:
        gui_event("cancel_clicked", active_worker=bool(self.worker and self.worker.is_running))
        if self.worker and self.worker.is_running:
            self.worker.cancel()
            self.log.emit("WARNING", "Cancellation requested.")

    def _worker_result(self, payload: dict) -> None:
        self.last_run_dir = Path(payload["run_dir"])
        gui_event("worker_result_handling", run_id=payload.get("run_id"), profile=payload.get("profile"))
        self.history.upsert_from_run_dir(self.last_run_dir)
        validation_path = Path(payload.get("validation_report_path", ""))
        if validation_path.exists():
            self.validation_changed.emit(json.loads(validation_path.read_text(encoding="utf-8")))
        if payload.get("profile") == "preview" and payload.get("stl_path"):
            self.preview_mesh_ready.emit(payload["stl_path"])
        self.run_completed.emit(payload)
        self.log.emit("INFO", f"{payload.get('profile', 'generation')} completed: run {payload.get('run_id')}.")

    def load_specification(self, parent=None) -> None:
        path, _ = QFileDialog.getOpenFileName(parent, "Load PGG specification", "", "YAML (*.yaml *.yml)")
        if path:
            try:
                spec = self.state.load_specification(path)
                self.spec_model = SpecificationModel(spec, self)
                self.spec_model.changed.connect(self._specification_updated)
                self.spec_model.validation_changed.connect(self.issues_changed)
                self.specification_changed.emit(spec)
                self.log.emit("INFO", f"Loaded specification {path}.")
            except Exception as exc:
                self.show_error("SPEC_INVALID", str(exc), repr(exc))

    def save_specification(self, parent=None) -> None:
        path, _ = QFileDialog.getSaveFileName(parent, "Save PGG specification", "pgg_specification.yaml", "YAML (*.yaml *.yml)")
        if path:
            self.state.save_specification(path)
            self.log.emit("INFO", f"Saved specification {path}.")

    def duplicate_run_specification(self, run_dir: str) -> None:
        spec_path = Path(run_dir) / "approved_specification.yaml"
        if spec_path.exists():
            spec = self.state.load_specification(spec_path)
            self.spec_model = SpecificationModel(spec, self)
            self.spec_model.changed.connect(self._specification_updated)
            self.spec_model.validation_changed.connect(self.issues_changed)
            self.specification_changed.emit(spec)
            self.log.emit("INFO", f"Duplicated specification from run {run_dir}.")

    def export_report(self, parent=None) -> Path | None:
        if not self.last_run_dir:
            QMessageBox.information(parent, "No Run", "Generate or open a run before exporting a report.")
            return None
        report = generate_html_report(self.last_run_dir)
        self.log.emit("INFO", f"HTML report exported: {report}.")
        return report

    def open_output_folder(self) -> None:
        if self.last_run_dir:
            os.startfile(str(self.last_run_dir))

    def show_error(self, code: str, message: str, technical_details: str = "") -> None:
        gui_event("user_error_displayed", code=code, message=message)
        self.log.emit("ERROR", message or code)
        ErrorDialog(code, message, technical_details).exec()
