"""Run history panel."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTableView, QVBoxLayout, QWidget

from porous_designer.gui.models.run_history_model import RunHistoryModel, RunHistoryStore


class RunHistoryPanel(QWidget):
    open_run_requested = Signal(str)
    duplicate_requested = Signal(str)

    def __init__(self, store: RunHistoryStore, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        layout = QVBoxLayout(self)
        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.open_button = QPushButton("Open Run")
        self.duplicate_button = QPushButton("Duplicate Spec")
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.open_button)
        actions.addWidget(self.duplicate_button)
        layout.addLayout(actions)
        self.model = RunHistoryModel(parent=self)
        self.table = QTableView()
        self.table.setModel(self.model)
        layout.addWidget(self.table)
        self.refresh_button.clicked.connect(lambda: self.refresh(Path("runs")))
        self.open_button.clicked.connect(self._open_selected)
        self.duplicate_button.clicked.connect(self._duplicate_selected)

    def refresh(self, root: Path) -> None:
        self.store.scan_runs(root)
        self.model.set_records(self.store.list_records())
        self.table.resizeColumnsToContents()

    def _selected_record(self):
        rows = self.table.selectionModel().selectedRows()
        return self.model.record(rows[0].row()) if rows else None

    def _open_selected(self) -> None:
        rec = self._selected_record()
        if rec:
            self.open_run_requested.emit(rec.output_folder)

    def _duplicate_selected(self) -> None:
        rec = self._selected_record()
        if rec:
            self.duplicate_requested.emit(rec.output_folder)
