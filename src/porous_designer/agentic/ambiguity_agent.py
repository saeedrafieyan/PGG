"""Deterministic ambiguity review helpers."""

from __future__ import annotations

from porous_designer.agentic.contracts import AmbiguityItem, ParsedRequestResult


def unresolved_ambiguities(parsed: ParsedRequestResult) -> list[AmbiguityItem]:
    return [item for item in parsed.ambiguities if item.mandatory and not item.resolved_choice]


def resolve_ambiguity(parsed: ParsedRequestResult, identifier: str, choice: str) -> ParsedRequestResult:
    data = parsed.model_copy(deep=True)
    for item in data.ambiguities:
        if item.identifier == identifier:
            item.resolved_choice = choice
    return data
