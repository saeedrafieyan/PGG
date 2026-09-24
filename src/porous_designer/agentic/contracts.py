"""Strict contracts for natural-language request interpretation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily, TPMSVariant


class FieldSource(str, Enum):
    DETERMINISTIC = "deterministic"
    LLM_RECOMMENDATION = "llm_recommendation"
    USER_EDIT = "user_edit"
    DEFAULT = "default"


class AgenticWorkflowStatus(str, Enum):
    STRUCTURED_ONLY = "Structured-only mode"
    REQUEST_NOT_PARSED = "Request not parsed"
    PARSING = "Parsing"
    REVIEW_REQUIRED = "Review required"
    AMBIGUITIES_UNRESOLVED = "Ambiguities unresolved"
    READY_FOR_APPROVAL = "Ready for approval"
    HUMAN_APPROVED = "Human approved"
    APPROVAL_STALE = "Approval stale"
    PARSER_FAILED = "Parser failed"
    DETERMINISTIC_FALLBACK_ACTIVE = "Deterministic fallback active"


class ProviderMode(str, Enum):
    DETERMINISTIC_ONLY = "deterministic"
    OPENROUTER = "openrouter"


class ProviderErrorCategory(str, Enum):
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    PROVIDER_AUTHENTICATION_FAILED = "PROVIDER_AUTHENTICATION_FAILED"
    PROVIDER_MODEL_UNAVAILABLE = "PROVIDER_MODEL_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_QUOTA_EXCEEDED = "PROVIDER_QUOTA_EXCEEDED"
    PROVIDER_NETWORK_ERROR = "PROVIDER_NETWORK_ERROR"
    PROVIDER_SCHEMA_INVALID = "PROVIDER_SCHEMA_INVALID"
    PROVIDER_REFUSAL = "PROVIDER_REFUSAL"
    PROVIDER_CONTENT_FILTERED = "PROVIDER_CONTENT_FILTERED"
    PROVIDER_INTERNAL_ERROR = "PROVIDER_INTERNAL_ERROR"
    PROVIDER_CANCELLED = "PROVIDER_CANCELLED"
    PROVIDER_ESCALATION_DECLINED = "PROVIDER_ESCALATION_DECLINED"
    PROVIDER_CACHE_INVALID = "PROVIDER_CACHE_INVALID"
    PROVIDER_REQUEST_INVALID = "PROVIDER_REQUEST_INVALID"
    PROVIDER_OUTPUT_UNGROUNDED = "PROVIDER_OUTPUT_UNGROUNDED"


class ExternalCallDecisionCode(str, Enum):
    NO_EXTERNAL_CALL_REQUIRED = "NO_EXTERNAL_CALL_REQUIRED"
    EXTERNAL_CALL_RECOMMENDED = "EXTERNAL_CALL_RECOMMENDED"
    EXTERNAL_CALL_REQUIRED_FOR_INTERPRETATION = "EXTERNAL_CALL_REQUIRED_FOR_INTERPRETATION"
    EXTERNAL_ACCESS_DISABLED = "EXTERNAL_ACCESS_DISABLED"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class ConfidenceCategory(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


ALLOWED_FIELD_PATHS = {
    "domain.shape",
    "domain.dimensions_mm",
    "structure.family",
    "structure.pore_diameter_mm",
    "structure.unit_cell_size_mm",
    "structure.tpms_variant",
    "targets.porosity_target.target",
    "targets.porosity_target.min_value",
    "targets.porosity_target.max_value",
    "constraints.require_open_pores",
    "constraints.minimum_wall_thickness_mm",
    "constraints.minimum_throat_size_mm",
    "generation.preview_resolution_mm",
    "generation.final_resolution_mm",
    "export.formats",
    "manufacturing.process",
}


def confidence_category(confidence: float) -> ConfidenceCategory:
    if confidence >= 0.90:
        return ConfidenceCategory.HIGH
    if confidence >= 0.70:
        return ConfidenceCategory.MODERATE
    return ConfidenceCategory.LOW


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParserEvidence(StrictModel):
    source_text: str
    rule: str
    normalized_value: Any
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedField(StrictModel):
    field_path: str
    value: Any
    unit: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_category: ConfidenceCategory | None = None
    source_text: str = ""
    source: FieldSource = FieldSource.DETERMINISTIC
    requires_confirmation: bool = False
    status: Literal["proposed", "accepted", "rejected", "unsupported", "missing"] = "proposed"

    @field_validator("field_path")
    @classmethod
    def known_field_path(cls, value: str) -> str:
        if value not in ALLOWED_FIELD_PATHS:
            raise ValueError(f"Unknown proposed field path: {value}")
        return value

    @field_validator("value")
    @classmethod
    def reject_executable_code(cls, value: Any) -> Any:
        text = str(value).lower()
        blocked = ("import os", "subprocess", "exec(", "eval(", "__import__", "open(", "powershell", "cmd.exe")
        if any(token in text for token in blocked):
            raise ValueError("Executable code is not allowed in parsed request fields.")
        return value

    def model_post_init(self, __context: Any) -> None:
        if self.confidence_category is None:
            object.__setattr__(self, "confidence_category", confidence_category(self.confidence))


class AmbiguityItem(StrictModel):
    identifier: str
    source_phrase: str
    explanation: str
    candidate_interpretations: list[str]
    recommended_choice: str
    recommendation_rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    mandatory: bool = True
    resolved_choice: str | None = None


class MissingRequirement(StrictModel):
    field_path: str
    explanation: str
    severity: Literal["info", "warning", "blocking"] = "warning"


class UnsupportedRequest(StrictModel):
    feature: str
    source_text: str
    explanation: str
    retained_as_future_requirement: bool = True


class Assumption(StrictModel):
    field_path: str
    value: Any
    rationale: str
    requires_confirmation: bool = True


class ParsedRequestResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    provider_mode: str = "deterministic"
    parser_version: str = "3B.1"
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    ambiguities: list[AmbiguityItem] = Field(default_factory=list)
    missing_requirements: list[MissingRequirement] = Field(default_factory=list)
    unsupported_requests: list[UnsupportedRequest] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    evidence: list[ParserEvidence] = Field(default_factory=list)
    provider_failed: bool = False
    provider_failure_reason: str = ""
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalCallDecision(StrictModel):
    decision_code: ExternalCallDecisionCode
    explanation: str
    unresolved_fields: list[str] = Field(default_factory=list)
    unresolved_ambiguities: list[str] = Field(default_factory=list)
    detected_conflicts: list[str] = Field(default_factory=list)
    unsupported_requests: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ProviderDisagreement(StrictModel):
    field_path: str
    deterministic_value: Any
    provider_value: Any
    deterministic_evidence: str = ""
    provider_evidence: str = ""
    severity: Literal["info", "warning", "blocking"] = "warning"
    required_review: bool = True
    resolution: str | None = None
    resolved_by: str | None = None
    resolved_at: str | None = None


class ProviderError(StrictModel):
    provider: str
    model: str
    category: ProviderErrorCategory
    safe_user_message: str
    retryable: bool = False
    technical_details: str = ""
    redacted_raw_details: str = ""
    fallback_status: str = "deterministic_fallback_available"


class ProviderMetadata(StrictModel):
    provider: str
    model: str
    model_category: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_id: str | None = None
    latency_s: float | None = None
    retries: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    schema_version: str = "1.0"
    completion_status: str = "unknown"
    escalation_status: str = "not_escalated"
    cache_status: str = "miss"


class FeasibilityExplanation(StrictModel):
    deterministic_status: str
    summary: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggested_user_actions: list[str] = Field(default_factory=list)


class FieldReviewDecision(StrictModel):
    field_path: str
    decision: Literal["accepted", "rejected", "edited"] = "accepted"
    edited_value: Any | None = None


class ApprovalRecord(StrictModel):
    approval_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_request: str
    deterministic_extraction: dict[str, Any]
    provider_result: dict[str, Any] | None = None
    ambiguity_resolutions: dict[str, str] = Field(default_factory=dict)
    field_decisions: list[FieldReviewDecision] = Field(default_factory=list)
    final_approved_fields: dict[str, Any] = Field(default_factory=dict)
    approved_specification: dict[str, Any]
    approved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reviewer: str = "local_user"
    provider_mode: str = "deterministic"
    parser_version: str = "3B.1"
    status: Literal["human_approved", "stale"] = "human_approved"


def validate_field_value(field_path: str, value: Any) -> Any:
    if field_path == "domain.shape":
        return DomainShape(value).value
    if field_path == "structure.family":
        return StructureFamily(value).value
    if field_path == "structure.tpms_variant":
        return TPMSVariant(value).value
    if field_path == "export.formats":
        return [ExportFormat(v).value for v in value]
    if field_path in {
        "domain.dimensions_mm",
    }:
        values = [float(v) for v in value]
        if any(v <= 0 for v in values):
            raise ValueError(f"{field_path} values must be positive.")
        return values
    if field_path in {
        "structure.pore_diameter_mm",
        "structure.unit_cell_size_mm",
        "targets.porosity_target.target",
        "targets.porosity_target.min_value",
        "targets.porosity_target.max_value",
        "constraints.minimum_wall_thickness_mm",
        "constraints.minimum_throat_size_mm",
        "generation.preview_resolution_mm",
        "generation.final_resolution_mm",
    }:
        number = float(value)
        if number < 0:
            raise ValueError(f"{field_path} must be non-negative.")
        if "porosity_target" in field_path and not 0.0 <= number <= 1.0:
            raise ValueError(f"{field_path} must be a fraction in [0, 1].")
        return number
    if field_path == "constraints.require_open_pores":
        return bool(value)
    if field_path == "manufacturing.process":
        return str(value)
    return value
