"""Provider payload construction with privacy filtering."""

from __future__ import annotations

from typing import Any

from porous_designer.agentic.contracts import ParsedRequestResult
from porous_designer.agentic.terminology import TERMINOLOGY


FORBIDDEN_PAYLOAD_KEYS = {"stl", "step_file", "mesh", "vertices", "faces", "voxels", "screenshot", "path", "api_key", "environment"}


def build_provider_payload(request: str, deterministic: ParsedRequestResult, schema: dict) -> dict[str, Any]:
    payload = {
        "request": request,
        "deterministic_extraction": {
            "extracted_fields": [f.model_dump(mode="json") for f in deterministic.extracted_fields],
            "ambiguities": [a.model_dump(mode="json") for a in deterministic.ambiguities],
            "missing_requirements": [m.model_dump(mode="json") for m in deterministic.missing_requirements],
            "unsupported_requests": [u.model_dump(mode="json") for u in deterministic.unsupported_requests],
        },
        "schema": schema,
        "supported_generator_families": ["sc_spherical_pores", "bcc_spherical_pores", "fcc_spherical_pores", "hcp_spherical_pores", "gyroid", "diamond", "primitive"],
        "terminology": {key: term.definition for key, term in TERMINOLOGY.items()},
        "privacy": "No geometry, paths, screenshots, environment variables, or API keys are included.",
    }
    text = str(payload).lower()
    if any(key in text for key in ("api_key", "authorization", "bearer")):
        raise ValueError("Provider payload contains a forbidden secret marker.")
    return payload
