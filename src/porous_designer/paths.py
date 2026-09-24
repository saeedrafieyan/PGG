"""Working-directory-independent locations for runs, caches, and configuration.

Resolution order for the data root:

1. ``AGE_HOME`` environment variable.
2. The source checkout root (the directory holding this project's
   ``pyproject.toml``) when running from a checkout, which keeps the historical
   ``<repo>/runs`` layout.
3. ``~/AGE`` for an installed package.

``AGE_RUNS_DIR`` and ``AGE_CONFIG`` override the runs directory and the
configuration file independently.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
_PROJECT_NAME_MARKER = 'name = "porous-designer"'


@lru_cache(maxsize=1)
def source_checkout_root() -> Path | None:
    for candidate in _PACKAGE_DIR.parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file():
            try:
                if _PROJECT_NAME_MARKER in pyproject.read_text(encoding="utf-8"):
                    return candidate
            except OSError:
                return None
            return None
    return None


def data_root() -> Path:
    env = os.environ.get("AGE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    root = source_checkout_root()
    if root is not None:
        return root
    return Path.home() / "AGE"


def runs_dir() -> Path:
    env = os.environ.get("AGE_RUNS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return data_root() / "runs"


def cache_dir() -> Path:
    return runs_dir() / ".cache"


def provider_cache_dir() -> Path:
    return runs_dir() / "provider_cache"


def default_config_path() -> Path:
    env = os.environ.get("AGE_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    root = source_checkout_root()
    if root is not None:
        return root / "configs" / "default.yaml"
    return data_root() / "configs" / "default.yaml"


def resolve_output_directory(value: str | Path) -> str:
    """Anchor a relative GUI output folder at the data root, not the CWD."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str(data_root() / path)
