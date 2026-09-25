"""Simple mode (Phase 4.4): Describe -> Review -> Download.

One text box, a process/printer choice and a card. The card and all logic
come from ``services.design_session`` (shared with the web front end); this
window only lays them out. *Advanced mode* opens the full engineering
window with every parameter.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from porous_designer.services.design_session import DesignSession, render_card_html

PLACEHOLDER = "e.g. Bone scaffold, 10 x 10 x 10 mm cube, gyroid, 70% porosity, for my resin printer"


class SimpleWindow(QMainWindow):
    def __init__(self, parent=None, *, preview: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("AGE Designer")
        self.resize(1200, 780)
        self.session: DesignSession | None = None
        self.worker = None
        self.files: dict[str, str] = {}
        self._advanced = None

        central = QWidget()
        outer = QVBoxLayout(central)
        self.steps = QLabel()
        outer.addWidget(self.steps)

        self.request = QPlainTextEdit()
        self.request.setPlaceholderText(PLACEHOLDER)
        self.request.setMaximumHeight(90)
        outer.addWidget(self.request)

        row = QHBoxLayout()
        self.process = QComboBox()
        self.printer = QComboBox()
        self._fill_processes()
        self.process.currentIndexChanged.connect(self._fill_printers)
        self.propose_button = QPushButton("Propose design")
        self.propose_button.clicked.connect(self.propose)
        self.advanced_button = QPushButton("Advanced mode...")
        self.advanced_button.clicked.connect(self.open_advanced)
        row.addWidget(QLabel("Process"))
        row.addWidget(self.process)
        row.addWidget(QLabel("Printer"))
        row.addWidget(self.printer, 1)
        row.addWidget(self.propose_button)
        row.addWidget(self.advanced_button)
        outer.addLayout(row)

        split = QSplitter(Qt.Horizontal)
        self.card = QTextBrowser()
        self.card.setOpenExternalLinks(True)
        split.addWidget(self.card)
        self.preview = None
        if preview:
            try:
                from porous_designer.gui.panels.preview_panel import PreviewPanel

                self.preview = PreviewPanel()
                split.addWidget(self.preview)
                split.setSizes([560, 640])
            except Exception:  # no OpenGL: the card alone still works
                self.preview = None
        outer.addWidget(split, 1)

        actions = QHBoxLayout()
        self.status = QLabel("")
        self.approve_button = QPushButton("Approve and generate")
        self.approve_button.clicked.connect(self.approve)
        self.download_buttons = {}
        actions.addWidget(self.status, 1)
        actions.addWidget(self.approve_button)
        for kind, label in (("stl", "Save STL"), ("3mf", "Save 3MF"), ("report", "Save report")):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, k=kind: self.save(k))
            self.download_buttons[kind] = b
            actions.addWidget(b)
        outer.addLayout(actions)
        self.setCentralWidget(central)
        self._set_step(1)

    # -- selectors ----------------------------------------------------------------
    def _fill_processes(self) -> None:
        from porous_designer.printability.profiles import all_profiles

        self._profiles = sorted(all_profiles().values(), key=lambda p: (p.process, p.id))
        self.process.addItem("from the text", "")
        for proc in sorted({p.process for p in self._profiles}):
            self.process.addItem(proc, proc)
        self._fill_printers()

    def _fill_printers(self) -> None:
        proc = self.process.currentData() or ""
        self.printer.clear()
        self.printer.addItem("generic for the process", "")
        for p in self._profiles:
            if not proc or p.process == proc:
                self.printer.addItem((p.display_name or p.id) + (" (calibrated)" if p.calibrated else ""), p.id)

    def _set_step(self, n: int) -> None:
        names = ["1 Describe", "2 Review", "3 Download"]
        self.steps.setText("  ›  ".join(f"<b>{s}</b>" if i + 1 == n else s for i, s in enumerate(names)))
        self.approve_button.setEnabled(n == 2 and self.session is not None and self.session.state == "proposed")
        for kind, b in self.download_buttons.items():
            b.setEnabled(n == 3 and kind in self.files)

    # -- steps ----------------------------------------------------------------------
    def propose(self) -> None:
        text = self.request.toPlainText().strip()
        if not text:
            return
        self.files = {}
        self.session = DesignSession()
        try:
            card = self.session.propose(text, process=self.process.currentData() or None, printer=self.printer.currentData() or None)
        except Exception as exc:
            QMessageBox.critical(self, "AGE", f"Could not read the request:\n{exc}")
            return
        self.card.setHtml(render_card_html(card))
        self.status.setText("Review the design; nothing has been generated yet." if self.session.state == "proposed" else "Not printable as stated; see the alternatives.")
        self._set_step(2)

    def approve(self) -> None:
        from porous_designer.gui.workers.design_worker import DesignWorker

        if self.session is None or self.session.state != "proposed":
            return
        self.approve_button.setEnabled(False)
        self.propose_button.setEnabled(False)
        self.status.setText("Generating...")
        self.worker = DesignWorker(self.session.snapshot(), parent=self)
        self.worker.progress.connect(lambda p: self.status.setText(p.get("message", "")))
        self.worker.result.connect(self._done)
        self.worker.error.connect(self._failed)
        self.worker.finished.connect(lambda: self.propose_button.setEnabled(True))
        self.worker.start()

    def _done(self, payload: dict) -> None:
        self.files = payload.get("files", {})
        self.session.state = "done"
        self.card.setHtml(render_card_html(payload["proposal_card"]) + "<hr>" + render_card_html(payload["result_card"]))
        self.status.setText(payload["result_card"]["headline"])
        if self.preview is not None and self.files.get("stl"):
            try:
                self.preview.load_mesh(self.files["stl"], artifact_state="final", validation_status=payload.get("status", ""))
            except Exception:
                pass
        self._set_step(3)

    def _failed(self, payload: dict) -> None:
        self.status.setText("Generation failed.")
        QMessageBox.critical(self, "AGE", payload.get("message", "Generation failed."))
        self.propose_button.setEnabled(True)

    def save(self, kind: str) -> None:
        src = self.files.get(kind)
        if not src:
            return
        suffix = Path(src).suffix
        dest, _ = QFileDialog.getSaveFileName(self, f"Save {kind.upper()}", str(Path.home() / Path(src).name), f"*{suffix}")
        if dest:
            shutil.copyfile(src, dest)
            self.status.setText(f"Saved {dest}")

    def open_advanced(self) -> None:
        from porous_designer.gui.main_window import MainWindow

        if self._advanced is None:
            self._advanced = MainWindow()
        self._advanced.show()
        self._advanced.raise_()
