"""Validation results panel."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTableView, QTextEdit, QVBoxLayout, QWidget
from PySide6.QtWidgets import QHeaderView

from porous_designer.gui.models.validation_table_model import ValidationTableModel


class ValidationPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        actions = QHBoxLayout()
        actions.addWidget(QLabel("Validation Results"))
        self.copy_button = QPushButton("Copy Row")
        self.export_button = QPushButton("Export CSV")
        actions.addWidget(self.copy_button)
        actions.addWidget(self.export_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.model = ValidationTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 210)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 240)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.table)
        layout.addWidget(self.details)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.copy_button.clicked.connect(self.copy_selected_row)
        self.export_button.clicked.connect(self.export_csv)

    def set_report(self, report) -> None:
        self.model.set_report(report)
        self.table.resizeRowsToContents()

    def _selection_changed(self) -> None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        details = self.model.row_details(row)
        self.details.setPlainText(
            f"Method: {details.get('method', '')}\n"
            f"Severity: {details.get('severity', '')}\n"
            f"Message: {details.get('message', '')}\n"
            f"Suggested action: inspect related run artifacts when status is WARNING or FAIL."
        )

    def copy_selected_row(self) -> None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return
        row = self.model.row_details(indexes[0].row())
        QGuiApplication.clipboard().setText(str(row))

    def export_csv(self) -> None:
        target = Path("runs") / "validation_table.csv"
        target.parent.mkdir(exist_ok=True)
        target.write_text(self.model.rows_as_csv(), encoding="utf-8")
