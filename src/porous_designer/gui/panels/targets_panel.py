"""Targets and constraints controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout, QLabel, QWidget


class TargetsPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.porosity = QDoubleSpinBox()
        self.porosity.setRange(0.0, 1.0)
        self.porosity.setDecimals(4)
        self.porosity.setSingleStep(0.01)
        self.porosity.setValue(0.55)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(0.0, 0.5)
        self.tolerance.setDecimals(4)
        self.tolerance.setValue(0.08)
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
        layout.addRow("Open pores", self.require_open)
        layout.addRow("Single solid", self.single_solid)
        layout.addRow("Min wall thickness", self.wall)
        layout.addRow("Min throat size", self.throat)
        layout.addRow("Unsupported", QLabel("Wall and throat measurements are not final validators in Phase 3A."))
        for widget in (self.porosity, self.tolerance, self.wall, self.throat):
            widget.valueChanged.connect(self.changed)
        self.require_open.toggled.connect(self.changed)
        self.single_solid.toggled.connect(self.changed)

    def values(self) -> dict:
        return {
            "porosity_target": self.porosity.value(),
            "porosity_tolerance": self.tolerance.value(),
            "require_open_pores": self.require_open.isChecked(),
            "require_single_solid_component": self.single_solid.isChecked(),
            "minimum_wall_thickness": self.wall.value() or None,
            "minimum_throat_size": self.throat.value() or None,
        }
