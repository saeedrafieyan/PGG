"""Run details dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextEdit, QVBoxLayout


class RunDetailsDialog(QDialog):
    def __init__(self, run_dir: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run Details")
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        path = Path(run_dir)
        parts = [f"Run directory: {path}"]
        for name in ("approved_specification.yaml", "blackboard.json", "validation_report.json", "timing.json"):
            file = path / name
            if file.exists():
                parts.append(f"\n--- {name} ---\n{file.read_text(encoding='utf-8')[:6000]}")
        text.setPlainText("\n".join(parts))
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
