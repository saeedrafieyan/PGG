"""Targets and constraints controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QWidget


def _fraction(value: float) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(0.0, 1.0)
    box.setDecimals(4)
    box.setSingleStep(0.01)
    box.setValue(value)
    return box


class TargetsPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.porosity = _fraction(0.55)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(0.0, 0.5)
        self.tolerance.setDecimals(4)
        self.tolerance.setValue(0.08)
        self.graded = QCheckBox("Graded porosity")
        self.graded.setToolTip("Porosity varies from the start value to the end value; the target above is then the mean.")
        self.grading_mode = QComboBox()
        self.grading_mode.addItems(["linear", "radial", "surface_distance"])
        self.grading_mode.setToolTip("linear: along an axis. radial: from the centre line outwards. surface_distance: from the surface inwards over the depth.")
        self.grading_axis = QComboBox()
        self.grading_axis.addItems(["z", "x", "y"])
        self.grading_start = _fraction(0.5)
        self.grading_end = _fraction(0.8)
        self.grading_depth = QDoubleSpinBox()
        self.grading_depth.setRange(0.01, 1000.0)
        self.grading_depth.setValue(2.0)
        self.grading_depth.setSuffix(" mm")
        self.require_open = QCheckBox("Require pore percolation")
        self.require_open.setChecked(True)
        self.single_solid = QCheckBox("Require single solid component")
        self.single_solid.setChecked(True)
        self.wall = QDoubleSpinBox()
        self.wall.setRange(0.0, 1000.0)
        self.wall.setSuffix(" mm")
        self.wall.setSpecialValueText("unavailable")
        self.throat = QDoubleSpinBox()
        self.throat.setRange(0.0, 1000.0)
        self.throat.setSuffix(" mm")
        self.throat.setSpecialValueText("unavailable")
        layout.addRow("Target porosity", self.porosity)
        layout.addRow("Porosity tolerance", self.tolerance)
        layout.addRow("Grading", self.graded)
        layout.addRow("Grading mode", self.grading_mode)
        layout.addRow("Grading axis", self.grading_axis)
        layout.addRow("Porosity at start", self.grading_start)
        layout.addRow("Porosity at end", self.grading_end)
        layout.addRow("Surface depth", self.grading_depth)
        layout.addRow("Open pores", self.require_open)
        layout.addRow("Single solid", self.single_solid)
        layout.addRow("Min wall thickness", self.wall)
        layout.addRow("Min throat size", self.throat)
        layout.addRow("Unsupported", QLabel("Wall and throat minima are recorded but not yet measured by validation."))
        for widget in (self.porosity, self.tolerance, self.wall, self.throat, self.grading_start, self.grading_end, self.grading_depth):
            widget.valueChanged.connect(self.changed)
        for combo in (self.grading_mode, self.grading_axis):
            combo.currentTextChanged.connect(self._grading_changed)
        self.graded.toggled.connect(self._grading_changed)
        self.require_open.toggled.connect(self.changed)
        self.single_solid.toggled.connect(self.changed)
        self._grading_changed()

    def _grading_changed(self) -> None:
        on = self.graded.isChecked()
        mode = self.grading_mode.currentText()
        self.grading_mode.setEnabled(on)
        self.grading_axis.setEnabled(on and mode != "surface_distance")
        self.grading_start.setEnabled(on)
        self.grading_end.setEnabled(on)
        self.grading_depth.setEnabled(on and mode == "surface_distance")
        self.porosity.setEnabled(not on)
        self.changed.emit()

    def values(self) -> dict:
        grading = None
        if self.graded.isChecked():
            mode = self.grading_mode.currentText()
            grading = {
                "mode": mode,
                "axis": self.grading_axis.currentText(),
                "start": self.grading_start.value(),
                "end": self.grading_end.value(),
                "depth_mm": self.grading_depth.value() if mode == "surface_distance" else None,
            }
        return {
            "porosity_target": self.porosity.value(),
            "porosity_tolerance": self.tolerance.value(),
            "porosity_grading": grading,
            "require_open_pores": self.require_open.isChecked(),
            "require_single_solid_component": self.single_solid.isChecked(),
            "minimum_wall_thickness": self.wall.value() or None,
            "minimum_throat_size": self.throat.value() or None,
        }

    def load(self, targets, constraints) -> None:
        self.porosity.setValue(targets.porosity_target.target)
        self.tolerance.setValue(targets.porosity_target.tolerance)
        grading = targets.porosity_grading
        self.graded.setChecked(grading is not None)
        if grading is not None:
            self.grading_mode.setCurrentText(grading.mode.value)
            self.grading_axis.setCurrentText(grading.axis)
            self.grading_start.setValue(grading.start)
            self.grading_end.setValue(grading.end)
            if grading.depth_mm:
                self.grading_depth.setValue(grading.depth_mm)
        self.require_open.setChecked(constraints.require_open_pores)
        self.single_solid.setChecked(constraints.require_single_solid_component)
        self.wall.setValue(constraints.minimum_wall_thickness_mm or 0.0)
        self.throat.setValue(constraints.minimum_throat_size_mm or 0.0)
        self._grading_changed()
