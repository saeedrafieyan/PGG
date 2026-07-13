"""Qt model for parsed agentic request fields."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from porous_designer.agentic.contracts import ExtractedField


class ExtractedFieldsModel(QAbstractTableModel):
    HEADERS = ["Field", "Value", "Confidence", "Source", "Status"]

    def __init__(self, fields: list[ExtractedField] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.fields = fields or []

    def set_fields(self, fields: list[ExtractedField]) -> None:
        self.beginResetModel()
        self.fields = fields
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.fields)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        field = self.fields[index.row()]
        values = [
            field.field_path,
            str(field.value),
            f"{field.confidence:.2f} ({field.confidence_category.value})",
            field.source.value,
            "confirmation required" if field.requires_confirmation else field.status,
        ]
        return values[index.column()]

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None
