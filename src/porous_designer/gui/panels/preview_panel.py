"""Interactive preview viewer with PyVistaQt fallback."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget


class PreviewPanel(QWidget):
    screenshot_saved = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.reset_button = QPushButton("Reset Camera")
        self.iso_button = QPushButton("Isometric")
        self.front_button = QPushButton("Front")
        self.side_button = QPushButton("Side")
        self.top_button = QPushButton("Top")
        self.wireframe = QCheckBox("Wireframe")
        self.surface = QCheckBox("Surface")
        self.surface.setChecked(True)
        self.bbox = QCheckBox("Bounding box")
        self.axes = QCheckBox("Axes")
        self.axes.setChecked(True)
        self.screenshot_button = QPushButton("Screenshot")
        for widget in (self.reset_button, self.iso_button, self.front_button, self.side_button, self.top_button, self.wireframe, self.surface, self.bbox, self.axes, self.screenshot_button):
            controls.addWidget(widget)
        layout.addLayout(controls)
        clip = QHBoxLayout()
        self.clip_x = QCheckBox("Clip X")
        self.clip_y = QCheckBox("Clip Y")
        self.clip_z = QCheckBox("Clip Z")
        self.invert_clip = QCheckBox("Invert")
        self.slice_visible = QCheckBox("Slice")
        self.slice_slider = QSlider(Qt.Horizontal)
        self.slice_slider.setRange(0, 100)
        self.reset_clip = QPushButton("Reset Clip")
        for widget in (self.clip_x, self.clip_y, self.clip_z, self.invert_clip, self.slice_visible, self.slice_slider, self.reset_clip):
            clip.addWidget(widget)
        layout.addLayout(clip)
        self.status = QLabel("Preview only, not final validation")
        layout.addWidget(self.status)
        self._plotter = None
        self._mesh_actor = None
        self._mesh_path: Path | None = None
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self.viewer = QLabel("3D viewer disabled in offscreen test mode.")
            self.viewer.setMinimumHeight(360)
            self.viewer.setAlignment(Qt.AlignCenter)
        else:
            try:
                from pyvistaqt import QtInteractor

                self.viewer = QtInteractor(self)
                self._plotter = self.viewer
                self._plotter.add_axes()
            except Exception as exc:
                self.viewer = QLabel(f"PyVista viewer unavailable: {exc}")
                self.viewer.setMinimumHeight(360)
                self.viewer.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.viewer)
        self.reset_button.clicked.connect(self.reset_camera)
        self.iso_button.clicked.connect(lambda: self.view("iso"))
        self.front_button.clicked.connect(lambda: self.view("front"))
        self.side_button.clicked.connect(lambda: self.view("side"))
        self.top_button.clicked.connect(lambda: self.view("top"))
        self.wireframe.toggled.connect(self._refresh_representation)
        self.surface.toggled.connect(self._refresh_representation)
        self.screenshot_button.clicked.connect(self.save_screenshot)

    def load_mesh(self, path: str | Path | None) -> None:
        if not path:
            return
        self._mesh_path = Path(path)
        if self._plotter is None:
            self.status.setText(f"Preview mesh ready: {self._mesh_path.name}")
            return
        import pyvista as pv

        self._plotter.clear()
        mesh = pv.read(str(self._mesh_path))
        style = "wireframe" if self.wireframe.isChecked() and not self.surface.isChecked() else "surface"
        self._mesh_actor = self._plotter.add_mesh(mesh, style=style, show_edges=self.wireframe.isChecked())
        if self.bbox.isChecked():
            self._plotter.add_bounding_box()
        if self.axes.isChecked():
            self._plotter.add_axes()
        self._plotter.reset_camera()
        self.status.setText(f"Preview mesh loaded: {self._mesh_path.name}")

    def reset_camera(self) -> None:
        if self._plotter:
            self._plotter.reset_camera()

    def view(self, name: str) -> None:
        if not self._plotter:
            return
        if name == "iso":
            self._plotter.view_isometric()
        elif name == "front":
            self._plotter.view_yz()
        elif name == "side":
            self._plotter.view_xz()
        elif name == "top":
            self._plotter.view_xy()

    def _refresh_representation(self) -> None:
        if self._mesh_path:
            self.load_mesh(self._mesh_path)

    def save_screenshot(self) -> None:
        target = Path("runs") / "pgg_preview_screenshot.png"
        target.parent.mkdir(exist_ok=True)
        if self._plotter:
            self._plotter.screenshot(str(target))
        else:
            target.write_text("Screenshot unavailable in fallback viewer.", encoding="utf-8")
        self.screenshot_saved.emit(str(target))
