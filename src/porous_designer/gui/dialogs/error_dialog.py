"""User-facing error dialog with technical details."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout


ERROR_MESSAGES = {
    "SPEC_INVALID": "One or more specification fields are invalid.",
    "MEMORY_ESTIMATE_EXCEEDED": "The requested geometry is estimated to exceed the configured memory limit.",
    "POROSITY_TARGET_UNREACHABLE": "The selected structure cannot reach the requested porosity.",
    "MESH_NOT_WATERTIGHT": "Final mesh validation failed. The STL was not accepted.",
    "PORE_CONNECTIVITY_FAILURE": "The generated pore space does not satisfy the connectivity constraint.",
    "USER_CANCELLED": "Generation was cancelled. Completed validated artifacts were preserved.",
}


class ErrorDialog(QDialog):
    def __init__(self, code: str, message: str = "", technical_details: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PGG Error")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(ERROR_MESSAGES.get(code, message or code)))
        if message and message != code:
            layout.addWidget(QLabel(message))
        details = QTextEdit()
        details.setReadOnly(True)
        details.setPlainText(technical_details or "No technical details were provided.")
        layout.addWidget(details)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
