"""SQLite-backed run history model."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


@dataclass
class RunRecord:
    run_id: str
    timestamp: str
    family: str
    domain: str
    dimensions: str
    requested_porosity: float | None
    achieved_porosity: float | None
    profile: str
    status: str
    runtime_s: float | None
    output_folder: str
    mode: str = ""
    plan_id: str = ""
    step_status_summary: str = ""
    report_available: bool = False


class RunHistoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                create table if not exists runs (
                    run_id text primary key,
                    timestamp text,
                    family text,
                    domain text,
                    dimensions text,
                    requested_porosity real,
                    achieved_porosity real,
                    profile text,
                    status text,
                    runtime_s real,
                    output_folder text,
                    mode text default '',
                    plan_id text default '',
                    step_status_summary text default '',
                    report_available integer default 0
                )
                """
            )
            columns = {row[1] for row in db.execute("pragma table_info(runs)").fetchall()}
            for name, ddl in {
                "mode": "alter table runs add column mode text default ''",
                "plan_id": "alter table runs add column plan_id text default ''",
                "step_status_summary": "alter table runs add column step_status_summary text default ''",
                "report_available": "alter table runs add column report_available integer default 0",
            }.items():
                if name not in columns:
                    db.execute(ddl)

    def upsert_from_run_dir(self, run_dir: Path) -> RunRecord | None:
        bb_path = run_dir / "blackboard.json"
        spec_path = run_dir / "approved_specification.yaml"
        if not bb_path.exists() or not spec_path.exists():
            return None
        import yaml

        bb = json.loads(bb_path.read_text(encoding="utf-8"))
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        timing = {}
        timing_path = run_dir / "timing.json"
        if timing_path.exists():
            timing = json.loads(timing_path.read_text(encoding="utf-8"))
        workflow = {}
        workflow_path = run_dir / "workflow_metadata.json"
        if workflow_path.exists():
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        plan_session = {}
        plan_session_path = run_dir / "agentic" / "plan_execution_session.json"
        if plan_session_path.exists():
            plan_session = json.loads(plan_session_path.read_text(encoding="utf-8"))
        mode = workflow.get("application_mode", "")
        if mode == "agentic_design" and workflow.get("strategy_plan_id"):
            mode = "agentic_plan_step_execution"
        step_summary = ""
        if plan_session:
            step_summary = (
                f"completed={len(plan_session.get('completed_steps', []))}; "
                f"failed={len(plan_session.get('failed_steps', []))}; "
                f"skipped={len(plan_session.get('skipped_steps', []))}"
            )
        record = RunRecord(
            run_id=bb.get("run_id", run_dir.name),
            timestamp=bb.get("updated_at") or bb.get("created_at", ""),
            family=spec.get("structure", {}).get("family", ""),
            domain=spec.get("domain", {}).get("shape", ""),
            dimensions=" x ".join(str(x) for x in spec.get("domain", {}).get("dimensions_mm", [])),
            requested_porosity=spec.get("targets", {}).get("porosity_target", {}).get("target"),
            achieved_porosity=bb.get("geometry_metrics", {}).get("final_mesh_porosity"),
            profile="final" if "_master.stl" in json.dumps(bb.get("artifacts", {})) else "preview",
            status=bb.get("status", ""),
            runtime_s=timing.get("total_s"),
            output_folder=str(run_dir),
            mode=mode,
            plan_id=workflow.get("strategy_plan_id", plan_session.get("plan_id", "")),
            step_status_summary=step_summary,
            report_available=(run_dir / "pgg_report.html").exists(),
        )
        with self._connect() as db:
            db.execute(
                """
                insert into runs values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(run_id) do update set
                    timestamp=excluded.timestamp,
                    family=excluded.family,
                    domain=excluded.domain,
                    dimensions=excluded.dimensions,
                    requested_porosity=excluded.requested_porosity,
                    achieved_porosity=excluded.achieved_porosity,
                    profile=excluded.profile,
                    status=excluded.status,
                    runtime_s=excluded.runtime_s,
                    output_folder=excluded.output_folder,
                    mode=excluded.mode,
                    plan_id=excluded.plan_id,
                    step_status_summary=excluded.step_status_summary,
                    report_available=excluded.report_available
                """,
                tuple(record.__dict__.values()),
            )
        return record

    def scan_runs(self, root: Path) -> list[RunRecord]:
        records = []
        if root.exists():
            for child in sorted(root.iterdir()):
                if child.is_dir():
                    rec = self.upsert_from_run_dir(child)
                    if rec:
                        records.append(rec)
        return records

    def list_records(self) -> list[RunRecord]:
        with self._connect() as db:
            rows = db.execute("select * from runs order by timestamp desc").fetchall()
        return [RunRecord(*row) for row in rows]


class RunHistoryModel(QAbstractTableModel):
    HEADERS = ["Run ID", "Timestamp", "Family", "Domain", "Dimensions", "Requested", "Achieved", "Profile", "Status", "Runtime", "Folder", "Mode", "Plan ID", "Steps", "Report"]

    def __init__(self, records: Iterable[RunRecord] = (), parent=None) -> None:
        super().__init__(parent)
        self._records = list(records)

    def set_records(self, records: Iterable[RunRecord]) -> None:
        self.beginResetModel()
        self._records = list(records)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        rec = self._records[index.row()]
        return str(list(rec.__dict__.values())[index.column()])

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def record(self, row: int) -> RunRecord | None:
        return self._records[row] if 0 <= row < len(self._records) else None
