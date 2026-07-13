"""Safe validated-provider-result cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from porous_designer.agentic.contracts import ParsedRequestResult
from porous_designer.agentic.terminology import normalize_text

TERMINOLOGY_REGISTRY_VERSION = "3B.1.1"


class ProviderResultCache:
    def __init__(self, root: str | Path = "runs/provider_cache", *, enabled: bool = True) -> None:
        self.root = Path(root)
        self.enabled = enabled

    def key(self, *, request: str, parser_version: str, provider: str, model: str, schema_version: str) -> str:
        data = {
            "normalized_request": normalize_text(request),
            "parser_version": parser_version,
            "provider": provider,
            "model": model,
            "schema_version": schema_version,
            "terminology_registry_version": TERMINOLOGY_REGISTRY_VERSION,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()

    def get(self, key: str) -> ParsedRequestResult | None:
        if not self.enabled:
            return None
        path = self.root / f"{key}.json"
        if not path.exists():
            return None
        return ParsedRequestResult.model_validate_json(path.read_text(encoding="utf-8"))

    def set(self, key: str, result: ParsedRequestResult) -> None:
        if not self.enabled:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{key}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

    def clear(self) -> None:
        if not self.root.exists():
            return
        for path in self.root.glob("*.json"):
            path.unlink()
