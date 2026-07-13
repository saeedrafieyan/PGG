"""Structured log display panel."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget


class LogsPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.level_filter = QComboBox()
        self.level_filter.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.copy_button = QPushButton("Copy")
        self.save_button = QPushButton("Save")
        top.addWidget(self.level_filter)
        top.addWidget(self.copy_button)
        top.addWidget(self.save_button)
        layout.addLayout(top)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        self._entries: list[tuple[str, str]] = []
        self.level_filter.currentTextChanged.connect(self._refresh)
        self.copy_button.clicked.connect(self.text.copy)

    def add_log(self, level: str, message: str) -> None:
        self._entries.append((level.upper(), message))
        self._refresh()

    def _refresh(self) -> None:
        selected = self.level_filter.currentText()
        lines = [f"[{level}] {msg}" for level, msg in self._entries if selected == "ALL" or level == selected]
        self.text.setPlainText("\n".join(lines))
