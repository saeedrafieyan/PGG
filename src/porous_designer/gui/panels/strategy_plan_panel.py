"""Agentic strategy plan review panel."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget

from porous_designer.agentic.strategy import PlanExecutionSession, PlanObservation, PlanStepExecution, StrategyPlan


class StrategyPlanPanel(QWidget):
    generate_requested = Signal()
    approve_requested = Signal()
    reject_requested = Signal()
    regenerate_requested = Signal()
    export_requested = Signal()
    execute_step_requested = Signal(str)
    skip_step_requested = Signal(str)

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
        self.execution_table = QTableWidget(0, 6)
        self.execution_table.setHorizontalHeaderLabels(["Step", "Tool", "Preconditions", "Status", "Last Result", "Action"])
        self.execution_table.setMinimumHeight(220)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(160)
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
        layout.addWidget(QLabel("Step Execution"))
        layout.addWidget(self.execution_table)
        layout.addWidget(QLabel("Selected Step Details"))
        layout.addWidget(self.details)
        self.generate_button.clicked.connect(self.generate_requested)
        self.approve_button.clicked.connect(self.approve_requested)
        self.reject_button.clicked.connect(self.reject_requested)
        self.regenerate_button.clicked.connect(self.regenerate_requested)
        self.export_button.clicked.connect(self.export_requested)
        self.execution_table.currentCellChanged.connect(lambda row, *_: self._show_step_details(row))
        self.set_plan(None)
        self._plan: StrategyPlan | None = None
        self._executions: dict[str, PlanStepExecution] = {}
        self._observations: dict[str, PlanObservation] = {}

    def set_specification_available(self, available: bool) -> None:
        self.generate_button.setEnabled(available)
        if not available:
            self.status.setText("No approved specification.")
            self.set_plan(None)

    def set_plan(self, plan: StrategyPlan | None) -> None:
        if plan is None:
            self.status.setText("No strategy plan generated.")
            self.plan_text.setPlainText("")
            self.execution_table.setRowCount(0)
            self.details.setPlainText("")
            self.approve_button.setEnabled(False)
            self.reject_button.setEnabled(False)
            self.regenerate_button.setEnabled(False)
            self.export_button.setEnabled(False)
            return
        self._plan = plan
        self.status.setText(f"Plan {plan.plan_id} - {plan.status}")
        self.plan_text.setPlainText(self._format_plan(plan))
        self.approve_button.setEnabled(plan.status in {"needs_review", "draft", "rejected"})
        self.reject_button.setEnabled(plan.status in {"needs_review", "draft", "approved"})
        self.regenerate_button.setEnabled(plan.status != "approved")
        self.export_button.setEnabled(True)
        self.set_execution_state(plan, None, [], [])

    def set_execution_state(
        self,
        plan: StrategyPlan | None,
        session: PlanExecutionSession | None,
        executions: list[PlanStepExecution],
        observations: list[PlanObservation],
    ) -> None:
        self._plan = plan
        self._executions = {item.step_id: item for item in executions}
        self._observations = {item.step_id: item for item in observations}
        self.execution_table.setRowCount(0)
        if plan is None:
            self.details.setPlainText("")
            return
        self.execution_table.setRowCount(len(plan.steps))
        for row, step in enumerate(plan.steps):
            execution = self._executions.get(step.step_id)
            observation = self._observations.get(step.step_id)
            status = execution.status if execution else step.execution_status
            preconditions = execution.precondition_status if execution else "not_checked"
            last_result = observation.status if observation else ""
            self.execution_table.setItem(row, 0, QTableWidgetItem(f"{step.step_id}: {step.title}"))
            self.execution_table.setItem(row, 1, QTableWidgetItem(step.deterministic_tool or "user_checkpoint"))
            self.execution_table.setItem(row, 2, QTableWidgetItem(preconditions))
            self.execution_table.setItem(row, 3, QTableWidgetItem(status.replace("_", " ").title()))
            self.execution_table.setItem(row, 4, QTableWidgetItem(last_result))
            action = QPushButton(self._action_label(step.deterministic_tool))
            action.setEnabled(plan.status == "approved" and step.deterministic_tool is not None and status not in {"running", "completed", "skipped"})
            action.clicked.connect(lambda _checked=False, sid=step.step_id: self.execute_step_requested.emit(sid))
            wrapper = QWidget()
            row_layout = QHBoxLayout(wrapper)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(action)
            if step.deterministic_tool == "run_sensitivity_analysis":
                skip = QPushButton("Skip")
                skip.clicked.connect(lambda _checked=False, sid=step.step_id: self.skip_step_requested.emit(sid))
                row_layout.addWidget(skip)
            self.execution_table.setCellWidget(row, 5, wrapper)
        self.execution_table.resizeColumnsToContents()
        self._show_step_details(max(self.execution_table.currentRow(), 0))

    def _action_label(self, tool: str | None) -> str:
        return {
            "estimate_resources": "Run Estimate",
            "generate_preview": "Generate Preview",
            "validate_preview": "Validate Preview",
            "generate_final": "Generate Final",
            "validate_final": "Validate Final",
            "export_html_report": "Export Report",
            "run_sensitivity_analysis": "Run Sensitivity",
        }.get(tool or "", "No Action")

    def _show_step_details(self, row: int) -> None:
        if self._plan is None or row < 0 or row >= len(self._plan.steps):
            self.details.setPlainText("")
            return
        step = self._plan.steps[row]
        execution = self._executions.get(step.step_id)
        observation = self._observations.get(step.step_id)
        lines = [
            f"Step: {step.step_id} - {step.title}",
            f"Tool: {step.deterministic_tool or 'user_checkpoint'}",
            f"Purpose: {step.purpose}",
            f"Required inputs: {step.required_inputs or ['none']}",
            f"Expected outputs: {step.expected_outputs or ['none']}",
            f"Preconditions: {step.preconditions or ['none']}",
            f"Success criteria: {step.success_criteria or ['none']}",
        ]
        if execution:
            lines.extend(
                [
                    "",
                    f"Execution status: {execution.status}",
                    f"Precondition status: {execution.precondition_status}",
                    f"Run ID: {execution.run_id or ''}",
                    f"Artifacts: {execution.output_artifacts or []}",
                    f"Warnings: {execution.warnings or []}",
                    f"Errors: {execution.errors or []}",
                ]
            )
        if observation:
            lines.extend(
                [
                    "",
                    f"Latest observation: {observation.status}",
                    f"Validation status: {observation.validation_status}",
                    f"Scalar summary: {observation.scalar_result_summary}",
                    f"Observation artifacts: {observation.artifact_paths}",
                    f"Next action: {observation.next_recommended_action}",
                ]
            )
        self.details.setPlainText("\n".join(lines))

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
