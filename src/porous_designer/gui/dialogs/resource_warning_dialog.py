"""Resource warning confirmation dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout


class ResourceWarningDialog(QDialog):
    def __init__(self, estimate: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resource Warning")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("The resource estimate requires confirmation before final generation."))
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n".join(f"{k}: {v}" for k, v in estimate.items()))
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
