"""Shared blackboard state object."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from porous_designer.domain.actions import RepairRecord
from porous_designer.domain.enums import RunStatus
from porous_designer.domain.run_state import (
    AmbiguityRecord,
    CandidateRecord,
    FeasibilityResult,
    SoftwareEnvironment,
    StrategyResult,
    StructuredError,
)
from porous_designer.domain.specification import DesignSpecification
from porous_designer.domain.validation import ValidationReport


class Blackboard(BaseModel):
    """Central shared state for all agents and services."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: RunStatus = RunStatus.CREATED
    raw_request: str = ""
    parsed_specification: dict[str, Any] | None = None
    approved_specification: dict[str, Any] | None = None
    ambiguities: list[AmbiguityRecord] = Field(default_factory=list)
    feasibility: FeasibilityResult | None = None
    selected_strategy: StrategyResult | None = None
    candidate_history: list[CandidateRecord] = Field(default_factory=list)
    active_candidate: CandidateRecord | None = None
    geometry_metrics: dict[str, Any] = Field(default_factory=dict)
    mesh_metrics: dict[str, Any] = Field(default_factory=dict)
    connectivity_metrics: dict[str, Any] = Field(default_factory=dict)
    thickness_metrics: dict[str, Any] = Field(default_factory=dict)
    export_results: dict[str, Any] = Field(default_factory=dict)
    validation_report: dict[str, Any] | None = None
    repair_history: list[RepairRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[StructuredError] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    software_environment: SoftwareEnvironment = Field(default_factory=SoftwareEnvironment)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def set_parsed_spec(self, spec: DesignSpecification) -> None:
        self.parsed_specification = spec.model_dump(mode="json")
        self.touch()

    def set_approved_spec(self, spec: DesignSpecification) -> None:
        self.approved_specification = spec.model_dump(mode="json")
        self.touch()

    def get_approved_spec(self) -> DesignSpecification | None:
        if self.approved_specification is None:
            return None
        return DesignSpecification.model_validate(self.approved_specification)

    def get_validation_report(self) -> ValidationReport | None:
        if self.validation_report is None:
            return None
        return ValidationReport.model_validate(self.validation_report)

    def set_validation_report(self, report: ValidationReport) -> None:
        self.validation_report = report.model_dump(mode="json")
        self.touch()

    def add_event(self, event_type: str, message: str, **data: Any) -> None:
        self.events.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": event_type,
                "message": message,
                "status": self.status.value,
                **data,
            }
        )
        self.touch()

    def add_error(
        self,
        code: str,
        stage: str,
        message: str,
        *,
        technical_details: str = "",
        suggested_action: str = "",
        repair_allowed: bool = False,
    ) -> None:
        self.errors.append(
            StructuredError(
                code=code,
                stage=stage,
                message=message,
                technical_details=technical_details,
                suggested_action=suggested_action,
                repair_allowed=repair_allowed,
            )
        )
        self.touch()

    def unresolved_ambiguities(self) -> list[AmbiguityRecord]:
        return [a for a in self.ambiguities if not a.user_confirmed and a.resolved is None]

    def critical_ambiguities_resolved(self) -> bool:
        return len(self.unresolved_ambiguities()) == 0
