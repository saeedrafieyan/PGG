"""Runtime and rendering diagnostics dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Any

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from porous_designer.gui.diagnostics import gui_event
from porous_designer.gui.rendering import rendering_diagnostics_text


class DiagnosticsDialog(QDialog):
    def __init__(self, runtime_text: Callable[[], str], rendering_model: Callable[[], dict[str, Any]], parent=None) -> None:
        super().__init__(parent)
        self._runtime_text = runtime_text
        self._rendering_model = rendering_model
        self.setWindowTitle("PGG Diagnostics")
        self.resize(760, 640)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.runtime_text = QPlainTextEdit()
        self.runtime_text.setReadOnly(True)
        self.runtime_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.tabs.addTab(self.runtime_text, "Runtime")

        rendering_tab = QWidget()
        rendering_layout = QVBoxLayout(rendering_tab)
        self.rendering_summary = QPlainTextEdit()
        self.rendering_summary.setReadOnly(True)
        self.rendering_summary.setLineWrapMode(QPlainTextEdit.NoWrap)
        rendering_layout.addWidget(self.rendering_summary, 1)

        self.extensions_group = QGroupBox("OpenGL Extensions")
        self.extensions_group.setCheckable(True)
        self.extensions_group.setChecked(False)
        extensions_layout = QVBoxLayout(self.extensions_group)
        self.extensions_text = QPlainTextEdit()
        self.extensions_text.setReadOnly(True)
        self.extensions_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.extensions_text.setStyleSheet("font-family: Consolas, 'Courier New', monospace;")
        self.extensions_text.setMaximumHeight(170)
        extensions_layout.addWidget(self.extensions_text)
        self.extensions_text.setVisible(False)
        self.extensions_group.toggled.connect(self.extensions_text.setVisible)
        rendering_layout.addWidget(self.extensions_group)
        self.tabs.addTab(rendering_tab, "Rendering")
        layout.addWidget(self.tabs)

        self.path_label = QLabel("")
        layout.addWidget(self.path_label)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy Rendering Diagnostics")
        self.save_button = QPushButton("Save Diagnostics")
        self.refresh_button = QPushButton("Refresh")
        self.close_button = QPushButton("Close")
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.save_button)
        buttons.addStretch()
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.copy_button.clicked.connect(self.copy_rendering_diagnostics)
        self.save_button.clicked.connect(self.save_diagnostics)
        self.refresh_button.clicked.connect(self.refresh)
        self.close_button.clicked.connect(self.close)

    def refresh(self) -> None:
        model = self._rendering_model()
        self.runtime_text.setPlainText(self._runtime_text())
        self.rendering_summary.setPlainText(self._summary_text(model))
        extensions = model.get("opengl", {}).get("extensions") or []
        self.extensions_text.setPlainText("\n".join(str(item) for item in extensions))
        self.path_label.clear()
        gui_event(
            "rendering_diagnostics_refreshed",
            preset=model.get("preset"),
            fallback=model.get("features", {}).get("fallback"),
            opengl_extension_count=len(extensions),
        )

    def copy_rendering_diagnostics(self) -> None:
        text = self._full_rendering_text()
        QApplication.clipboard().setText(text)
        gui_event("rendering_diagnostics_copied", character_count=len(text))

    def save_diagnostics(self) -> Path | None:
        path, _ = QFileDialog.getSaveFileName(self, "Save diagnostics", "pgg_rendering_diagnostics.txt", "Text (*.txt)")
        if not path:
            return None
        target = Path(path)
        target.write_text(self._full_diagnostics_text(), encoding="utf-8")
        self.path_label.setText(f"Saved: {target}")
        gui_event("rendering_diagnostics_saved", path=str(target))
        return target

    def _summary_text(self, model: dict[str, Any]) -> str:
        text = rendering_diagnostics_text(model)
        marker = "\n[OpenGL extensions]"
        return text.split(marker, 1)[0].rstrip()

    def _full_rendering_text(self) -> str:
        return rendering_diagnostics_text(self._rendering_model())

    def _full_diagnostics_text(self) -> str:
        return f"[Runtime]\n{self._runtime_text()}\n\n[Rendering]\n{self._full_rendering_text()}\n"
