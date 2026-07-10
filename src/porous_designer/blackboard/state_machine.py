"""Validated blackboard state transitions."""

from __future__ import annotations

from porous_designer.blackboard.events import EventType
from porous_designer.blackboard.state import Blackboard
from porous_designer.domain.enums import RunStatus


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""


# Valid transitions: from_status -> set of allowed to_status
TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.PARSING, RunStatus.CANCELLED},
    RunStatus.PARSING: {
        RunStatus.NEEDS_USER_REVIEW,
        RunStatus.SPECIFICATION_APPROVED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.NEEDS_USER_REVIEW: {
        RunStatus.SPECIFICATION_APPROVED,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
    },
    RunStatus.SPECIFICATION_APPROVED: {
        RunStatus.FEASIBILITY_CHECKING,
        RunStatus.CANCELLED,
    },
    RunStatus.FEASIBILITY_CHECKING: {
        RunStatus.INFEASIBLE,
        RunStatus.PREVIEW_GENERATING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.INFEASIBLE: {RunStatus.NEEDS_USER_REVIEW, RunStatus.CANCELLED},
    RunStatus.PREVIEW_GENERATING: {
        RunStatus.PREVIEW_READY,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.PREVIEW_READY: {
        RunStatus.FINAL_GENERATING,
        RunStatus.NEEDS_USER_REVIEW,
        RunStatus.CANCELLED,
    },
    RunStatus.FINAL_GENERATING: {
        RunStatus.VALIDATING,
        RunStatus.REPAIRING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.VALIDATING: {
        RunStatus.PASSED,
        RunStatus.REPAIRING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.REPAIRING: {
        RunStatus.FINAL_GENERATING,
        RunStatus.VALIDATING,
        RunStatus.FAILED,
        RunStatus.INFEASIBLE,
        RunStatus.CANCELLED,
    },
    RunStatus.PASSED: {RunStatus.EXPORTED, RunStatus.CANCELLED},
    RunStatus.FAILED: {RunStatus.NEEDS_USER_REVIEW, RunStatus.CANCELLED},
    RunStatus.EXPORTED: set(),
    RunStatus.CANCELLED: set(),
}


class StateMachine:
    """Enforces valid blackboard state transitions."""

    def __init__(self, blackboard: Blackboard) -> None:
        self._bb = blackboard

    @property
    def status(self) -> RunStatus:
        return self._bb.status

    def can_transition(self, to_status: RunStatus) -> bool:
        allowed = TRANSITIONS.get(self._bb.status, set())
        return to_status in allowed

    def transition(
        self,
        to_status: RunStatus,
        message: str = "",
        event_type: EventType | None = None,
    ) -> None:
        if not self.can_transition(to_status):
            raise InvalidTransitionError(
                f"Cannot transition from {self._bb.status.value} to {to_status.value}"
            )
        from_status = self._bb.status
        self._bb.status = to_status
        self._bb.add_event(
            event_type.value if event_type else "state_transition",
            message or f"{from_status.value} -> {to_status.value}",
            from_status=from_status.value,
            to_status=to_status.value,
        )

    def cancel(self, message: str = "User cancelled") -> None:
        if self._bb.status == RunStatus.CANCELLED:
            return
        if RunStatus.CANCELLED not in TRANSITIONS.get(self._bb.status, set()) and self._bb.status != RunStatus.EXPORTED:
            # Force cancel from any non-terminal state
            self._bb.status = RunStatus.CANCELLED
        else:
            self.transition(RunStatus.CANCELLED, message, EventType.RUN_CANCELLED)
