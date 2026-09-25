"""Manufacturing: process, printer profile, and printability enforcement."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QWidget

PROCESSES = ["unknown", "fdm", "sla", "dlp", "volumetric", "bioprinting", "sls", "lpbf"]
AUTO = "(generic for process)"


class ManufacturingPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.process = QComboBox()
        self.process.addItems(PROCESSES)
        self.process.setToolTip("Printing process; 'unknown' skips the printability checks.")
        self.printer = QComboBox()
        self.printer.setToolTip("Printer profile (generic, or calibrated with 'porous-designer calibrate').")
        self.enforce = QCheckBox("Fail the run on printability issues")
        self.minimum_feature = QDoubleSpinBox()
        self.minimum_feature.setRange(0.01, 100.0)
        self.minimum_feature.setValue(0.4)
        self.minimum_feature.setSuffix(" mm")
        self.profile_info = QLabel("")
        self.profile_info.setWordWrap(True)
        layout.addRow("Process", self.process)
        layout.addRow("Printer profile", self.printer)
        layout.addRow("", self.profile_info)
        layout.addRow("Printability", self.enforce)
        layout.addRow("Min printable feature", self.minimum_feature)
        self._refresh_profiles()
        self.process.currentTextChanged.connect(self._refresh_profiles)
        self.process.currentTextChanged.connect(self.changed)
        self.printer.currentTextChanged.connect(self._show_profile)
        self.printer.currentTextChanged.connect(self.changed)
        self.enforce.toggled.connect(self.changed)
        self.minimum_feature.valueChanged.connect(self.changed)

    def _profiles(self):
        try:
            from porous_designer.printability.profiles import all_profiles

            return all_profiles()
        except Exception:
            return {}

    def _refresh_profiles(self) -> None:
        process = self.process.currentText()
        current = self.printer.currentText()
        self.printer.blockSignals(True)
        self.printer.clear()
        self.printer.addItem(AUTO)
        for pid, prof in sorted(self._profiles().items()):
            if process in ("unknown", prof.process):
                self.printer.addItem(pid)
        index = self.printer.findText(current)
        self.printer.setCurrentIndex(index if index >= 0 else 0)
        self.printer.blockSignals(False)
        self._show_profile()

    def _show_profile(self) -> None:
        pid = self.printer.currentText()
        prof = self._profiles().get(pid)
        if prof is None:
            self.profile_info.setText("No printability checks." if self.process.currentText() == "unknown" else "Generic limits for the selected process.")
            return
        tag = "calibrated" if prof.calibrated else "generic - calibrate with a coupon"
        self.profile_info.setText(f"min wall {prof.min_wall_mm} mm, min hole {prof.min_hole_mm} mm ({tag})")

    def values(self) -> dict:
        printer = self.printer.currentText()
        return {
            "process": self.process.currentText(),
            "printer_profile": "" if printer == AUTO else printer,
            "enforce_printability": self.enforce.isChecked(),
            "minimum_printable_feature_mm": self.minimum_feature.value(),
        }

    def load(self, manufacturing) -> None:
        process = manufacturing.process if manufacturing.process in PROCESSES else "unknown"
        self.process.setCurrentText(process)
        self._refresh_profiles()
        index = self.printer.findText(manufacturing.printer_profile or "")
        self.printer.setCurrentIndex(index if index >= 0 else 0)
        self.enforce.setChecked(bool(getattr(manufacturing, "enforce_printability", False)))
        self.minimum_feature.setValue(manufacturing.minimum_printable_feature_mm)
