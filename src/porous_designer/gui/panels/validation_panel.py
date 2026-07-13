"""Validation results panel."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTableView, QTextEdit, QVBoxLayout, QWidget

from porous_designer.gui.models.validation_table_model import ValidationTableModel


class ValidationPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Validation Results"))
        self.model = ValidationTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.table)
        layout.addWidget(self.details)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)

    def set_report(self, report) -> None:
        self.model.set_report(report)
        self.table.resizeColumnsToContents()

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
