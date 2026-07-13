"""Standalone validation worker."""

from __future__ import annotations

from porous_designer.gui.workers.base_worker import ProcessWorker, child_event
from porous_designer.services.validation_service import validate_standalone_stl


def run_stl_validation_job(payload: dict, result_queue, event_queue) -> None:
    child_event(event_queue, "validation", message="Validating STL.")
    report = validate_standalone_stl(payload["path"], expected_dims=payload.get("dims"))
    result_queue.put({"kind": "result", "payload": report.model_dump(mode="json")})


class ValidationWorker(ProcessWorker):
    def __init__(self, path: str, dims: list[float] | None = None, parent=None) -> None:
        super().__init__(
            run_stl_validation_job,
            {"path": path, "dims": dims},
            worker_type="validation",
            parent=parent,
        )
