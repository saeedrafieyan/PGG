"""Structure-family controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from porous_designer.domain.enums import StructureFamily
from porous_designer.gui.panels.domain_panel import spin


def _form(widget: QWidget) -> QFormLayout:
    form = QFormLayout(widget)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    return form


class StructurePanel(QWidget):
    changed = Signal()

    # Sphere-pore families first: indices < 4 use the pore-diameter page.
    FAMILY_LABELS = {
        "SC": "sc_spherical_pores",
        "BCC": "bcc_spherical_pores",
        "FCC": "fcc_spherical_pores",
        "HCP": "hcp_spherical_pores",
        "Gyroid": "gyroid",
        "Diamond": "diamond",
        "Primitive": "primitive",
        "I-WP": "iwp",
        "Neovius": "neovius",
        "Fischer-Koch S": "fischer_koch_s",
        "Lidinoid": "lidinoid",
        "Cubic struts": "strut_cubic",
        "BCC struts": "strut_bcc",
        "Octet truss": "strut_octet",
        "Kelvin cell": "strut_kelvin",
        "Voronoi foam": "voronoi_foam",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.family = QComboBox()
        self.family.addItems(self.FAMILY_LABELS.keys())
        layout.addWidget(self.family)
        self.stack = QStackedWidget()

        sphere = QWidget()
        sphere_form = _form(sphere)
        self.pore_diameter = spin(1.0)
        self.lattice_spacing = QDoubleSpinBox()
        self.lattice_spacing.setRange(0.0, 1000.0)
        self.lattice_spacing.setSpecialValueText("tuned")
        self.lattice_spacing.setSuffix(" mm")
        sphere_form.addRow("Pore diameter", self.pore_diameter)
        sphere_form.addRow("Lattice spacing", self.lattice_spacing)

        cell = QWidget()
        cell_form = _form(cell)
        self.unit_cell = spin(1.5)
        self.variant = QComboBox()
        self.variant.addItems(["sheet", "network"])
        self.variant.setToolTip("sheet: thin walls around the minimal surface. network: solid on one side of it.")
        self.wall_thickness = QDoubleSpinBox()
        self.wall_thickness.setRange(0.0, 100.0)
        self.wall_thickness.setDecimals(4)
        self.wall_thickness.setSuffix(" mm")
        self.wall_thickness.setSpecialValueText("tuned to porosity")
        self.wall_thickness.setToolTip("Fixed sheet thickness or strut diameter. When set, porosity becomes a result.")
        self.randomness = QDoubleSpinBox()
        self.randomness.setRange(0.0, 1.0)
        self.randomness.setDecimals(2)
        self.randomness.setSingleStep(0.1)
        self.randomness.setValue(1.0)
        self.randomness.setToolTip("Voronoi seed jitter: 0 regular grid, 1 fully random within each cell.")
        self.cell_grading = QCheckBox("Grade the unit-cell size")
        self.cell_axis = QComboBox()
        self.cell_axis.addItems(["z", "x", "y"])
        self.cell_start = spin(1.5)
        self.cell_end = spin(2.5)
        self.periodicity = QCheckBox("Periodic continuation")
        self.periodicity.setChecked(True)
        cell_form.addRow("Unit-cell size", self.unit_cell)
        cell_form.addRow("TPMS variant", self.variant)
        cell_form.addRow("Wall / strut thickness", self.wall_thickness)
        cell_form.addRow("Voronoi randomness", self.randomness)
        cell_form.addRow("Cell-size grading", self.cell_grading)
        cell_form.addRow("Grading axis", self.cell_axis)
        cell_form.addRow("Cell size at start", self.cell_start)
        cell_form.addRow("Cell size at end", self.cell_end)
        cell_form.addRow("Periodicity", self.periodicity)
        cell_form.addRow("Search", QLabel("Wall thickness is tuned by the backend to reach the porosity target."))

        self.stack.addWidget(sphere)
        self.stack.addWidget(cell)
        layout.addWidget(self.stack)
        self.family.currentIndexChanged.connect(self._family_changed)
        self.family.currentIndexChanged.connect(self.changed)
        self.variant.currentTextChanged.connect(self._family_changed)
        self.cell_grading.toggled.connect(self._family_changed)
        for widget in (self.pore_diameter, self.lattice_spacing, self.unit_cell, self.wall_thickness, self.randomness, self.cell_start, self.cell_end):
            widget.valueChanged.connect(self.changed)
        for combo in (self.variant, self.cell_axis):
            combo.currentTextChanged.connect(self.changed)
        for check in (self.periodicity, self.cell_grading):
            check.toggled.connect(self.changed)
        self._family_changed()

    def current_family(self) -> StructureFamily:
        return StructureFamily(self.FAMILY_LABELS[self.family.currentText()])

    def _family_changed(self) -> None:
        family = self.current_family()
        self.stack.setCurrentIndex(0 if family.is_sphere_lattice else 1)
        self.variant.setEnabled(family.is_tpms)
        network = family.is_tpms and self.variant.currentText() == "network"
        self.wall_thickness.setEnabled(not network)
        self.randomness.setEnabled(family.is_stochastic)
        gradable = family.is_tpms or family.is_strut_lattice
        self.cell_grading.setEnabled(gradable)
        for widget in (self.cell_axis, self.cell_start, self.cell_end):
            widget.setEnabled(gradable and self.cell_grading.isChecked())

    def values(self) -> dict:
        family = self.current_family()
        gradable = family.is_tpms or family.is_strut_lattice
        return {
            "family": family.value,
            "pore_diameter": self.pore_diameter.value(),
            "lattice_spacing": self.lattice_spacing.value() or None,
            "unit_cell_size": self.unit_cell.value(),
            "tpms_variant": self.variant.currentText() if family.is_tpms else "sheet",
            "wall_thickness": (self.wall_thickness.value() or None) if self.wall_thickness.isEnabled() else None,
            "voronoi_randomness": self.randomness.value(),
            "cell_size_grading": (
                {"mode": "linear", "axis": self.cell_axis.currentText(), "start": self.cell_start.value(), "end": self.cell_end.value()}
                if gradable and self.cell_grading.isChecked()
                else None
            ),
            "tpms_level_set": None,
            "periodicity": self.periodicity.isChecked(),
        }

    def load(self, structure) -> None:
        """Show an existing StructureSpec in the controls."""
        label = next((name for name, value in self.FAMILY_LABELS.items() if value == structure.family.value), "SC")
        self.family.setCurrentText(label)
        if structure.pore_diameter_mm is not None:
            self.pore_diameter.setValue(structure.pore_diameter_mm)
        self.lattice_spacing.setValue(structure.lattice_spacing_mm or 0.0)
        if structure.unit_cell_size_mm is not None:
            self.unit_cell.setValue(structure.unit_cell_size_mm)
        self.variant.setCurrentText(structure.tpms_variant.value)
        self.wall_thickness.setValue(structure.wall_thickness_mm or 0.0)
        self.randomness.setValue(structure.voronoi_randomness)
        grading = structure.cell_size_grading
        self.cell_grading.setChecked(grading is not None)
        if grading is not None:
            self.cell_axis.setCurrentText(grading.axis)
            self.cell_start.setValue(grading.start)
            self.cell_end.setValue(grading.end)
        self.periodicity.setChecked(structure.periodicity)
        self._family_changed()
