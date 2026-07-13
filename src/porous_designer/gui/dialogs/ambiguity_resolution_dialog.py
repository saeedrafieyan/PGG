"""Simple ambiguity resolution dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QPushButton, QVBoxLayout

from porous_designer.agentic.contracts import AmbiguityItem


class AmbiguityResolutionDialog(QDialog):
    def __init__(self, ambiguities: list[AmbiguityItem], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resolve Ambiguities")
        self.combos: dict[str, QComboBox] = {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        for item in ambiguities:
            combo = QComboBox()
            combo.addItems(item.candidate_interpretations)
            combo.setCurrentText(item.recommended_choice)
            combo.setToolTip(item.explanation)
            self.combos[item.identifier] = combo
            form.addRow(item.source_phrase, combo)
        layout.addLayout(form)
        approve = QPushButton("Apply Resolutions")
        layout.addWidget(approve)
        approve.clicked.connect(self.accept)

    def resolutions(self) -> dict[str, str]:
        return {identifier: combo.currentText() for identifier, combo in self.combos.items()}
