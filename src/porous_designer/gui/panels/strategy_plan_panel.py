"""Agentic strategy plan review panel."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from porous_designer.agentic.strategy import StrategyPlan


class StrategyPlanPanel(QWidget):
    generate_requested = Signal()
    approve_requested = Signal()
    reject_requested = Signal()
    regenerate_requested = Signal()
    export_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.status = QLabel("No approved specification.")
        self.status.setWordWrap(True)
        self.generate_button = QPushButton("Generate Strategy Plan")
        self.approve_button = QPushButton("Approve Plan")
        self.reject_button = QPushButton("Reject Plan")
        self.regenerate_button = QPushButton("Regenerate Plan")
        self.export_button = QPushButton("Export Plan JSON")
        self.plan_text = QTextEdit()
        self.plan_text.setReadOnly(True)
        self.plan_text.setMinimumHeight(260)
        buttons = QHBoxLayout()
        for button in (
            self.generate_button,
            self.approve_button,
            self.reject_button,
            self.regenerate_button,
            self.export_button,
        ):
            buttons.addWidget(button)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        layout.addWidget(self.plan_text)
        self.generate_button.clicked.connect(self.generate_requested)
        self.approve_button.clicked.connect(self.approve_requested)
        self.reject_button.clicked.connect(self.reject_requested)
        self.regenerate_button.clicked.connect(self.regenerate_requested)
        self.export_button.clicked.connect(self.export_requested)
        self.set_plan(None)

    def set_specification_available(self, available: bool) -> None:
        self.generate_button.setEnabled(available)
        if not available:
            self.status.setText("No approved specification.")
            self.set_plan(None)

    def set_plan(self, plan: StrategyPlan | None) -> None:
        if plan is None:
            self.status.setText("No strategy plan generated.")
            self.plan_text.setPlainText("")
            self.approve_button.setEnabled(False)
            self.reject_button.setEnabled(False)
            self.regenerate_button.setEnabled(False)
            self.export_button.setEnabled(False)
            return
        self.status.setText(f"Plan {plan.plan_id} - {plan.status}")
        self.plan_text.setPlainText(self._format_plan(plan))
        self.approve_button.setEnabled(plan.status in {"needs_review", "draft", "rejected"})
        self.reject_button.setEnabled(plan.status in {"needs_review", "draft", "approved"})
        self.regenerate_button.setEnabled(plan.status != "approved")
        self.export_button.setEnabled(True)

    def _format_plan(self, plan: StrategyPlan) -> str:
        lines = [
            f"Summary: {plan.summary}",
            f"Specification: {plan.specification_id} revision {plan.specification_revision}",
            f"Planner: {plan.planner_source} ({plan.provider} / {plan.model})",
            "",
            "Steps:",
        ]
        for step in plan.steps:
            tool = step.deterministic_tool or "user_checkpoint"
            lines.append(f"{step.step_id}. {step.title} [{tool}] - {step.execution_status}")
            lines.append(f"  Purpose: {step.purpose}")
        lines.append("")
        lines.append("Validation gates:")
        lines.extend(f"- {gate.title}: {', '.join(gate.checks)}" for gate in plan.validation_gates)
        lines.append("")
        lines.append("User checkpoints:")
        lines.extend(f"- {checkpoint.title} before {checkpoint.required_before}" for checkpoint in plan.user_checkpoints)
        lines.append("")
        lines.append("Unsupported requests:")
        lines.extend(f"- {note.feature}: {note.explanation}" for note in plan.unsupported_requirements)
        if not plan.unsupported_requirements:
            lines.append("- none")
        lines.append("")
        lines.append("Risks:")
        lines.extend(f"- {risk.severity}: {risk.description}" for risk in plan.risks)
        lines.append("")
        lines.append("Assumptions:")
        lines.extend(f"- {assumption.description}" for assumption in plan.assumptions)
        if plan.provider_explanation:
            lines.extend(["", f"Provider explanation: {plan.provider_explanation}"])
        return "\n".join(lines)
