"""Standalone validation worker."""

from __future__ import annotations

from porous_designer.gui.workers.base_worker import ProcessWorker
from porous_designer.services.validation_service import validate_standalone_stl


def run_stl_validation(path: str, dims: list[float] | None = None) -> dict:
    return validate_standalone_stl(path, expected_dims=dims).model_dump(mode="json")


class ValidationWorker(ProcessWorker):
    def __init__(self, path: str, dims: list[float] | None = None, parent=None) -> None:
        super().__init__(run_stl_validation, (path, dims), parent)
