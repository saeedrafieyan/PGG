"""Progress state for background operations."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal


@dataclass
class ProgressEvent:
    stage: str
    message: str
    percent: int | None = None
    level: str = "INFO"


class ProgressModel(QObject):
    changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.events: list[ProgressEvent] = []
        self.active_stage = "idle"

    def add(self, stage: str, message: str, percent: int | None = None, level: str = "INFO") -> None:
        event = ProgressEvent(stage=stage, message=message, percent=percent, level=level)
        self.events.append(event)
        self.active_stage = stage
        self.changed.emit(event)

    def clear(self) -> None:
        self.events.clear()
        self.active_stage = "idle"
        self.changed.emit(ProgressEvent("idle", "Ready"))
