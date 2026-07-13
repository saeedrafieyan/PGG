"""Resolution-sensitivity worker."""

from __future__ import annotations

from porous_designer.domain.specification import DesignSpecification
from porous_designer.gui.workers.base_worker import ProcessWorker, child_event
from porous_designer.services.sensitivity_service import run_resolution_sensitivity


def run_sensitivity_job(payload: dict, result_queue, event_queue) -> None:
    child_event(event_queue, "sensitivity", message="Running resolution sensitivity.")
    spec = DesignSpecification.model_validate(payload["specification"])
    result = run_resolution_sensitivity(spec, resolutions=payload["resolutions"])
    result_queue.put({"kind": "result", "payload": {
        "output_dir": str(result.output_dir),
        "rows": result.rows,
        "status": result.status,
        "reference_resolution_mm": result.reference_resolution_mm,
    }})


class SensitivityWorker(ProcessWorker):
    def __init__(self, spec: DesignSpecification, resolutions: list[float], parent=None) -> None:
        super().__init__(
            run_sensitivity_job,
            {"specification": spec.model_dump(mode="json"), "resolutions": resolutions},
            worker_type="sensitivity",
            parent=parent,
        )
