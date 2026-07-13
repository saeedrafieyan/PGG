"""Structure-family controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from porous_designer.gui.panels.domain_panel import spin


class StructurePanel(QWidget):
    changed = Signal()

    FAMILY_LABELS = {
        "SC": "sc_spherical_pores",
        "BCC": "bcc_spherical_pores",
        "FCC": "fcc_spherical_pores",
        "HCP": "hcp_spherical_pores",
        "Gyroid": "gyroid",
        "Diamond": "diamond",
        "Primitive": "primitive",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.family = QComboBox()
        self.family.addItems(self.FAMILY_LABELS.keys())
        layout.addWidget(self.family)
        self.stack = QStackedWidget()
        sphere = QWidget()
        sphere_form = QFormLayout(sphere)
        sphere_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        sphere_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.pore_diameter = spin(1.0)
        self.lattice_spacing = QDoubleSpinBox()
        self.lattice_spacing.setRange(0.0, 1000.0)
        self.lattice_spacing.setSpecialValueText("tuned")
        self.lattice_spacing.setSuffix(" mm")
        sphere_form.addRow("Pore diameter", self.pore_diameter)
        sphere_form.addRow("Lattice spacing", self.lattice_spacing)
        tpms = QWidget()
        tpms_form = QFormLayout(tpms)
        tpms_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        tpms_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.unit_cell = spin(1.5)
        self.tpms_level = QDoubleSpinBox()
        self.tpms_level.setRange(-5.0, 5.0)
        self.tpms_level.setDecimals(5)
        self.tpms_level.setSpecialValueText("tuned")
        self.periodicity = QCheckBox("Periodic continuation")
        self.periodicity.setChecked(True)
        tpms_form.addRow("Unit-cell size", self.unit_cell)
        tpms_form.addRow("Level set", self.tpms_level)
        tpms_form.addRow("Periodicity", self.periodicity)
        tpms_form.addRow("Search", QLabel("Bisection range is provided by the backend generator."))
        self.stack.addWidget(sphere)
        self.stack.addWidget(tpms)
        layout.addWidget(self.stack)
        self.family.currentIndexChanged.connect(self._family_changed)
        self.family.currentIndexChanged.connect(self.changed)
        for widget in (self.pore_diameter, self.lattice_spacing, self.unit_cell, self.tpms_level):
            widget.valueChanged.connect(self.changed)
        self.periodicity.toggled.connect(self.changed)

    def _family_changed(self) -> None:
        self.stack.setCurrentIndex(0 if self.family.currentIndex() < 4 else 1)

    def values(self) -> dict:
        return {
            "family": self.FAMILY_LABELS[self.family.currentText()],
            "pore_diameter": self.pore_diameter.value(),
            "lattice_spacing": self.lattice_spacing.value() or None,
            "unit_cell_size": self.unit_cell.value(),
            "tpms_level_set": self.tpms_level.value() or None,
            "periodicity": self.periodicity.isChecked(),
        }
