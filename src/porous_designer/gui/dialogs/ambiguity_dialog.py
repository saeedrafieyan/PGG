"""Structured ambiguity confirmation dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout


class AmbiguityDialog(QDialog):
    def __init__(self, message: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review Specification")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(message))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
