"""Bounding-box and domain geometry validation."""

from __future__ import annotations

from typing import Sequence

import numpy as np

from porous_designer.domain.enums import Severity, ValidationStatus
from porous_designer.domain.validation import ValidationCheck, ValidationReport


def validate_dimensions(
    bounds_min: Sequence[float],
    bounds_max: Sequence[float],
    expected_dims: Sequence[float],
    tolerance_mm: float,
) -> list[ValidationCheck]:
    achieved = np.array(bounds_max) - np.array(bounds_min)
    checks = []
    names = ["X", "Y", "Z"]
    for i, name in enumerate(names):
        exp = expected_dims[i]
        ach = float(achieved[i])
        ok = abs(ach - exp) <= tolerance_mm
        checks.append(
            ValidationCheck(
                name=f"domain_dimension_{name.lower()}_mm",
                requested_value=exp,
                achieved_value=round(ach, 4),
                units="mm",
                tolerance=tolerance_mm,
                status=ValidationStatus.PASS if ok else ValidationStatus.FAIL,
                severity=Severity.CRITICAL if not ok else Severity.INFO,
                method="mesh bounding box",
                message=f"{name} dimension {'within' if ok else 'outside'} tolerance.",
            )
        )
    return checks


def add_checks_to_report(report: ValidationReport, checks: list[ValidationCheck]) -> None:
    for c in checks:
        report.add_check(c)
