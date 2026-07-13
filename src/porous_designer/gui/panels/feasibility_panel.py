"""Resource feasibility display."""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QWidget


class FeasibilityPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)
        self.status = QLabel("not estimated")
        self.grid = QLabel("-")
        self.voxels = QLabel("-")
        self.peak = QLabel("-")
        self.available = QLabel("-")
        self.runtime = QLabel("-")
        self.message = QLabel("-")
        for label, widget in (
            ("Status", self.status),
            ("Grid", self.grid),
            ("Voxels", self.voxels),
            ("Peak memory", self.peak),
            ("Available memory", self.available),
            ("Runtime", self.runtime),
            ("Message", self.message),
        ):
            layout.addRow(label, widget)

    def set_estimate(self, estimate: dict) -> None:
        self.status.setText(str(estimate.get("status", "unknown")).upper())
        self.grid.setText(" x ".join(str(x) for x in estimate.get("grid_shape", [])))
        self.voxels.setText(f"{estimate.get('voxel_count', '-')}")
        self.peak.setText(f"{estimate.get('estimated_peak_mb', '-')} MB")
        self.available.setText(f"{estimate.get('available_memory_mb', '-')} MB")
        self.runtime.setText(str(estimate.get("runtime_class", "-")))
        self.message.setText(str(estimate.get("message", "-")))
