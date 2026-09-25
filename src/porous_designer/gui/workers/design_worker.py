"""Design-agent worker: runs an approved proposal (generate, measure, repair) in a child process."""

from __future__ import annotations

from porous_designer.gui.workers.base_worker import ProcessWorker, child_event


def run_design_job(payload: dict, result_queue, event_queue) -> None:
    from porous_designer.services.design_session import run_approved_snapshot

    def on_event(stage: str, message: str) -> None:
        child_event(event_queue, stage, message=message)

    out = run_approved_snapshot(payload["snapshot"], on_event=on_event)
    result_queue.put({"kind": "result", "payload": out})


class DesignWorker(ProcessWorker):
    def __init__(self, snapshot: dict, parent=None) -> None:
        super().__init__(run_design_job, {"snapshot": snapshot}, worker_type="design", timeout_ms=3 * 60 * 60 * 1000, parent=parent)
