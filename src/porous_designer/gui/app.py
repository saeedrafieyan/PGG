"""PySide6 GUI entry point for PGG, Porous Geometry Generation."""

from __future__ import annotations

import os
import sys
import argparse
import multiprocessing as mp
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="porous-designer-gui")
    parser.add_argument("--debug-gui", action="store_true", help="write structured GUI runtime diagnostics")
    args, qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is not installed. Install with: pip install porous-designer[gui]",
            file=sys.stderr,
        )
        return 1

    from porous_designer.paths import runs_dir

    cache_dir = runs_dir() / ".gui_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    from porous_designer.gui.diagnostics import configure_gui_logging, gui_event

    log_path = configure_gui_logging(debug=args.debug_gui)
    gui_event("app_start", argv=qt_args, log_path=str(log_path))
    from porous_designer.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([sys.argv[0], *qt_args])
    gui_event("qapplication_ready", top_level_widgets=len(QApplication.topLevelWidgets()))
    app.setApplicationName("PGG, Porous Geometry Generation")
    app.setOrganizationName("Federica Research Lab")
    window = MainWindow()
    window.show()
    gui_event("main_window_shown", top_level_widgets=len(QApplication.topLevelWidgets()))
    code = app.exec()
    gui_event("app_shutdown", exit_code=code)
    return code


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
