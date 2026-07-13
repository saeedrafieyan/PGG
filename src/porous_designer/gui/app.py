"""PySide6 GUI entry point for PGG, Porous Geometry Generation."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is not installed. Install with: pip install porous-designer[gui]",
            file=sys.stderr,
        )
        return 1

    cache_dir = Path.cwd() / "runs" / ".gui_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")
    from porous_designer.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("PGG, Porous Geometry Generation")
    app.setOrganizationName("Federica Research Lab")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
