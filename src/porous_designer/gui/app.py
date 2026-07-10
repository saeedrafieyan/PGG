"""PySide6 GUI entry point (Phase 5)."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        print(
            "PySide6 is not installed. Install with: pip install porous-designer[gui]",
            file=sys.stderr,
        )
        return 1

    app = QApplication(sys.argv)
    QMessageBox.information(
        None,
        "Porous Structure Designer",
        "GUI implementation is in progress (Phase 5).\n\n"
        "Use the CLI for now:\n  porous-designer sample_spec.txt",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
