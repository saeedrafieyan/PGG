"""Confidence scoring helpers."""

from __future__ import annotations

from porous_designer.agentic.contracts import ConfidenceCategory, confidence_category


def score_explicit_numeric() -> float:
    return 0.99


def score_explicit_alias() -> float:
    return 0.95


def score_inferred_domain() -> float:
    return 0.82


def score_ambiguous_phrase() -> float:
    return 0.62


def category(confidence: float) -> ConfidenceCategory:
    return confidence_category(confidence)
