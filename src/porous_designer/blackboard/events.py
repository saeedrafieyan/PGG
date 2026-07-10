"""Blackboard event types."""

from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    RUN_CREATED = "run_created"
    PARSING_STARTED = "parsing_started"
    PARSING_COMPLETED = "parsing_completed"
    AMBIGUITY_DETECTED = "ambiguity_detected"
    AMBIGUITY_RESOLVED = "ambiguity_resolved"
    SPECIFICATION_APPROVED = "specification_approved"
    FEASIBILITY_STARTED = "feasibility_started"
    FEASIBILITY_COMPLETED = "feasibility_completed"
    STRATEGY_SELECTED = "strategy_selected"
    PREVIEW_STARTED = "preview_started"
    PREVIEW_COMPLETED = "preview_completed"
    FINAL_GENERATION_STARTED = "final_generation_started"
    FINAL_GENERATION_COMPLETED = "final_generation_completed"
    VALIDATION_STARTED = "validation_started"
    VALIDATION_COMPLETED = "validation_completed"
    REPAIR_STARTED = "repair_started"
    REPAIR_COMPLETED = "repair_completed"
    EXPORT_STARTED = "export_started"
    EXPORT_COMPLETED = "export_completed"
    RUN_CANCELLED = "run_cancelled"
    RUN_FAILED = "run_failed"
    RUN_PASSED = "run_passed"
    PROGRESS = "progress"
