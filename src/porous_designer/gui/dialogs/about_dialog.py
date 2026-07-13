"""About dialog for PGG."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from porous_designer import __version__


def show_about(parent=None) -> None:
    QMessageBox.about(
        parent,
        "About PGG",
        f"PGG, Porous Geometry Generation\nVersion {__version__}\n\n"
        "Deterministic local desktop GUI for porous-geometry research workflows.\n"
        "LLM assistance, STEP, FEA, inverse design, and cloud features are disabled in Phase 3A.",
    )
