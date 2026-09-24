"""Unit normalization helpers for natural-language parsing."""

from __future__ import annotations

_LENGTH_FACTORS_TO_MM: dict[str, float] = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "millimetre": 1.0,
    "millimetres": 1.0,
    "cm": 10.0,
    "centimeter": 10.0,
    "centimeters": 10.0,
    "centimetre": 10.0,
    "centimetres": 10.0,
    "m": 1000.0,
    "meter": 1000.0,
    "meters": 1000.0,
    "metre": 1000.0,
    "metres": 1000.0,
    "um": 0.001,
    "µm": 0.001,
    "μm": 0.001,
    "micron": 0.001,
    "microns": 0.001,
    "micrometer": 0.001,
    "micrometers": 0.001,
    "micrometre": 0.001,
    "micrometres": 0.001,
}

# Regex alternation for length units, longest first so "mm" wins over "m" and
# "microns" wins over "micron". Callers must follow it with a word boundary so
# that e.g. the "m" of "microns" is never read as metres.
LENGTH_UNIT_PATTERN = "|".join(
    sorted(
        {"[µμ]m" if unit in {"µm", "μm"} else unit for unit in _LENGTH_FACTORS_TO_MM},
        key=len,
        reverse=True,
    )
)


def length_to_mm(value: float, unit: str | None) -> float:
    normalized = (unit or "mm").lower().strip()
    factor = _LENGTH_FACTORS_TO_MM.get(normalized)
    if factor is None:
        raise ValueError(f"Unsupported length unit: {unit}")
    return float(value) * factor


def is_length_unit(unit: str | None) -> bool:
    return unit is not None and unit.lower().strip() in _LENGTH_FACTORS_TO_MM


def porosity_to_fraction(value: float) -> float:
    number = float(value)
    if number > 1.0:
        number /= 100.0
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"Porosity must be between 0 and 1, got {number}.")
    return number
