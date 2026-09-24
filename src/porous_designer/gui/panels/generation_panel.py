"""Generation controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget


class GenerationPanel(QWidget):
    changed = Signal()
    estimate_requested = Signal()
    preview_requested = Signal()
    final_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.profile = QComboBox()
        self.profile.addItems(["preview", "final", "reference"])
        self.preview_resolution = QDoubleSpinBox()
        self.preview_resolution.setRange(0.01, 10.0)
        self.preview_resolution.setValue(0.20)
        self.preview_resolution.setSuffix(" mm")
        self.final_resolution = QDoubleSpinBox()
        self.final_resolution.setRange(0.01, 10.0)
        self.final_resolution.setValue(0.12)
        self.final_resolution.setSuffix(" mm")
        self.reference_resolution = QDoubleSpinBox()
        self.reference_resolution.setRange(0.01, 10.0)
        self.reference_resolution.setValue(0.08)
        self.reference_resolution.setSuffix(" mm")
        self.maximum_memory = QDoubleSpinBox()
        self.maximum_memory.setRange(0.1, 1024.0)
        self.maximum_memory.setValue(16.0)
        self.maximum_memory.setSuffix(" GB")
        self.maximum_runtime = QDoubleSpinBox()
        self.maximum_runtime.setRange(1.0, 86400.0)
        self.maximum_runtime.setValue(600.0)
        self.maximum_runtime.setSuffix(" s")
        self.stl_enabled = QCheckBox("STL")
        self.stl_enabled.setChecked(True)
        self.threemf_enabled = QCheckBox("3MF (millimetre units, preferred by slicers)")
        self.step_enabled = QCheckBox("STEP (faceted solid for CAD)")
        self.step_enabled.setToolTip("Written only when the mesh can be reduced to the STEP triangle limit within 0.05 mm; otherwise skipped with a note.")
        self.step_max_triangles = QSpinBox()
        self.step_max_triangles.setRange(1000, 200000)
        self.step_max_triangles.setSingleStep(5000)
        self.step_max_triangles.setValue(20000)
        self.compute_backend = QComboBox()
        self.compute_backend.addItems(["auto", "cpu", "cuda"])
        self.compute_backend.setToolTip("auto uses the GPU (PyTorch CUDA) for large grids when available.")
        form.addRow("Profile", self.profile)
        form.addRow("Preview resolution", self.preview_resolution)
        form.addRow("Final resolution", self.final_resolution)
        form.addRow("Reference resolution", self.reference_resolution)
        form.addRow("Memory limit", self.maximum_memory)
        form.addRow("Runtime limit", self.maximum_runtime)
        form.addRow("Compute", self.compute_backend)
        form.addRow("Export", self.stl_enabled)
        form.addRow("", self.threemf_enabled)
        form.addRow("", self.step_enabled)
        form.addRow("STEP triangle limit", self.step_max_triangles)
        layout.addLayout(form)
        self.status_label = QLabel("Preview only, not final validation")
        layout.addWidget(self.status_label)
        self.estimate_button = QPushButton("Estimate")
        self.preview_button = QPushButton("Generate Preview")
        self.final_button = QPushButton("Generate Final")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        layout.addWidget(self.estimate_button)
        layout.addWidget(self.preview_button)
        layout.addWidget(self.final_button)
        layout.addWidget(self.cancel_button)
        self.estimate_button.clicked.connect(self.estimate_requested)
        self.preview_button.clicked.connect(self.preview_requested)
        self.final_button.clicked.connect(self.final_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)
        for widget in (self.profile, self.preview_resolution, self.final_resolution, self.reference_resolution, self.maximum_memory, self.maximum_runtime, self.compute_backend, self.step_max_triangles):
            signal = widget.currentTextChanged if isinstance(widget, QComboBox) else widget.valueChanged
            signal.connect(self.changed)
        for check in (self.stl_enabled, self.threemf_enabled, self.step_enabled):
            check.toggled.connect(self.changed)

    def set_generation_enabled(self, enabled: bool, final_allowed: bool = True) -> None:
        self.preview_button.setEnabled(enabled)
        self.final_button.setEnabled(enabled and final_allowed)

    def set_inputs_enabled(self, enabled: bool) -> None:
        for widget in (
            self.profile,
            self.preview_resolution,
            self.final_resolution,
            self.reference_resolution,
            self.maximum_memory,
            self.maximum_runtime,
            self.stl_enabled,
            self.threemf_enabled,
            self.step_enabled,
            self.step_max_triangles,
            self.compute_backend,
        ):
            widget.setEnabled(enabled)

    def set_busy(self, busy: bool) -> None:
        for widget in (
            self.estimate_button,
            self.preview_button,
            self.final_button,
            self.profile,
            self.preview_resolution,
            self.final_resolution,
            self.reference_resolution,
            self.maximum_memory,
            self.maximum_runtime,
        ):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def values(self) -> dict:
        return {
            "preview_resolution": self.preview_resolution.value(),
            "final_resolution": self.final_resolution.value(),
            "reference_resolution": self.reference_resolution.value(),
            "maximum_memory_gb": self.maximum_memory.value(),
            "maximum_runtime_s": self.maximum_runtime.value(),
            "compute_backend": self.compute_backend.currentText(),
            "step_max_triangles": self.step_max_triangles.value(),
            "export_formats": [fmt for fmt, check in (("stl", self.stl_enabled), ("3mf", self.threemf_enabled), ("step", self.step_enabled)) if check.isChecked()],
        }

    def load(self, generation, export) -> None:
        self.preview_resolution.setValue(generation.preview_resolution_mm)
        self.final_resolution.setValue(generation.final_resolution_mm)
        self.reference_resolution.setValue(generation.reference_resolution_mm)
        self.maximum_memory.setValue(generation.maximum_memory_gb)
        self.maximum_runtime.setValue(generation.maximum_runtime_s)
        self.compute_backend.setCurrentText(generation.compute_backend)
        self.step_max_triangles.setValue(generation.step_max_triangles)
        formats = {f.value for f in export.formats}
        self.stl_enabled.setChecked("stl" in formats)
        self.threemf_enabled.setChecked("3mf" in formats)
        self.step_enabled.setChecked("step" in formats)
