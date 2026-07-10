"""Bounded repair actions — explicit allowed operations."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RepairActionType(str, Enum):
    ADJUST_LATTICE_SPACING = "adjust_lattice_spacing"
    ADJUST_TPMS_LEVEL_SET = "adjust_tpms_level_set"
    ADJUST_UNIT_CELL_SIZE = "adjust_unit_cell_size"
    INCREASE_VOXEL_RESOLUTION = "increase_voxel_resolution"
    DECREASE_VOXEL_RESOLUTION = "decrease_voxel_resolution"
    INCREASE_MESH_SMOOTHING = "increase_mesh_smoothing"
    DECREASE_MESH_SMOOTHING = "decrease_mesh_smoothing"
    CHANGE_BOOLEAN_BATCH_SIZE = "change_boolean_batch_size"
    RETRY_STEP_EXPORT = "retry_step_export"
    DISABLE_STEP_EXPORT = "disable_step_export"
    SWITCH_TO_STL_ONLY = "switch_to_stl_only"
    REGENERATE_WITH_BOUNDARY_PADDING = "regenerate_with_boundary_padding"
    REJECT_CANDIDATE = "reject_candidate"


class RepairAction(BaseModel):
    """A single bounded repair action with preconditions and limits."""

    action: RepairActionType
    parameter: str = ""
    delta: float | None = None
    new_value: float | None = None
    expected_effect: str = ""
    max_retries: int = Field(default=2, ge=0, le=5)
    preconditions: list[str] = Field(default_factory=list)
    rollback_on_failure: bool = True


class RepairRecord(BaseModel):
    """History entry for a repair attempt."""

    attempt: int
    action: RepairAction
    previous_parameters: dict[str, Any] = Field(default_factory=dict)
    observed_failure: str = ""
    resulting_metrics: dict[str, Any] = Field(default_factory=dict)
    improved: bool | None = None
    message: str = ""


# Preconditions registry for deterministic repair selection
ACTION_REGISTRY: dict[RepairActionType, dict[str, Any]] = {
    RepairActionType.ADJUST_LATTICE_SPACING: {
        "applies_to": ["porosity_mismatch", "throat_violation"],
        "max_retries": 5,
        "allowed_range_factor": (0.5, 3.0),  # relative to pore diameter
    },
    RepairActionType.ADJUST_TPMS_LEVEL_SET: {
        "applies_to": ["porosity_mismatch"],
        "max_retries": 5,
        "allowed_range": (-1.5, 1.5),
    },
    RepairActionType.INCREASE_VOXEL_RESOLUTION: {
        "applies_to": ["mesh_defect", "thickness_uncertain"],
        "max_retries": 2,
        "min_resolution_mm": 0.02,
    },
    RepairActionType.DISABLE_STEP_EXPORT: {
        "applies_to": ["step_boolean_failure", "step_validation_failure"],
        "max_retries": 1,
    },
    RepairActionType.REJECT_CANDIDATE: {
        "applies_to": ["unrecoverable"],
        "max_retries": 1,
    },
}


def allowed_actions_for_failure(failure_code: str) -> list[RepairActionType]:
    """Return repair actions allowed for a given failure code."""
    result = []
    for action, meta in ACTION_REGISTRY.items():
        if failure_code in meta.get("applies_to", []):
            result.append(action)
    return result
