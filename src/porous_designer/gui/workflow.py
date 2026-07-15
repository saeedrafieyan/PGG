"""GUI workflow modes and specification authority metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from porous_designer.domain.specification import DesignSpecification


class ApplicationMode(str, Enum):
    MANUAL_DESIGN = "manual_design"
    AGENTIC_DESIGN = "agentic_design"


class ManualWorkflowState(str, Enum):
    MANUAL_EMPTY = "manual_empty"
    MANUAL_EDITING = "manual_editing"
    MANUAL_VALID = "manual_valid"
    MANUAL_ESTIMATED = "manual_estimated"
    MANUAL_PREVIEWED = "manual_previewed"
    MANUAL_FINAL_GENERATED = "manual_final_generated"
    MANUAL_FAILED = "manual_failed"


class AgenticWorkflowState(str, Enum):
    AGENTIC_REQUEST_EMPTY = "agentic_request_empty"
    AGENTIC_REQUEST_DRAFT = "agentic_request_draft"
    AGENTIC_PARSING = "agentic_parsing"
    AGENTIC_EXTERNAL_INTERPRETATION = "agentic_external_interpretation"
    AGENTIC_CLARIFICATION_REQUIRED = "agentic_clarification_required"
    AGENTIC_PROPOSAL_READY = "agentic_proposal_ready"
    AGENTIC_REVIEWING = "agentic_reviewing"
    AGENTIC_APPROVED = "agentic_approved"
    AGENTIC_APPROVAL_STALE = "agentic_approval_stale"
    AGENTIC_ESTIMATED = "agentic_estimated"
    AGENTIC_PREVIEWED = "agentic_previewed"
    AGENTIC_FAILED = "agentic_failed"


@dataclass
class SpecificationRevision:
    specification_id: str
    revision: int
    origin: str
    approval_status: str = "not_required"
    approval_id: str = ""
    approval_timestamp: str = ""
    superseded_revision: int | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_run_metadata(self, mode: ApplicationMode) -> dict[str, Any]:
        return {
            "application_mode": mode.value,
            "specification_id": self.specification_id,
            "specification_revision": self.revision,
            "specification_origin": self.origin,
            "approval_status": self.approval_status,
            "approval_id": self.approval_id,
            "approval_timestamp": self.approval_timestamp,
            "superseded_revision": self.superseded_revision,
            "provenance": self.provenance,
        }


def new_manual_revision(spec: DesignSpecification, *, origin: str = "manual", superseded_revision: int | None = None) -> SpecificationRevision:
    return SpecificationRevision(
        specification_id=spec.request_id,
        revision=1 if superseded_revision is None else superseded_revision + 1,
        origin=origin,
        approval_status="not_required",
        superseded_revision=superseded_revision,
    )


def approved_agentic_revision(spec: DesignSpecification, *, approval_id: str, provider_mode: str, superseded_revision: int | None = None) -> SpecificationRevision:
    return SpecificationRevision(
        specification_id=spec.request_id,
        revision=1 if superseded_revision is None else superseded_revision + 1,
        origin="external_provider" if not provider_mode.startswith("deterministic") else "deterministic_parser",
        approval_status="approved",
        approval_id=approval_id,
        approval_timestamp=datetime.now(timezone.utc).isoformat(),
        superseded_revision=superseded_revision,
        provenance={"provider_mode": provider_mode},
    )
