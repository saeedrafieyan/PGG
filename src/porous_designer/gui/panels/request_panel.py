"""Request and specification file controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget


class RequestPanel(QWidget):
    changed = Signal()
    load_requested = Signal()
    save_requested = Signal()
    report_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.output_name = QLineEdit("pgg_scaffold")
        self.output_directory = QLineEdit("runs")
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Internal research notes")
        form.addRow("Output name", self.output_name)
        form.addRow("Output folder", self.output_directory)
        form.addRow("Request notes", self.notes)
        layout.addLayout(form)
        self.load_button = QPushButton("Load Spec")
        self.save_button = QPushButton("Save Spec")
        self.report_button = QPushButton("Export Report")
        layout.addWidget(self.load_button)
        layout.addWidget(self.save_button)
        layout.addWidget(self.report_button)
        self.load_button.clicked.connect(self.load_requested)
        self.save_button.clicked.connect(self.save_requested)
        self.report_button.clicked.connect(self.report_requested)
        for widget in (self.output_name, self.output_directory):
            widget.textChanged.connect(self.changed)
        self.notes.textChanged.connect(self.changed)

    def values(self) -> dict:
        return {
            "output_name": self.output_name.text().strip() or "pgg_scaffold",
            "output_directory": self.output_directory.text().strip() or "runs",
            "source_text": self.notes.toPlainText(),
        }
