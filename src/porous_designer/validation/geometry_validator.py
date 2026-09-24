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
    *,
    undersize_is_warning: bool = False,
) -> list[ValidationCheck]:
    """Compare the mesh bounding box with the domain bounding box.

    A curved or scanned domain touches its bounding box only at points or
    lines; a pore that happens to sit there makes the porous part slightly
    smaller without anything being wrong. With ``undersize_is_warning`` such
    a shortfall is reported as a warning, while an oversize part (material
    outside the domain) always fails.
    """
    achieved = np.array(bounds_max) - np.array(bounds_min)
    checks = []
    names = ["X", "Y", "Z"]
    for i, name in enumerate(names):
        exp = expected_dims[i]
        ach = float(achieved[i])
        ok = abs(ach - exp) <= tolerance_mm
        soft = not ok and undersize_is_warning and ach < exp
        if ok:
            status, severity, message = ValidationStatus.PASS, Severity.INFO, f"{name} dimension within tolerance."
        elif soft:
            status, severity = ValidationStatus.WARNING, Severity.WARNING
            message = f"{name} extent is {exp - ach:.3f} mm short of the domain: pores lie on the domain's extreme points. Add a solid skin if the full size is needed."
        else:
            status, severity, message = ValidationStatus.FAIL, Severity.CRITICAL, f"{name} dimension outside tolerance."
        checks.append(
            ValidationCheck(
                name=f"domain_dimension_{name.lower()}_mm",
                requested_value=exp,
                achieved_value=round(ach, 4),
                units="mm",
                tolerance=tolerance_mm,
                status=status,
                severity=severity,
                method="mesh bounding box",
                message=message,
            )
        )
    return checks


def add_checks_to_report(report: ValidationReport, checks: list[ValidationCheck]) -> None:
    for c in checks:
        report.add_check(c)
