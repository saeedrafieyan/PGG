"""Domain models."""

from porous_designer.domain.enums import (
    DomainShape,
    ErrorCode,
    ExportFormat,
    FeasibilityStatus,
    LLMMode,
    RunStatus,
    Severity,
    StructureFamily,
    ValidationStatus,
)
from porous_designer.domain.specification import DesignSpecification, load_legacy_spec

__all__ = [
    "DesignSpecification",
    "load_legacy_spec",
    "DomainShape",
    "StructureFamily",
    "ExportFormat",
    "RunStatus",
    "ValidationStatus",
    "Severity",
    "FeasibilityStatus",
    "ErrorCode",
    "LLMMode",
]
