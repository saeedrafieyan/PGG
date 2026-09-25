"""Application presets with citations (``knowledge/data/applications.yaml``)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DATA_FILE = Path(__file__).resolve().parent / "data" / "applications.yaml"


@lru_cache(maxsize=1)
def knowledge() -> dict[str, Any]:
    return yaml.safe_load(DATA_FILE.read_text(encoding="utf-8"))


def reference(key: str) -> str:
    return knowledge()["references"].get(key, key)


def cite(sources) -> list[str]:
    if not sources:
        return []
    if isinstance(sources, str):
        sources = [sources]
    return [reference(s) for s in sources]


@dataclass
class ApplicationMatch:
    key: str
    label: str
    phrase: str
    preset: dict[str, Any]


def match_application(text: str) -> ApplicationMatch | None:
    """The application named in the request (longest alias wins), if any."""
    low = text.lower()
    best = None
    for key, preset in knowledge()["applications"].items():
        for alias in preset.get("aliases", []):
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low):
                if best is None or len(alias) > len(best.phrase):
                    best = ApplicationMatch(key, preset.get("label", key), alias, preset)
    return best


def design_rule(key: str) -> dict[str, Any]:
    return knowledge()["design_rules"][key]
