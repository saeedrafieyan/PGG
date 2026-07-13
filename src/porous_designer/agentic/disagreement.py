"""Provider disagreement detection."""

from __future__ import annotations

from porous_designer.agentic.contracts import ParsedRequestResult, ProviderDisagreement


def detect_provider_disagreements(deterministic: ParsedRequestResult, provider: ParsedRequestResult) -> list[ProviderDisagreement]:
    det = {f.field_path: f for f in deterministic.extracted_fields}
    disagreements: list[ProviderDisagreement] = []
    for field in provider.extracted_fields:
        other = det.get(field.field_path)
        if other is not None and other.value != field.value:
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
