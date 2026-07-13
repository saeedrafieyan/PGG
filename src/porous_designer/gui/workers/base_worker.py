"""Windows-spawn-safe process worker helpers."""

from __future__ import annotations

import multiprocessing as mp
import queue
import traceback
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, Signal

from porous_designer.gui.diagnostics import current_log_path, gui_event

JobFunction = Callable[[dict[str, Any], Any, Any], None]


def child_event(event_queue, event: str, **payload: Any) -> None:
    try:
        event_queue.put({"kind": "progress", "payload": {"stage": event, "message": payload.pop("message", event), **payload}})
    except Exception:
        pass


def run_process_job(job: JobFunction, payload: dict[str, Any], result_queue, event_queue) -> None:
    """Top-level child entry point. Never imports or constructs Qt widgets."""
    from porous_designer.gui.diagnostics import configure_gui_logging, gui_event

    log_path = payload.get("_debug_log_path")
    if log_path:
        configure_gui_logging(debug=True, log_path=Path(log_path))
    gui_event("child_process_entry", worker_type=payload.get("_worker_type"))
    try:
        child_event(event_queue, "child_started", message="Child process started.")
        job(payload, result_queue, event_queue)
        gui_event("child_process_result_sent", worker_type=payload.get("_worker_type"))
    except BaseException as exc:
        error = {
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "technical_details": traceback.format_exc(),
            "stage": payload.get("_worker_type", "worker"),
        }
        result_queue.put({"kind": "error", "payload": error})
        gui_event("child_process_error", **error)


class ProcessWorker(QObject):
    """Run a pure job function in a child process and forward compact events."""

    progress = Signal(dict)
    result = Signal(dict)
    error = Signal(dict)
    cancelled = Signal(dict)
    finished = Signal()

    def __init__(
        self,
        job: JobFunction,
        payload: dict[str, Any],
        *,
        worker_type: str,
        timeout_ms: int = 30 * 60 * 1000,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.worker_type = worker_type
        self._ctx = mp.get_context("spawn")
        self._result_queue = self._ctx.Queue()
        self._event_queue = self._ctx.Queue()
        self._payload = dict(payload)
        self._payload["_worker_type"] = worker_type
        if current_log_path():
            self._payload["_debug_log_path"] = str(current_log_path())
        self._process = self._ctx.Process(
            target=run_process_job,
            args=(job, self._payload, self._result_queue, self._event_queue),
            daemon=True,
        )
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(timeout_ms)
        self._timeout.timeout.connect(self._timeout_expired)
        self._completed = False
        self._finished_emitted = False
        gui_event("worker_constructed", worker_type=worker_type)

    @property
    def is_running(self) -> bool:
        return self._process.is_alive()

    @property
    def child_pid(self) -> int | None:
        return self._process.pid

    @property
    def exit_code(self) -> int | None:
        return self._process.exitcode

    def start(self) -> None:
        gui_event("worker_start_requested", worker_type=self.worker_type)
        self._process.start()
        gui_event("worker_process_started", worker_type=self.worker_type, child_pid=self._process.pid)
        self._timer.start()
        self._timeout.start()

    def cancel(self) -> None:
        gui_event("worker_cancel_requested", worker_type=self.worker_type, child_pid=self.child_pid)
        self._terminate_child()
        self.cancelled.emit(
            {
                "message": "Generation was cancelled. Completed validated artifacts were preserved.",
                "worker_type": self.worker_type,
                "child_pid": self.child_pid,
                "exit_code": self.exit_code,
            }
        )
        self._finish()

    def _timeout_expired(self) -> None:
        gui_event("worker_timeout", worker_type=self.worker_type, child_pid=self.child_pid)
        self._terminate_child()
        self.error.emit(
            {
                "message": f"{self.worker_type} timed out.",
                "technical_details": "Worker exceeded configured timeout and was terminated.",
                "stage": self.worker_type,
                "child_pid": self.child_pid,
                "exit_code": self.exit_code,
            }
        )
        self._finish()

    def _terminate_child(self) -> None:
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=5)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=2)

    def _poll(self) -> None:
        self._drain_events()
        self._drain_results()
        if not self._process.is_alive():
            self._process.join(timeout=0.1)
            self._drain_events()
            self._drain_results()
            gui_event(
                "worker_process_exited",
                worker_type=self.worker_type,
                child_pid=self.child_pid,
                exit_code=self.exit_code,
                completed=self._completed,
            )
            if not self._completed and self.exit_code not in (0, None):
                self.error.emit(
                    {
                        "message": f"{self.worker_type} exited with code {self.exit_code}.",
                        "technical_details": "The child process ended before returning a structured result.",
                        "stage": self.worker_type,
                        "child_pid": self.child_pid,
                        "exit_code": self.exit_code,
                    }
                )
            self._finish()

    def _drain_events(self) -> None:
        while True:
            try:
                msg = self._event_queue.get_nowait()
            except queue.Empty:
                break
            payload = msg.get("payload", {})
            gui_event("worker_event_received", worker_type=self.worker_type, **payload)
            self.progress.emit(payload)

    def _drain_results(self) -> None:
        while True:
            try:
                msg = self._result_queue.get_nowait()
            except queue.Empty:
                break
            kind = msg.get("kind")
            payload = msg.get("payload", {})
            payload.setdefault("child_pid", self.child_pid)
            payload.setdefault("exit_code", self.exit_code)
            if kind == "result":
                self._completed = True
                gui_event("worker_result_received", worker_type=self.worker_type, run_id=payload.get("run_id"))
                self.result.emit(payload)
            elif kind == "error":
                self._completed = True
                gui_event("worker_error_received", worker_type=self.worker_type, message=payload.get("message"))
                self.error.emit(payload)

    def _finish(self) -> None:
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self._timer.stop()
        self._timeout.stop()
        try:
            self._result_queue.close()
            self._event_queue.close()
        except Exception:
            pass
        gui_event("worker_finished", worker_type=self.worker_type, child_pid=self.child_pid, exit_code=self.exit_code)
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
