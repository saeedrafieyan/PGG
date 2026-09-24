"""Domain controls: box, cylinder, sphere, or an imported closed mesh."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

MESH_FILE_FILTER = "Closed meshes (*.stl *.obj *.ply *.off *.glb *.3mf);;All files (*)"


def spin(value: float, minimum: float = 0.01, maximum: float = 1000.0, suffix: str = " mm") -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(4)
    box.setValue(value)
    box.setSuffix(suffix)
    box.setMinimumWidth(150)
    return box


def _form(widget: QWidget) -> QFormLayout:
    form = QFormLayout(widget)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    return form


class DomainPanel(QWidget):
    changed = Signal()

    SHAPES = ["box", "cylinder", "sphere", "mesh"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.shape = QComboBox()
        self.shape.addItems(self.SHAPES)
        layout.addWidget(self.shape)
        self.stack = QStackedWidget()

        box_widget = QWidget()
        box_form = _form(box_widget)
        self.box_x = spin(4.0)
        self.box_y = spin(4.0)
        self.box_z = spin(4.0)
        box_form.addRow("X dimension", self.box_x)
        box_form.addRow("Y dimension", self.box_y)
        box_form.addRow("Z dimension", self.box_z)

        cyl_widget = QWidget()
        cyl_form = _form(cyl_widget)
        self.cyl_diameter = spin(4.0)
        self.cyl_height = spin(6.0)
        self.axis = QComboBox()
        self.axis.addItems(["z_up"])
        cyl_form.addRow("Diameter", self.cyl_diameter)
        cyl_form.addRow("Height", self.cyl_height)
        cyl_form.addRow("Axis", self.axis)

        sphere_widget = QWidget()
        sphere_form = _form(sphere_widget)
        self.sphere_diameter = spin(8.0)
        sphere_form.addRow("Diameter", self.sphere_diameter)

        mesh_widget = QWidget()
        mesh_form = _form(mesh_widget)
        self.mesh_path = QLineEdit()
        self.mesh_path.setPlaceholderText("Closed (watertight) STL / OBJ / PLY / 3MF")
        self.mesh_browse = QPushButton("Browse...")
        row = QHBoxLayout()
        row.addWidget(self.mesh_path, 1)
        row.addWidget(self.mesh_browse)
        self.mesh_units = QComboBox()
        self.mesh_units.addItems(["mm", "cm", "m", "um", "in"])
        self.mesh_info = QLabel("No mesh loaded.")
        self.mesh_info.setWordWrap(True)
        mesh_form.addRow("Mesh file", row)
        mesh_form.addRow("File units", self.mesh_units)
        mesh_form.addRow("Extents", self.mesh_info)

        for page in (box_widget, cyl_widget, sphere_widget, mesh_widget):
            self.stack.addWidget(page)
        layout.addWidget(self.stack)

        skin = QWidget()
        skin_form = _form(skin)
        self.skin_thickness = QDoubleSpinBox()
        self.skin_thickness.setRange(0.0, 100.0)
        self.skin_thickness.setDecimals(3)
        self.skin_thickness.setSuffix(" mm")
        self.skin_thickness.setSpecialValueText("none")
        self.skin_mode = QComboBox()
        self.skin_mode.addItems(["all", "lateral"])
        self.skin_mode.setToolTip("all: solid shell on every boundary (closes the pores). lateral: side walls only, open along Z.")
        skin_form.addRow("Solid skin", self.skin_thickness)
        skin_form.addRow("Skin on", self.skin_mode)
        layout.addWidget(skin)

        self.shape.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.shape.currentIndexChanged.connect(self.changed)
        self.mesh_browse.clicked.connect(self._browse_mesh)
        self.mesh_path.editingFinished.connect(self._mesh_changed)
        self.mesh_units.currentTextChanged.connect(self._mesh_changed)
        for widget in (self.box_x, self.box_y, self.box_z, self.cyl_diameter, self.cyl_height, self.sphere_diameter, self.skin_thickness):
            widget.valueChanged.connect(self.changed)
        self.skin_mode.currentTextChanged.connect(self.changed)

    def _browse_mesh(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a closed mesh domain", self.mesh_path.text(), MESH_FILE_FILTER)
        if path:
            self.mesh_path.setText(path)
            self._mesh_changed()

    def _mesh_changed(self) -> None:
        self.mesh_info.setText(self.describe_mesh())
        self.changed.emit()

    def describe_mesh(self) -> str:
        path = self.mesh_path.text().strip()
        if not path:
            return "No mesh loaded."
        if not Path(path).is_file():
            return "File not found."
        try:
            from porous_designer.domain.specification import DomainSpec

            domain = DomainSpec.from_mesh_file(path, units=self.mesh_units.currentText())
        except Exception as exc:  # shown to the user, not raised
            return f"Cannot use this mesh: {exc}"
        dims = " x ".join(f"{v:.3f}" for v in domain.dimensions_mm)
        return f"{dims} mm, volume {domain.volume_mm3:.2f} mm³"

    def values(self) -> dict:
        return {
            "domain_shape": self.shape.currentText(),
            "box_x": self.box_x.value(),
            "box_y": self.box_y.value(),
            "box_z": self.box_z.value(),
            "cylinder_diameter": self.cyl_diameter.value(),
            "cylinder_height": self.cyl_height.value(),
            "sphere_diameter": self.sphere_diameter.value(),
            "mesh_path": self.mesh_path.text().strip() or None,
            "mesh_units": self.mesh_units.currentText(),
            "skin_thickness": self.skin_thickness.value() or None,
            "skin_mode": self.skin_mode.currentText(),
            "axis": self.axis.currentText(),
        }

    def load(self, domain) -> None:
        """Show an existing DomainSpec in the controls."""
        self.shape.setCurrentText(domain.shape.value)
        dims = domain.dimensions_mm
        if domain.shape.value == "box":
            self.box_x.setValue(dims[0])
            self.box_y.setValue(dims[1])
            self.box_z.setValue(dims[2])
        elif domain.shape.value == "cylinder":
            self.cyl_diameter.setValue(dims[0])
            self.cyl_height.setValue(dims[1])
        elif domain.shape.value == "sphere":
            self.sphere_diameter.setValue(dims[0])
        else:
            self.mesh_path.setText(domain.mesh_path or "")
            self.mesh_units.setCurrentText(domain.mesh_units)
            self.mesh_info.setText(self.describe_mesh())
        self.skin_thickness.setValue(domain.skin_thickness_mm or 0.0)
        self.skin_mode.setCurrentText(domain.skin_mode.value)
