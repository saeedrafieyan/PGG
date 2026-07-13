"""Unit normalization helpers for natural-language parsing."""

from __future__ import annotations


def length_to_mm(value: float, unit: str | None) -> float:
    normalized = (unit or "mm").lower().strip()
    if normalized in {"mm", "millimeter", "millimeters", "millimetre", "millimetres"}:
        return float(value)
    if normalized in {"cm", "centimeter", "centimeters", "centimetre", "centimetres"}:
        return float(value) * 10.0
    if normalized in {"m", "meter", "meters", "metre", "metres"}:
        return float(value) * 1000.0
    raise ValueError(f"Unsupported length unit: {unit}")


def porosity_to_fraction(value: float) -> float:
    number = float(value)
    if number > 1.0:
        number /= 100.0
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"Porosity must be between 0 and 1, got {number}.")
    return number
