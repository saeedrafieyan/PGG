"""Run state and provenance models."""

from __future__ import annotations

import platform
import sys
from typing import Any

from pydantic import BaseModel, Field

from porous_designer import __version__


class SoftwareEnvironment(BaseModel):
    python_version: str = Field(default_factory=lambda: sys.version)
    platform: str = Field(default_factory=lambda: platform.platform())
    porous_designer_version: str = Field(default=__version__)
    packages: dict[str, str] = Field(default_factory=dict)
    deterministic_seed: int = 42


class CandidateRecord(BaseModel):
    """A single geometry generation candidate."""

    candidate_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    geometry_metrics: dict[str, Any] = Field(default_factory=dict)
    mesh_metrics: dict[str, Any] = Field(default_factory=dict)
    is_preview: bool = False
    geometry_hash: str | None = None


class AmbiguityRecord(BaseModel):
    term: str
    possible_meanings: list[str] = Field(default_factory=list)
    recommended: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    resolved: str | None = None
    user_confirmed: bool = False


class StructuredError(BaseModel):
    code: str
    stage: str
    message: str
    technical_details: str = ""
    suggested_action: str = ""
    repair_allowed: bool = False


class FeasibilityResult(BaseModel):
    status: str  # feasible | conditionally_feasible | infeasible | unknown
    expected_pore_count: int | None = None
    expected_memory_gb: float | None = None
    expected_runtime_s: float | None = None
    step_complexity: str = ""
    incompatible_constraints: list[str] = Field(default_factory=list)
    recommended_changes: list[str] = Field(default_factory=list)
    explanation: str = ""


class StrategyResult(BaseModel):
    generator: str
    geometry_backend: str = "voxel_sdf"
    porosity_control_parameter: str = ""
    preview_resolution_mm: float = 0.10
    final_resolution_mm: float = 0.04
    step_backend: str | None = None
    validation_profile: str = "default"
