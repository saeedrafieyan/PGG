"""Blackboard persistence to run directory."""

from __future__ import annotations

import json
from pathlib import Path

from porous_designer.blackboard.state import Blackboard


def run_directory(base: str | Path, run_id: str) -> Path:
    return Path(base) / run_id


def save_blackboard(bb: Blackboard, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(bb.model_dump_json(indent=2), encoding="utf-8")


def load_blackboard(path: str | Path) -> Blackboard:
    return Blackboard.model_validate_json(Path(path).read_text(encoding="utf-8"))


def persist_blackboard(bb: Blackboard, output_directory: str = "runs") -> Path:
    """Save blackboard to runs/<run_id>/blackboard.json."""
    run_dir = run_directory(output_directory, bb.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "blackboard.json"
    save_blackboard(bb, out)
    return out


def save_environment(bb: Blackboard, run_dir: Path) -> None:
    env_path = run_dir / "environment.json"
    env_path.write_text(
        json.dumps(bb.software_environment.model_dump(), indent=2),
        encoding="utf-8",
    )
