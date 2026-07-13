"""Field-by-field proposed specification review."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from porous_designer.agentic.contracts import FieldReviewDecision, ParsedRequestResult
from porous_designer.domain.specification import DesignSpecification


class SpecificationReviewDialog(QDialog):
    HEADERS = ["Field", "Current", "Proposed", "Confidence", "Source", "Status", "Decision"]

    def __init__(self, current: DesignSpecification, parsed: ParsedRequestResult, parent=None) -> None:
        super().__init__(parent)
        self.current = current
        self.parsed = parsed
        self.setWindowTitle("Review Proposed Specification")
        self.resize(980, 520)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(len(parsed.extracted_fields), len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self._decision_widgets: list[QComboBox] = []
        current_data = current.model_dump(mode="json")
        for row, field in enumerate(parsed.extracted_fields):
            current_value = self._get_path(current_data, field.field_path)
            values = [
                field.field_path,
                str(current_value),
                str(field.value),
                f"{field.confidence:.2f} ({field.confidence_category.value})",
                field.source.value,
                "unsupported" if field.status == "unsupported" else "confirmation required" if field.requires_confirmation else "proposed",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 2:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.table.setItem(row, col, item)
            combo = QComboBox()
            combo.addItems(["accepted", "rejected", "edited"])
            combo.setCurrentText("rejected" if field.requires_confirmation else "accepted")
            self._decision_widgets.append(combo)
            self.table.setCellWidget(row, 6, combo)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.accept_high_button = QPushButton("Accept High Confidence")
        self.reject_all_button = QPushButton("Reject All")
        self.reset_button = QPushButton("Reset Proposal")
        self.approve_button = QPushButton("Approve Resolved Specification")
        self.cancel_button = QPushButton("Cancel")
        for button in (self.accept_high_button, self.reject_all_button, self.reset_button):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(self.approve_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.accept_high_button.clicked.connect(self.accept_high_confidence)
        self.reject_all_button.clicked.connect(self.reject_all)
        self.reset_button.clicked.connect(self.reset_decisions)
        self.approve_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def decisions(self) -> list[FieldReviewDecision]:
        result = []
        for row, field in enumerate(self.parsed.extracted_fields):
            decision = self._decision_widgets[row].currentText()
            proposed_text = self.table.item(row, 2).text()
            edited = self._parse_edit(proposed_text) if proposed_text != str(field.value) else None
            result.append(
                FieldReviewDecision(
                    field_path=field.field_path,
                    decision="edited" if decision == "edited" or edited is not None else decision,
                    edited_value=edited,
                )
            )
        return result

    def accept_high_confidence(self) -> None:
        for field, combo in zip(self.parsed.extracted_fields, self._decision_widgets):
            if field.confidence >= 0.90 and not field.requires_confirmation:
                combo.setCurrentText("accepted")

    def reject_all(self) -> None:
        for combo in self._decision_widgets:
            combo.setCurrentText("rejected")

    def reset_decisions(self) -> None:
        for field, combo in zip(self.parsed.extracted_fields, self._decision_widgets):
            combo.setCurrentText("rejected" if field.requires_confirmation else "accepted")

    def _get_path(self, data: dict, dotted: str):
        target = data
        for part in dotted.split("."):
            if not isinstance(target, dict):
                return ""
            target = target.get(part, "")
        return target

    def _parse_edit(self, text: str):
        try:
            return json.loads(text)
        except Exception:
            lowered = text.strip().lower()
            if lowered in {"true", "false"}:
                return lowered == "true"
            try:
                return float(text)
            except ValueError:
                return text
