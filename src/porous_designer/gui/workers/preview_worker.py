"""Preview generation worker entry points."""

from __future__ import annotations

from porous_designer.domain.specification import DesignSpecification
from porous_designer.services.generation_service import GenerationProfile, generate_porous_stl
from porous_designer.services.mesh_optimization import OptimizationProfile

from porous_designer.gui.workers.base_worker import ProcessWorker, child_event, result_payload_from_generation


def run_preview_job(payload: dict, result_queue, event_queue) -> None:
    child_event(event_queue, "specification_validation", message="Validating preview specification.")
    spec = DesignSpecification.model_validate(payload["specification"])
    child_event(event_queue, "preview_generation", message="Generating preview STL.")
    result = generate_porous_stl(
        spec,
        profile=GenerationProfile.PREVIEW,
        optimization_profile=OptimizationProfile.NONE,
    )
    child_event(event_queue, "preview_complete", message="Preview generation complete.", run_id=result.run_id)
    result_queue.put({"kind": "result", "payload": result_payload_from_generation(result)})


class PreviewWorker(ProcessWorker):
    def __init__(self, spec: DesignSpecification, parent=None) -> None:
        super().__init__(
            run_preview_job,
            {"specification": spec.model_dump(mode="json")},
            worker_type="preview",
            parent=parent,
        )
