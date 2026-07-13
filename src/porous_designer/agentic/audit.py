"""Audit-file persistence for agentic request interpretation."""

from __future__ import annotations

import json
from pathlib import Path

from porous_designer.agentic.contracts import ApprovalRecord, ParsedRequestResult
from porous_designer.domain.specification import DesignSpecification


def write_agentic_audit(
    run_dir: str | Path,
    *,
    original_request: str,
    parsed: ParsedRequestResult,
    proposed_specification: DesignSpecification,
    approved_specification: DesignSpecification | None = None,
    approval_record: ApprovalRecord | None = None,
) -> Path:
    target = Path(run_dir) / "agentic"
    target.mkdir(parents=True, exist_ok=True)
    (target / "original_request.txt").write_text(original_request, encoding="utf-8")
    parsed_json = parsed.model_dump(mode="json")
    (target / "deterministic_extraction.json").write_text(json.dumps(parsed_json, indent=2), encoding="utf-8")
    (target / "provider_response.json").write_text(json.dumps(parsed_json if not parsed.provider_failed else {"provider_failed": True, "reason": parsed.provider_failure_reason}, indent=2), encoding="utf-8")
    metadata = parsed.provider_metadata or {}
    (target / "external_call_decision.json").write_text(json.dumps(metadata.get("external_call_decision", {}), indent=2), encoding="utf-8")
    (target / "provider_request_redacted.json").write_text(json.dumps(metadata.get("provider_request_redacted", {}), indent=2), encoding="utf-8")
    (target / "provider_response_validated.json").write_text(json.dumps(parsed_json, indent=2), encoding="utf-8")
    (target / "provider_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (target / "provider_disagreements.json").write_text(json.dumps(metadata.get("provider_disagreements", []), indent=2), encoding="utf-8")
    (target / "cache_metadata.json").write_text(json.dumps({"cache_status": metadata.get("cache_status", "miss")}, indent=2), encoding="utf-8")
    (target / "ambiguities.json").write_text(json.dumps([a.model_dump(mode="json") for a in parsed.ambiguities], indent=2), encoding="utf-8")
    (target / "resolutions.json").write_text(json.dumps({a.identifier: a.resolved_choice for a in parsed.ambiguities if a.resolved_choice}, indent=2), encoding="utf-8")
    proposed_specification.save_yaml(target / "proposed_specification.yaml")
    if approved_specification is not None:
        approved_specification.save_yaml(target / "approved_specification.yaml")
    if approval_record is not None:
        (target / "approval_audit.json").write_text(json.dumps(approval_record.model_dump(mode="json"), indent=2), encoding="utf-8")
    return target
