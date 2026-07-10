"""Validation report models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from porous_designer.domain.enums import Severity, ValidationStatus


class ValidationCheck(BaseModel):
    """Single validation measurement with explicit method documentation."""

    name: str
    requested_value: str | float | None = None
    achieved_value: str | float | None = None
    units: str = ""
    tolerance: str | float | None = None
    status: ValidationStatus = ValidationStatus.NOT_MEASURED
    severity: Severity = Severity.INFO
    method: str = Field(description="How this measurement was obtained.")
    message: str = ""


class ValidationReport(BaseModel):
    """Unified validation report aggregating all checks."""

    schema_version: str = "1.0"
    run_id: str = ""
    overall_status: ValidationStatus = ValidationStatus.NOT_MEASURED
    checks: list[ValidationCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def add_check(self, check: ValidationCheck) -> None:
        self.checks.append(check)
        if check.status == ValidationStatus.FAIL:
            if check.severity in (Severity.ERROR, Severity.CRITICAL):
                self.errors.append(f"{check.name}: {check.message}")
            else:
                self.warnings.append(f"{check.name}: {check.message}")

    def compute_overall_status(self) -> ValidationStatus:
        if any(c.status == ValidationStatus.FAIL for c in self.checks):
            self.overall_status = ValidationStatus.FAIL
        elif any(c.status == ValidationStatus.WARNING for c in self.checks):
            self.overall_status = ValidationStatus.WARNING
        elif all(c.status == ValidationStatus.PASS for c in self.checks if c.status != ValidationStatus.NOT_MEASURED):
            measured = [c for c in self.checks if c.status != ValidationStatus.NOT_MEASURED]
            self.overall_status = ValidationStatus.PASS if measured else ValidationStatus.NOT_MEASURED
        else:
            self.overall_status = ValidationStatus.NOT_MEASURED
        return self.overall_status

    @property
    def passed(self) -> bool:
        return self.compute_overall_status() == ValidationStatus.PASS
