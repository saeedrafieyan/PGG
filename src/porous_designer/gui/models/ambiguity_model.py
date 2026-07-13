"""Qt model for agentic ambiguities."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from porous_designer.agentic.contracts import AmbiguityItem


class AmbiguityModel(QAbstractTableModel):
    HEADERS = ["Phrase", "Explanation", "Recommended", "Mandatory"]

    def __init__(self, ambiguities: list[AmbiguityItem] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.ambiguities = ambiguities or []

    def set_ambiguities(self, ambiguities: list[AmbiguityItem]) -> None:
        self.beginResetModel()
        self.ambiguities = ambiguities
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.ambiguities)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        item = self.ambiguities[index.row()]
        values = [
            item.source_phrase,
            item.explanation,
            item.recommended_choice,
            "yes" if item.mandatory else "no",
        ]
        return values[index.column()]

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None
