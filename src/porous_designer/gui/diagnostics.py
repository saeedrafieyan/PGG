"""Runtime diagnostics for the Windows desktop GUI."""

from __future__ import annotations

import json
import logging
import multiprocessing as mp
import os
import platform
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger("porous_designer.gui")
_LOG_PATH: Path | None = None


def configure_gui_logging(*, debug: bool = False, log_path: Path | None = None) -> Path:
    """Configure compact JSON-lines diagnostics for GUI runtime analysis."""
    global _LOG_PATH
    if log_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = Path("logs") / f"gui_debug_{stamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _LOG_PATH = log_path
    _LOGGER.handlers.clear()
    _LOGGER.setLevel(logging.DEBUG if debug else logging.INFO)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)
    gui_event("diagnostics_configured", debug=debug, log_path=str(log_path))
    return log_path


def current_log_path() -> Path | None:
    return _LOG_PATH


def gui_event(event: str, **data: Any) -> None:
    """Write one structured diagnostic event without large payloads."""
    if not _LOGGER.handlers:
        return
    payload = {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "pid": os.getpid(),
        "ppid": os.getppid() if hasattr(os, "getppid") else None,
        "thread_id": threading.get_ident(),
        "event": event,
        **data,
    }
    try:
        _LOGGER.info(json.dumps(payload, sort_keys=True, default=str))
    except Exception:
        _LOGGER.info(json.dumps({"event": event, "logging_error": True}))


def runtime_diagnostics() -> str:
    """Return user-copyable GUI runtime diagnostics."""
    rows: list[tuple[str, str]] = [
        ("Python", sys.version.replace("\n", " ")),
        ("Executable", sys.executable),
        ("Platform", platform.platform()),
        ("Process ID", str(os.getpid())),
        ("Parent process ID", str(os.getppid() if hasattr(os, "getppid") else "")),
        ("Multiprocessing start method", mp.get_start_method(allow_none=True) or "default"),
        ("Qt platform", os.environ.get("QT_QPA_PLATFORM", "system default")),
        ("PYVISTA_OFF_SCREEN", os.environ.get("PYVISTA_OFF_SCREEN", "unset")),
        ("Debug log", str(_LOG_PATH or "")),
    ]
    try:
        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import QT_VERSION_STR
        from PySide6.QtWidgets import QApplication

        rows.extend(
            [
                ("Qt version", QT_VERSION_STR),
                ("PySide6 version", pyside_version),
                ("QApplication exists", str(QApplication.instance() is not None)),
                ("Top-level widgets", str(len(QApplication.topLevelWidgets()))),
            ]
        )
    except Exception as exc:
        rows.append(("Qt diagnostics error", str(exc)))
    for package in ("pyvista", "pyvistaqt", "vtk"):
        try:
            mod = __import__(package)
            rows.append((f"{package} version", str(getattr(mod, "__version__", "unknown"))))
        except Exception as exc:
            rows.append((f"{package} version", f"unavailable: {exc}"))
    return "\n".join(f"{key}: {value}" for key, value in rows)
