"""Validation report table model."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from porous_designer.domain.validation import ValidationReport


class ValidationTableModel(QAbstractTableModel):
    HEADERS = ["Metric", "Requested", "Achieved", "Tolerance", "Status", "Method"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []

    def set_report(self, report: ValidationReport | dict | None) -> None:
        self.beginResetModel()
        if isinstance(report, dict):
            report = ValidationReport.model_validate(report)
        self._rows = [c.model_dump(mode="json") for c in report.checks] if report else []
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        row = self._rows[index.row()]
        status = str(row.get("status", "")).upper()
        values = [
            row.get("name"),
            self._format_value(row.get("requested_value"), row.get("units")),
            self._format_value(row.get("achieved_value"), row.get("units")),
            row.get("tolerance"),
            status,
            row.get("method"),
        ]
        if role == Qt.ToolTipRole:
            return (
                f"{row.get('name', '')}\n"
                f"Status: {status}\n"
                f"Method: {row.get('method', '')}\n"
                f"{row.get('message', '')}"
            )
        return "" if values[index.column()] is None else str(values[index.column()])

    def _format_value(self, value, units: str | None) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            text = f"{value:.6g}"
        else:
            text = str(value)
        return f"{text} {units}".strip() if units else text

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def row_details(self, row: int) -> dict:
        return self._rows[row] if 0 <= row < len(self._rows) else {}

    def rows_as_csv(self) -> str:
        import csv
        import io

        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(self.HEADERS)
        for row in self._rows:
            writer.writerow(
                [
                    row.get("name", ""),
                    self._format_value(row.get("requested_value"), row.get("units")),
                    self._format_value(row.get("achieved_value"), row.get("units")),
                    row.get("tolerance", ""),
                    str(row.get("status", "")).upper(),
                    row.get("method", ""),
                ]
            )
        return out.getvalue()
