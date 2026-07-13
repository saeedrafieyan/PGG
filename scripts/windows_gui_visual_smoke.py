"""Manual visual smoke helper for PGG preview rendering.

Run from the repository root on a Windows desktop session:

    python scripts/windows_gui_visual_smoke.py --family gyroid --output docs/phase_3a2_before_gyroid.png
"""

from __future__ import annotations

import argparse
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


def make_spec(family: str, output_dir: str, output_name: str) -> DesignSpecification:
    enum = StructureFamily(family)
    structure = (
        StructureSpec(family=enum, unit_cell_size_mm=1.5)
        if enum.is_tpms
        else StructureSpec(family=enum, pore_diameter_mm=0.8)
    )
    return DesignSpecification(
        domain=DomainSpec(shape=DomainShape.BOX, dimensions_mm=[4.0, 4.0, 4.0]),
        structure=structure,
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.55, tolerance=0.18)),
        constraints=ConstraintsSpec(require_open_pores=False, require_single_solid_component=False),
        generation=GenerationSpec(preview_resolution_mm=0.4, final_resolution_mm=0.4, maximum_memory_gb=4.0),
        export=ExportSpec(output_directory=output_dir, output_name=output_name),
    )


class VisualSmoke:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.window = MainWindow()
        self.failed: str | None = None
        self.window.controller.run_completed.connect(self._preview_complete)
        self.window.controller.log.connect(lambda level, msg: print(f"[{level}] {msg}"))

    def run(self) -> int:
        configure_gui_logging(debug=True)
        gui_event("windows_visual_smoke_start", family=self.args.family, preset=self.args.preset)
        self.window.show()
        spec = make_spec(self.args.family, "runs", self.args.output_name)
        self.window.controller.state.set_specification(spec)
        self.window.preview_panel.apply_preset(self.args.preset)
        QTimer.singleShot(250, self.window.controller.estimate)
        QTimer.singleShot(750, self.window.controller.start_preview)
        QTimer.singleShot(self.args.timeout_ms, self._timeout)
        code = self.app.exec()
        if self.failed:
            print(f"VISUAL SMOKE FAILED: {self.failed}", file=sys.stderr)
            return 1
        return code

    def _preview_complete(self, payload: dict) -> None:
        if payload.get("profile") != "preview":
            return
        target = Path(self.args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        if self.window.preview_panel._plotter is not None:
            self.window.preview_panel._plotter.screenshot(str(target))
        else:
            self.failed = "PyVistaQt renderer was unavailable."
        actor_count = self.window.preview_panel.actor_count()
        print(
            f"Visual smoke complete family={self.args.family} actors={actor_count} "
            f"preset={self.args.preset} screenshot={target} child_pid={payload.get('child_pid')}"
        )
        self.window.close()
        self.app.quit()

    def _timeout(self) -> None:
        self.failed = "Visual smoke timed out."
        self.window.close()
        self.app.quit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", default="gyroid", choices=[f.value for f in StructureFamily])
    parser.add_argument("--output", default="docs/phase_3a2_visual_smoke.png")
    parser.add_argument("--output-name", default="visual_smoke")
    parser.add_argument("--preset", default="Scientific")
    parser.add_argument("--timeout-ms", type=int, default=60000)
    args = parser.parse_args(argv)
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        print("WARNING: QT_QPA_PLATFORM=offscreen; this is not the full interactive rendering path.")
    return VisualSmoke(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
