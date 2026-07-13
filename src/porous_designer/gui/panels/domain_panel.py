"""Domain controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QStackedWidget, QVBoxLayout, QWidget


def spin(value: float, minimum: float = 0.01, maximum: float = 1000.0, suffix: str = " mm") -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(4)
    box.setValue(value)
    box.setSuffix(suffix)
    return box


class DomainPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.shape = QComboBox()
        self.shape.addItems(["box", "cylinder"])
        layout.addWidget(self.shape)
        self.stack = QStackedWidget()
        box_widget = QWidget()
        box_form = QFormLayout(box_widget)
        self.box_x = spin(4.0)
        self.box_y = spin(4.0)
        self.box_z = spin(4.0)
        box_form.addRow("X dimension", self.box_x)
        box_form.addRow("Y dimension", self.box_y)
        box_form.addRow("Z dimension", self.box_z)
        cyl_widget = QWidget()
        cyl_form = QFormLayout(cyl_widget)
        self.cyl_diameter = spin(4.0)
        self.cyl_height = spin(6.0)
        self.axis = QComboBox()
        self.axis.addItems(["z_up"])
        cyl_form.addRow("Diameter", self.cyl_diameter)
        cyl_form.addRow("Height", self.cyl_height)
        cyl_form.addRow("Axis", self.axis)
        self.stack.addWidget(box_widget)
        self.stack.addWidget(cyl_widget)
        layout.addWidget(self.stack)
        self.shape.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.shape.currentIndexChanged.connect(self.changed)
        for widget in (self.box_x, self.box_y, self.box_z, self.cyl_diameter, self.cyl_height):
            widget.valueChanged.connect(self.changed)

    def values(self) -> dict:
        return {
            "domain_shape": self.shape.currentText(),
            "box_x": self.box_x.value(),
            "box_y": self.box_y.value(),
            "box_z": self.box_z.value(),
            "cylinder_diameter": self.cyl_diameter.value(),
            "cylinder_height": self.cyl_height.value(),
            "axis": self.axis.currentText(),
        }
