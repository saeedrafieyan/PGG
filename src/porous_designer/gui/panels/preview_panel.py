"""Interactive scientific preview viewer with PyVistaQt fallback."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from porous_designer.gui.diagnostics import gui_event
from porous_designer.gui.rendering import (
    PRESETS,
    RenderingSettings,
    load_rendering_settings,
    preset,
    rendering_diagnostics,
    save_rendering_settings,
)


class PreviewPanel(QWidget):
    screenshot_saved = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.settings = load_rendering_settings()
        self.capabilities: dict[str, Any] = {
            "ambient_occlusion": False,
            "anti_aliasing": "none",
            "depth_peeling": False,
            "opengl_renderer": "unknown",
            "fallback": False,
        }
        self._plotter = None
        self._mesh_actor = None
        self._slice_actor = None
        self._display_mesh = None
        self._loaded_mesh = None
        self._mesh_path: Path | None = None
        self._last_timings: dict[str, float] = {}
        self._build_ui()
        self._init_viewer()
        self._connect()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        controls = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(PRESETS.keys())
        self.preset_combo.setCurrentText(self.settings.preset)
        self.mesh_color_button = QPushButton("Mesh Color")
        self.background_color_button = QPushButton("Background")
        self.edge_color_button = QPushButton("Edge Color")
        self.reset_rendering_button = QPushButton("Reset Rendering")
        self.reset_button = QPushButton("Reset Camera")
        self.fit_button = QPushButton("Fit to View")
        self.iso_button = QPushButton("Isometric")
        self.front_button = QPushButton("Front")
        self.side_button = QPushButton("Side")
        self.top_button = QPushButton("Top")
        for widget in (
            self.preset_combo,
            self.mesh_color_button,
            self.background_color_button,
            self.edge_color_button,
            self.reset_rendering_button,
            self.reset_button,
            self.fit_button,
            self.iso_button,
            self.front_button,
            self.side_button,
            self.top_button,
        ):
            controls.addWidget(widget)
        layout.addLayout(controls)

        display = QHBoxLayout()
        self.smooth = QCheckBox("Smooth")
        self.smooth.setChecked(self.settings.smooth_shading)
        self.edges = QCheckBox("Edges")
        self.edges.setChecked(self.settings.show_edges)
        self.bbox = QCheckBox("Bounding box")
        self.bbox.setChecked(self.settings.show_bounding_box)
        self.axes = QCheckBox("Axes")
        self.axes.setChecked(self.settings.show_axes)
        self.perspective = QCheckBox("Perspective")
        self.perspective.setChecked(self.settings.perspective)
        self.ambient_occlusion = QCheckBox("Ambient occlusion")
        self.ambient_occlusion.setChecked(self.settings.ambient_occlusion)
        self.transparent = QCheckBox("Transparent Exterior")
        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.05, 1.0)
        self.opacity.setSingleStep(0.05)
        self.opacity.setValue(self.settings.opacity)
        self.opacity.setToolTip("Visualization-only opacity; exported geometry is unchanged.")
        self.edge_width = QDoubleSpinBox()
        self.edge_width.setRange(0.1, 5.0)
        self.edge_width.setSingleStep(0.1)
        self.edge_width.setValue(self.settings.edge_width)
        for widget in (
            self.smooth,
            self.edges,
            self.bbox,
            self.axes,
            self.perspective,
            self.ambient_occlusion,
            self.transparent,
            QLabel("Opacity"),
            self.opacity,
            QLabel("Edge width"),
            self.edge_width,
        ):
            display.addWidget(widget)
        layout.addLayout(display)

        clip = QHBoxLayout()
        self.clip_x = QCheckBox("Clip X")
        self.clip_y = QCheckBox("Clip Y")
        self.clip_z = QCheckBox("Clip Z")
        self.invert_clip = QCheckBox("Invert")
        self.slice_visible = QCheckBox("Slice")
        self.slice_slider = QSlider(Qt.Horizontal)
        self.slice_slider.setRange(0, 100)
        self.slice_value = QLabel("Plane: 50%")
        self.reset_clip = QPushButton("Reset Clip")
        self.operation_label = QLabel("Display operation only, exported geometry unchanged")
        self.operation_label.setWordWrap(True)
        for widget in (
            self.clip_x,
            self.clip_y,
            self.clip_z,
            self.invert_clip,
            self.slice_visible,
            self.slice_slider,
            self.slice_value,
            self.reset_clip,
            self.operation_label,
        ):
            clip.addWidget(widget)
        layout.addLayout(clip)

        screenshot = QHBoxLayout()
        self.screenshot_button = QPushButton("Screenshot")
        self.screenshot_scale = QSpinBox()
        self.screenshot_scale.setRange(1, 4)
        self.screenshot_scale.setValue(2)
        self.transparent_background = QCheckBox("Transparent PNG")
        screenshot.addWidget(self.screenshot_button)
        screenshot.addWidget(QLabel("Scale"))
        screenshot.addWidget(self.screenshot_scale)
        screenshot.addWidget(self.transparent_background)
        layout.addLayout(screenshot)

        self.status = QLabel("Preview only, not final validation")
        layout.addWidget(self.status)
        self.diagnostics = QLabel()
        self.diagnostics.setWordWrap(True)
        layout.addWidget(self.diagnostics)

    def _init_viewer(self) -> None:
        layout = self.layout()
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self.viewer = QLabel("3D viewer disabled in offscreen test mode.")
            self.viewer.setMinimumHeight(360)
            self.viewer.setAlignment(Qt.AlignCenter)
            self.capabilities["fallback"] = True
            gui_event("preview_viewer_fallback", reason="QT_QPA_PLATFORM=offscreen")
        else:
            try:
                from pyvistaqt import QtInteractor

                self.viewer = QtInteractor(self)
                self.viewer.setMinimumHeight(460)
                self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                self._plotter = self.viewer
                self._configure_renderer()
                gui_event("preview_viewer_created", widget_parent=bool(self.viewer.parent()))
            except Exception as exc:
                self.viewer = QLabel("3D preview unavailable")
                self.viewer.setToolTip(str(exc))
                self.viewer.setMinimumHeight(360)
                self.viewer.setAlignment(Qt.AlignCenter)
                self.capabilities["fallback"] = True
                gui_event("preview_viewer_unavailable", error=str(exc))
        layout.addWidget(self.viewer)
        self._update_diagnostics()

    def _connect(self) -> None:
        self.preset_combo.currentTextChanged.connect(self.apply_preset)
        self.mesh_color_button.clicked.connect(lambda: self._choose_color("mesh_color"))
        self.background_color_button.clicked.connect(lambda: self._choose_color("background_color"))
        self.edge_color_button.clicked.connect(lambda: self._choose_color("edge_color"))
        self.reset_rendering_button.clicked.connect(lambda: self.apply_preset("Scientific"))
        self.reset_button.clicked.connect(self.reset_camera)
        self.fit_button.clicked.connect(self.fit_to_view)
        self.iso_button.clicked.connect(lambda: self.view("iso"))
        self.front_button.clicked.connect(lambda: self.view("front"))
        self.side_button.clicked.connect(lambda: self.view("side"))
        self.top_button.clicked.connect(lambda: self.view("top"))
        for widget in (self.smooth, self.edges, self.bbox, self.axes, self.perspective, self.ambient_occlusion, self.transparent):
            widget.toggled.connect(self._controls_changed)
        self.opacity.valueChanged.connect(self._controls_changed)
        self.edge_width.valueChanged.connect(self._controls_changed)
        for widget in (self.clip_x, self.clip_y, self.clip_z, self.invert_clip, self.slice_visible):
            widget.toggled.connect(self._refresh_scene)
        self.slice_slider.valueChanged.connect(self._slice_changed)
        self.reset_clip.clicked.connect(self._reset_clipping)
        self.screenshot_button.clicked.connect(self.save_screenshot)

    def _configure_renderer(self) -> None:
        if not self._plotter:
            return
        self._plotter.set_background(self.settings.background_color)
        try:
            self._plotter.enable_anti_aliasing("fxaa")
            self.capabilities["anti_aliasing"] = "fxaa"
        except Exception as exc:
            self.capabilities["anti_aliasing"] = f"unavailable: {exc}"
        self._apply_ambient_occlusion()
        self._apply_depth_peeling()
        self._apply_projection()
        self._rebuild_lights()
        try:
            self.capabilities["opengl_renderer"] = self._plotter.ren_win.ReportCapabilities()
        except Exception:
            self.capabilities["opengl_renderer"] = "unknown"

    def _apply_ambient_occlusion(self) -> None:
        self.capabilities["ambient_occlusion"] = False
        if not self._plotter or not self.settings.ambient_occlusion:
            return
        for name in ("enable_ssao", "enable_eye_dome_lighting"):
            method = getattr(self._plotter, name, None)
            if method:
                try:
                    method()
                    self.capabilities["ambient_occlusion"] = name
                    return
                except Exception as exc:
                    gui_event("ambient_occlusion_failed", method=name, error=str(exc))

    def _apply_depth_peeling(self) -> None:
        self.capabilities["depth_peeling"] = False
        if not self._plotter or not self.settings.transparent_exterior:
            return
        method = getattr(self._plotter, "enable_depth_peeling", None)
        if method:
            try:
                method()
                self.capabilities["depth_peeling"] = True
            except Exception as exc:
                gui_event("depth_peeling_failed", error=str(exc))

    def _rebuild_lights(self) -> None:
        if not self._plotter:
            return
        try:
            import pyvista as pv

            self._plotter.renderer.remove_all_lights()
            lights = [
                pv.Light(position=(3, -4, 5), focal_point=(0, 0, 0), intensity=0.95, light_type="scene light"),
                pv.Light(position=(-4, 3, 2), focal_point=(0, 0, 0), intensity=0.35, light_type="scene light"),
                pv.Light(position=(0, 5, 5), focal_point=(0, 0, 0), intensity=0.55, light_type="scene light"),
            ]
            for light in lights:
                self._plotter.renderer.add_light(light)
            gui_event("lighting_rebuilt", light_count=len(lights))
        except Exception as exc:
            gui_event("lighting_failed", error=str(exc))

    def apply_preset(self, name: str) -> None:
        self.settings = preset(name)
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText(self.settings.preset)
        self.preset_combo.blockSignals(False)
        self._sync_controls_from_settings()
        save_rendering_settings(self.settings)
        self._configure_renderer()
        self._refresh_scene()

    def _sync_controls_from_settings(self) -> None:
        for widget, value in (
            (self.smooth, self.settings.smooth_shading),
            (self.edges, self.settings.show_edges),
            (self.bbox, self.settings.show_bounding_box),
            (self.axes, self.settings.show_axes),
            (self.perspective, self.settings.perspective),
            (self.ambient_occlusion, self.settings.ambient_occlusion),
            (self.transparent, self.settings.transparent_exterior),
        ):
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)
        self.opacity.blockSignals(True)
        self.opacity.setValue(self.settings.opacity)
        self.opacity.blockSignals(False)
        self.edge_width.blockSignals(True)
        self.edge_width.setValue(self.settings.edge_width)
        self.edge_width.blockSignals(False)

    def _controls_changed(self) -> None:
        self.settings.preset = self.preset_combo.currentText()
        self.settings.smooth_shading = self.smooth.isChecked()
        self.settings.show_edges = self.edges.isChecked()
        self.settings.show_bounding_box = self.bbox.isChecked()
        self.settings.show_axes = self.axes.isChecked()
        self.settings.perspective = self.perspective.isChecked()
        self.settings.ambient_occlusion = self.ambient_occlusion.isChecked()
        self.settings.transparent_exterior = self.transparent.isChecked()
        self.settings.opacity = self.opacity.value() if self.transparent.isChecked() else 1.0
        self.settings.edge_width = self.edge_width.value()
        save_rendering_settings(self.settings)
        self._configure_renderer()
        self._refresh_scene()

    def _choose_color(self, field: str) -> None:
        color = QColorDialog.getColor(QColor(getattr(self.settings, field)), self, "Choose display color")
        if color.isValid():
            setattr(self.settings, field, color.name())
            save_rendering_settings(self.settings)
            self._refresh_scene()

    def load_mesh(self, path: str | Path | None) -> None:
        if not path:
            return
        self._mesh_path = Path(path)
        gui_event("preview_mesh_load_requested", path=str(self._mesh_path), plotter=bool(self._plotter))
        if self._plotter is None:
            self.status.setText(f"Preview mesh ready: {self._mesh_path.name}")
            return
        try:
            import pyvista as pv

            t0 = time.perf_counter()
            self._loaded_mesh = pv.read(str(self._mesh_path))
            load_s = time.perf_counter() - t0
            normal_info = self._normal_info(self._loaded_mesh)
            t0 = time.perf_counter()
            self._display_mesh = self._make_display_mesh(self._loaded_mesh)
            normals_s = time.perf_counter() - t0
            self._last_timings = {"stl_load_s": load_s, "display_normals_s": normals_s}
            gui_event("display_normals_ready", **normal_info, **self._last_timings)
            self._refresh_scene(reset_camera=True)
        except Exception as exc:
            self.status.setText("3D preview unavailable")
            gui_event("preview_mesh_load_failed", path=str(self._mesh_path), error=str(exc))
            raise

    def _normal_info(self, mesh) -> dict[str, Any]:
        return {
            "points": int(mesh.n_points),
            "cells": int(mesh.n_cells),
            "bounds": tuple(round(float(x), 5) for x in mesh.bounds),
            "point_normals": bool(mesh.point_data.get("Normals") is not None),
            "cell_normals": bool(mesh.cell_data.get("Normals") is not None),
        }

    def _make_display_mesh(self, mesh):
        try:
            surface = mesh.extract_surface(algorithm="dataset_surface").triangulate()
        except TypeError:
            surface = mesh.extract_surface().triangulate()
        try:
            return surface.compute_normals(
                point_normals=True,
                cell_normals=True,
                consistent_normals=True,
                auto_orient_normals=True,
                inplace=False,
            )
        except Exception as exc:
            gui_event("display_normals_auto_orient_failed", error=str(exc))
            return surface.compute_normals(point_normals=True, cell_normals=True, consistent_normals=True, inplace=False)

    def _refresh_scene(self, reset_camera: bool = False) -> None:
        if not self._plotter or self._display_mesh is None:
            self._update_diagnostics()
            return
        t0 = time.perf_counter()
        self._plotter.clear()
        self._mesh_actor = None
        self._slice_actor = None
        mesh = self._clipped_mesh(self._display_mesh)
        style = "wireframe" if self.settings.preset == "Wireframe" else "surface"
        self._mesh_actor = self._plotter.add_mesh(
            mesh,
            color=self.settings.mesh_color,
            style=style,
            show_edges=self.settings.show_edges,
            edge_color=self.settings.edge_color,
            line_width=self.settings.edge_width,
            smooth_shading=self.settings.smooth_shading,
            ambient=0.14,
            diffuse=0.78,
            specular=0.22,
            specular_power=22,
            opacity=self.settings.opacity,
        )
        if self.slice_visible.isChecked():
            self._add_slice()
        if self.settings.show_bounding_box:
            self._plotter.add_bounding_box(color="#cbd5e1", line_width=1)
        if self.settings.show_axes:
            self._plotter.add_axes()
        self._plotter.set_background(self.settings.background_color)
        self._apply_projection()
        self._rebuild_lights()
        if reset_camera:
            self.view("iso")
            self.fit_to_view()
        else:
            self._plotter.render()
        actor_s = time.perf_counter() - t0
        self._last_timings["actor_render_s"] = actor_s
        self.status.setText(f"Preview mesh loaded: {self._mesh_path.name if self._mesh_path else ''}")
        self._update_diagnostics()
        gui_event("preview_scene_refreshed", actor_count=self.actor_count(), **self._last_timings)

    def _clipped_mesh(self, mesh):
        active = [(self.clip_x, "x"), (self.clip_y, "y"), (self.clip_z, "z")]
        clipped = mesh
        for checkbox, normal in active:
            if checkbox.isChecked():
                origin = self._clip_origin(normal)
                clipped = clipped.clip(normal=normal, origin=origin, invert=self.invert_clip.isChecked())
        return clipped

    def _clip_origin(self, axis: str) -> tuple[float, float, float]:
        if self._display_mesh is None:
            return (0.0, 0.0, 0.0)
        bounds = self._display_mesh.bounds
        fraction = self.slice_slider.value() / 100.0
        x = bounds[0] + (bounds[1] - bounds[0]) * fraction
        y = bounds[2] + (bounds[3] - bounds[2]) * fraction
        z = bounds[4] + (bounds[5] - bounds[4]) * fraction
        if axis == "x":
            return (x, (bounds[2] + bounds[3]) / 2.0, (bounds[4] + bounds[5]) / 2.0)
        if axis == "y":
            return ((bounds[0] + bounds[1]) / 2.0, y, (bounds[4] + bounds[5]) / 2.0)
        return ((bounds[0] + bounds[1]) / 2.0, (bounds[2] + bounds[3]) / 2.0, z)

    def _add_slice(self) -> None:
        if self._display_mesh is None:
            return
        axis = "x" if self.clip_x.isChecked() else "y" if self.clip_y.isChecked() else "z"
        normal = axis
        section = self._display_mesh.slice(normal=normal, origin=self._clip_origin(axis))
        self._slice_actor = self._plotter.add_mesh(section, color="#f59e0b", line_width=2.0, render_lines_as_tubes=True)

    def _slice_changed(self) -> None:
        self.slice_value.setText(f"Plane: {self.slice_slider.value()}%")
        self._refresh_scene()

    def _reset_clipping(self) -> None:
        for widget in (self.clip_x, self.clip_y, self.clip_z, self.invert_clip, self.slice_visible):
            widget.blockSignals(True)
            widget.setChecked(False)
            widget.blockSignals(False)
        self.slice_slider.setValue(50)
        self._refresh_scene()

    def reset_camera(self) -> None:
        if self._plotter:
            self.fit_to_view()

    def fit_to_view(self) -> None:
        if self._plotter:
            self._plotter.reset_camera(bounds=self._display_mesh.bounds if self._display_mesh is not None else None)
            try:
                self._plotter.camera.Zoom(0.88)
                self._plotter.camera.clipping_range = self._plotter.renderer.compute_visible_prop_bounds()
            except Exception:
                pass
            self._plotter.render()

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
        self.fit_to_view()

    def _apply_projection(self) -> None:
        if not self._plotter:
            return
        try:
            if self.settings.perspective:
                self._plotter.camera.SetParallelProjection(False)
            else:
                self._plotter.camera.SetParallelProjection(True)
        except Exception as exc:
            gui_event("projection_failed", error=str(exc))

    def save_screenshot(self) -> None:
        target = Path("runs") / "pgg_preview_screenshot.png"
        target.parent.mkdir(exist_ok=True)
        t0 = time.perf_counter()
        if self._plotter:
            self._plotter.screenshot(
                str(target),
                scale=self.screenshot_scale.value(),
                transparent_background=self.transparent_background.isChecked(),
            )
        else:
            target.write_text("Screenshot unavailable in fallback viewer.", encoding="utf-8")
        elapsed = time.perf_counter() - t0
        meta = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "rendering_preset": self.settings.preset,
            "camera_position": self._plotter.camera_position if self._plotter else None,
            "projection": "perspective" if self.settings.perspective else "orthographic",
            "mesh_artifact_path": str(self._mesh_path) if self._mesh_path else None,
            "screenshot_s": elapsed,
        }
        target.with_suffix(".json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        gui_event("screenshot_saved", path=str(target), **meta)
        self.screenshot_saved.emit(str(target))

    def actor_count(self) -> int:
        if not self._plotter:
            return 0
        try:
            return len(self._plotter.renderer.actors)
        except Exception:
            return 0

    def _update_diagnostics(self) -> None:
        self.diagnostics.setText(rendering_diagnostics(self.settings, self.capabilities))

    def close_viewer(self) -> None:
        if self._plotter:
            try:
                self._plotter.clear()
                self._plotter.close()
            except Exception as exc:
                gui_event("preview_viewer_close_failed", error=str(exc))
        self._display_mesh = None
        self._loaded_mesh = None
