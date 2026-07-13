"""Agent-assisted natural-language request panel."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from porous_designer.agentic.contracts import ParsedRequestResult
from porous_designer.gui.models.ambiguity_model import AmbiguityModel
from porous_designer.gui.models.extracted_fields_model import ExtractedFieldsModel


EXAMPLES = [
    "Generate an 8 x 14 x 8 mm scaffold with hexagonal packing, 1 mm pore size, 75-80% porosity, interconnected pores, and STL and STP files.",
    "Create a 10 x 10 x 5 mm HCP spherical-pore scaffold with 1.2 mm generating sphere diameter and 72% target porosity. Require pore percolation in X, Y, and Z.",
    "Generate a 12 x 12 x 6 mm gyroid scaffold with a 2 mm unit-cell size and 70% porosity.",
    "Create a cylindrical diamond TPMS scaffold, 8 mm diameter and 12 mm high, with 65% porosity.",
    "Create a scaffold with 1 mm pore size and hexagonal layout.",
    "Create a STEP-only scaffold with no STL output.",
]


class AgenticRequestPanel(QWidget):
    parse_requested = Signal(str)
    review_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._example_index = 0
        layout = QVBoxLayout(self)
        self.privacy_notice = QLabel(
            "Agent-assisted parsing is deterministic by default. External agent access is disabled unless explicitly configured; do not send files, meshes, paths, or credentials."
        )
        self.privacy_notice.setWordWrap(True)
        layout.addWidget(self.privacy_notice)
        self.request_text = QTextEdit()
        self.request_text.setPlaceholderText("Describe the porous scaffold requirements in natural language.")
        self.request_text.setMinimumHeight(90)
        layout.addWidget(self.request_text)
        buttons = QHBoxLayout()
        self.parse_button = QPushButton("Parse Request")
        self.clear_button = QPushButton("Clear")
        self.example_button = QPushButton("Load Example")
        buttons.addWidget(self.parse_button)
        buttons.addWidget(self.clear_button)
        buttons.addWidget(self.example_button)
        layout.addLayout(buttons)
        self.mode_label = QLabel("Parser mode: Structured-only mode")
        self.provider_label = QLabel("Provider: deterministic parser, no network")
        self.confidence_label = QLabel("Confidence: no parsed fields")
        self.ambiguity_label = QLabel("Unresolved ambiguities: 0")
        for label in (self.mode_label, self.provider_label, self.confidence_label, self.ambiguity_label):
            label.setWordWrap(True)
            layout.addWidget(label)
        self.fields_model = ExtractedFieldsModel()
        self.fields_view = QTableView()
        self.fields_view.setModel(self.fields_model)
        self.fields_view.setMinimumHeight(120)
        layout.addWidget(self.fields_view)
        self.ambiguity_model = AmbiguityModel()
        self.ambiguity_view = QTableView()
        self.ambiguity_view.setModel(self.ambiguity_model)
        self.ambiguity_view.setMinimumHeight(90)
        layout.addWidget(self.ambiguity_view)
        self.review_button = QPushButton("Review Proposed Specification")
        self.review_button.setEnabled(False)
        layout.addWidget(self.review_button)

        self.parse_button.clicked.connect(lambda: self.parse_requested.emit(self.request_text.toPlainText()))
        self.clear_button.clicked.connect(self.clear)
        self.example_button.clicked.connect(self.load_example)
        self.review_button.clicked.connect(self.review_requested)

    def load_example(self) -> None:
        self.request_text.setPlainText(EXAMPLES[self._example_index % len(EXAMPLES)])
        self._example_index += 1

    def clear(self) -> None:
        self.request_text.clear()
        self.set_result(None, "Request not parsed", "deterministic parser, no network")

    def set_busy(self, busy: bool) -> None:
        self.parse_button.setEnabled(not busy)
        self.mode_label.setText("Parser mode: Parsing" if busy else self.mode_label.text())

    def set_result(self, result: ParsedRequestResult | None, status: str, provider_status: str) -> None:
        self.mode_label.setText(f"Parser mode: {status}")
        self.provider_label.setText(f"Provider: {provider_status}")
        if result is None:
            self.fields_model.set_fields([])
            self.ambiguity_model.set_ambiguities([])
            self.confidence_label.setText("Confidence: no parsed fields")
            self.ambiguity_label.setText("Unresolved ambiguities: 0")
            self.review_button.setEnabled(False)
            return
        self.fields_model.set_fields(result.extracted_fields)
        self.ambiguity_model.set_ambiguities(result.ambiguities)
        if result.extracted_fields:
            avg = sum(field.confidence for field in result.extracted_fields) / len(result.extracted_fields)
            self.confidence_label.setText(f"Confidence: {len(result.extracted_fields)} fields, average {avg:.2f}")
        else:
            self.confidence_label.setText("Confidence: no parsed fields")
        unresolved = sum(1 for item in result.ambiguities if item.mandatory and not item.resolved_choice)
        self.ambiguity_label.setText(f"Unresolved ambiguities: {unresolved}")
        self.review_button.setEnabled(bool(result.extracted_fields))
