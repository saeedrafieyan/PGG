"""Manufacturing constraints panel."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLineEdit, QWidget


class ManufacturingPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.process = QLineEdit("unknown")
        self.printer = QLineEdit("generic_fdm")
        self.minimum_feature = QDoubleSpinBox()
        self.minimum_feature.setRange(0.01, 100.0)
        self.minimum_feature.setValue(0.4)
        self.minimum_feature.setSuffix(" mm")
        layout.addRow("Process", self.process)
        layout.addRow("Printer profile", self.printer)
        layout.addRow("Min printable feature", self.minimum_feature)
        self.process.textChanged.connect(self.changed)
        self.printer.textChanged.connect(self.changed)
        self.minimum_feature.valueChanged.connect(self.changed)

    def values(self) -> dict:
        return {
            "process": self.process.text(),
            "printer_profile": self.printer.text(),
            "minimum_printable_feature_mm": self.minimum_feature.value(),
        }
