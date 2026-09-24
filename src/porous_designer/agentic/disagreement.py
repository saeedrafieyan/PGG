"""Provider disagreement detection."""

from __future__ import annotations

import math
from typing import Any

from porous_designer.agentic.contracts import ParsedRequestResult, ProviderDisagreement


def values_agree(a: Any, b: Any, *, rel_tol: float = 1e-6) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=rel_tol, abs_tol=1e-12)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(values_agree(x, y, rel_tol=rel_tol) for x, y in zip(a, b))
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    return a == b


def detect_provider_disagreements(deterministic: ParsedRequestResult, provider: ParsedRequestResult) -> list[ProviderDisagreement]:
    det = {f.field_path: f for f in deterministic.extracted_fields}
    disagreements: list[ProviderDisagreement] = []
    for field in provider.extracted_fields:
        other = det.get(field.field_path)
        if other is not None and not values_agree(other.value, field.value):
            disagreements.append(
                ProviderDisagreement(
                    field_path=field.field_path,
                    deterministic_value=other.value,
                    provider_value=field.value,
                    deterministic_evidence=other.source_text,
                    provider_evidence=field.source_text,
                    severity="blocking",
                )
            )
    return disagreements
