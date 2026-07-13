"""Process-backed Qt worker helpers."""

from __future__ import annotations

import multiprocessing as mp
import queue
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, Signal


@dataclass
class WorkerMessage:
    kind: str
    payload: dict[str, Any]


def _run_target(target: Callable, args: tuple, q: mp.Queue) -> None:
    try:
        q.put({"kind": "progress", "payload": {"stage": "started", "message": "Worker process started."}})
        result = target(*args)
        q.put({"kind": "result", "payload": result})
    except BaseException as exc:
        q.put(
            {
                "kind": "error",
                "payload": {
                    "message": str(exc),
                    "technical_details": traceback.format_exc(),
                },
            }
        )


class ProcessWorker(QObject):
    """Runs a callable in a child process and forwards queue messages as Qt signals."""

    progress = Signal(dict)
    result = Signal(dict)
    error = Signal(dict)
    cancelled = Signal(dict)
    finished = Signal()

    def __init__(self, target: Callable, args: tuple = (), parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: mp.Queue = mp.Queue()
        self._process = mp.Process(target=_run_target, args=(target, args, self._queue), daemon=True)
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._poll)
        self._completed = False

    @property
    def is_running(self) -> bool:
        return self._process.is_alive()

    def start(self) -> None:
        self._process.start()
        self._timer.start()

    def cancel(self) -> None:
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=5)
            if self._process.is_alive():
                self._process.kill()
        self._timer.stop()
        self.cancelled.emit({"message": "Generation was cancelled. Completed validated artifacts were preserved."})
        self.finished.emit()

    def _poll(self) -> None:
        while True:
            try:
                msg = self._queue.get_nowait()
            except queue.Empty:
                break
            kind = msg.get("kind")
            payload = msg.get("payload", {})
            if kind == "progress":
                self.progress.emit(payload)
            elif kind == "result":
                self._completed = True
                self.result.emit(payload)
            elif kind == "error":
                self._completed = True
                self.error.emit(payload)
        if not self._process.is_alive():
            self._timer.stop()
            self._process.join(timeout=1)
            if not self._completed and self._process.exitcode not in (0, None):
                self.error.emit(
                    {
                        "message": f"Worker exited with code {self._process.exitcode}.",
                        "technical_details": "The process ended before returning a structured result.",
                    }
                )
            self.finished.emit()


def result_payload_from_generation(result: Any) -> dict[str, Any]:
    return {
        "success": result.success,
        "run_id": result.run_id,
        "run_dir": str(result.run_dir),
        "profile": result.profile.value,
        "lattice_spacing_mm": result.lattice_spacing_mm,
        "tuning_grid_porosity": result.tuning_grid_porosity,
        "final_voxel_porosity": result.final_voxel_porosity,
        "final_mesh_porosity": result.final_mesh_porosity,
        "triangle_count": result.triangle_count,
        "solid_components": result.solid_components,
        "watertight": result.watertight,
        "stl_path": str(result.stl_path) if result.stl_path else None,
        "stl_sha256": result.stl_sha256,
        "timing": result.timing.__dict__,
        "peak_memory_mb": result.peak_memory_mb,
        "validation_passed": result.validation_passed,
        "messages": result.messages,
        "connectivity": result.connectivity,
        "resource_estimate": result.resource_estimate.to_dict() if result.resource_estimate else None,
        "validation_report_path": str(Path(result.run_dir) / "validation_report.json"),
        "blackboard_path": str(Path(result.run_dir) / "blackboard.json"),
    }
