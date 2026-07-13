"""Interactive Windows smoke test for the real PGG GUI.

This script intentionally does not force QT_QPA_PLATFORM=offscreen. Run it from
the repository root on a Windows desktop session:

    python scripts/windows_gui_smoke.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from porous_designer.domain.enums import DomainShape, StructureFamily
from porous_designer.domain.specification import (
    ConstraintsSpec,
    DesignSpecification,
    DomainSpec,
    ExportSpec,
    GenerationSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
)
from porous_designer.gui.diagnostics import configure_gui_logging, gui_event
from porous_designer.gui.main_window import MainWindow


def small_spec() -> DesignSpecification:
    return DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[2.5, 2.5, 2.5]),
        structure=StructureSpec(family=StructureFamily.SC_SPHERICAL_PORES, pore_diameter_mm=0.8),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.45, tolerance=0.2)),
        constraints=ConstraintsSpec(require_open_pores=False, require_single_solid_component=False),
        generation=GenerationSpec(preview_resolution_mm=0.5, final_resolution_mm=0.5, maximum_memory_gb=4.0),
        export=ExportSpec(output_directory="runs", output_name="windows_gui_smoke"),
    )


class Smoke:
    def __init__(self) -> None:
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.window = MainWindow()
        self.done = False
        self.failed: str | None = None
        self.window.controller.run_completed.connect(self._preview_complete)
        self.window.controller.log.connect(lambda level, msg: print(f"[{level}] {msg}"))

    def run(self) -> int:
        configure_gui_logging(debug=True)
        gui_event("windows_smoke_start")
        self.window.show()
        self.window.controller.state.set_specification(small_spec())
        QTimer.singleShot(250, self._estimate)
        QTimer.singleShot(750, self._preview)
        QTimer.singleShot(60000, self._timeout)
        code = self.app.exec()
        if self.failed:
            print(f"SMOKE FAILED: {self.failed}", file=sys.stderr)
            return 1
        return code

    def _estimate(self) -> None:
        estimate = self.window.controller.estimate()
        if not estimate or not self.window.feasibility_panel.status.text():
            self.failed = "Estimate did not populate the resource panel."
            self.app.quit()
            return
        print(f"Estimate status: {estimate['status']} grid={estimate['grid_shape']}")

    def _preview(self) -> None:
        before = len(QApplication.topLevelWidgets())
        self.window.controller.start_preview()
        after = len(QApplication.topLevelWidgets())
        if after > before:
            self.failed = f"Preview created a new top-level widget: before={before} after={after}"
            self.app.quit()

    def _preview_complete(self, payload: dict) -> None:
        if payload.get("profile") != "preview":
            return
        path = Path(payload.get("stl_path") or "")
        if not path.exists():
            self.failed = f"Preview STL missing: {path}"
            self.app.quit()
            return
        actor_count = self.window.preview_panel.actor_count()
        if self.window.preview_panel._plotter is not None and actor_count < 1:
            self.failed = "Preview renderer has no actors."
            self.app.quit()
            return
        screenshot = Path("runs") / "windows_gui_smoke.png"
        if self.window.preview_panel._plotter is not None:
            self.window.preview_panel._plotter.screenshot(str(screenshot))
            if not screenshot.exists() or screenshot.stat().st_size < 1000:
                self.failed = "Preview screenshot was empty or missing."
                self.app.quit()
                return
        print(
            f"Preview complete: {path} actors={actor_count} "
            f"gui_pid={os.getpid()} child_pid={payload.get('child_pid')} exit={payload.get('exit_code')}"
        )
        self.window.close()
        self.app.quit()

    def _timeout(self) -> None:
        self.failed = "Smoke test timed out."
        self.window.close()
        self.app.quit()


if __name__ == "__main__":
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        print("WARNING: QT_QPA_PLATFORM=offscreen; this is not the full interactive smoke path.")
    raise SystemExit(Smoke().run())
