"""Deterministic HTML report generation for GUI runs."""

from __future__ import annotations

import html
import json
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def generate_html_report(run_dir: Path, preview_image: Path | None = None) -> Path:
    bb = _read_json(run_dir / "blackboard.json")
    validation = _read_json(run_dir / "validation_report.json")
    timing = _read_json(run_dir / "timing.json")
    checksums = _read_json(run_dir / "checksums.json")
    workflow = _read_json(run_dir / "workflow_metadata.json")
    agentic_dir = run_dir / "agentic"
    plan_session = _read_json(agentic_dir / "plan_execution_session.json")
    plan_steps = _read_json(agentic_dir / "plan_step_executions.json")
    plan_observations = _read_json(agentic_dir / "plan_observations.json")
    plan_gates = _read_json(agentic_dir / "plan_validation_gates.json")
    plan_next_actions = _read_json(agentic_dir / "plan_next_actions.json")
    spec = html.escape(_read_text(run_dir / "approved_specification.yaml"))
    tuning = html.escape(_read_text(run_dir / "tuning_history.csv"))
    rows = []
    for check in validation.get("checks", []):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(check.get('name', '')))}</td>"
            f"<td>{html.escape(str(check.get('requested_value', '')))}</td>"
            f"<td>{html.escape(str(check.get('achieved_value', '')))}</td>"
            f"<td>{html.escape(str(check.get('tolerance', '')))}</td>"
            f"<td>{html.escape(str(check.get('status', '')).upper())}</td>"
            f"<td>{html.escape(str(check.get('method', '')))}</td>"
            "</tr>"
        )
    image_html = ""
    if preview_image and preview_image.exists():
        image_html = f'<img src="{html.escape(preview_image.name)}" alt="Preview image" />'
    out = run_dir / "pgg_report.html"
    out.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>PGG Run Report {html.escape(bb.get('run_id', run_dir.name))}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #1f2933; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
    th, td {{ border: 1px solid #c9d1d9; padding: 6px 8px; text-align: left; }}
    th {{ background: #eef2f7; }}
    pre {{ background: #f6f8fa; padding: 12px; overflow: auto; }}
    .status {{ font-weight: 700; }}
    img {{ max-width: 900px; border: 1px solid #c9d1d9; }}
  </style>
</head>
<body>
  <h1>PGG Run Report</h1>
  <p class="status">Final status: {html.escape(str(bb.get('status', 'unknown')).upper())}</p>
  <h2>Run Summary</h2>
  <table>
    <tr><th>Run ID</th><td>{html.escape(bb.get('run_id', run_dir.name))}</td></tr>
    <tr><th>Updated</th><td>{html.escape(bb.get('updated_at', ''))}</td></tr>
    <tr><th>Recommended STL</th><td>{html.escape(str(bb.get('export_results', {}).get('stl', '')))}</td></tr>
    <tr><th>STL SHA-256</th><td>{html.escape(str(checksums.get('stl_sha256', '')))}</td></tr>
  </table>
  <h2>Requested Versus Achieved Metrics</h2>
  <table><tr><th>Metric</th><th>Requested</th><th>Achieved</th><th>Tolerance</th><th>Status</th><th>Method</th></tr>{''.join(rows)}</table>
  <h2>Runtime and Memory</h2><pre>{html.escape(json.dumps(timing, indent=2))}</pre>
  <h2>Cleanup and Resource Estimates</h2><pre>{html.escape(json.dumps(bb.get('geometry_metrics', {}), indent=2))}</pre>
  <h2>Agentic Plan Execution Evidence</h2>
  <table>
    <tr><th>Application mode</th><td>{html.escape(str(workflow.get('application_mode', 'manual_or_unknown')))}</td></tr>
    <tr><th>Specification revision</th><td>{html.escape(str(workflow.get('specification_revision', '')))}</td></tr>
    <tr><th>Strategy plan ID</th><td>{html.escape(str(workflow.get('strategy_plan_id', plan_session.get('plan_id', ''))))}</td></tr>
    <tr><th>Plan execution status</th><td>{html.escape(str(plan_session.get('status', 'not_available')))}</td></tr>
  </table>
  <h3>Executed Steps</h3><pre>{html.escape(json.dumps(plan_steps, indent=2))}</pre>
  <h3>Observations</h3><pre>{html.escape(json.dumps(plan_observations, indent=2))}</pre>
  <h3>Validation Gate Results</h3><pre>{html.escape(json.dumps(plan_gates, indent=2))}</pre>
  <h3>Next Actions</h3><pre>{html.escape(json.dumps(plan_next_actions, indent=2))}</pre>
  <h2>Tuning History</h2><pre>{tuning}</pre>
  <h2>Preview Image</h2>{image_html or '<p>No preview image captured.</p>'}
  <h2>Approved Specification</h2><pre>{spec}</pre>
  <h2>Environment</h2><pre>{html.escape(_read_text(run_dir / 'environment.json'))}</pre>
  <h2>Limitations</h2>
  <ul>
    <li>Preview metrics are not final validation metrics.</li>
    <li>STEP, FEA, inverse design, cloud deployment, and LLM assistance are disabled in Phase 3A.</li>
    <li>Wall thickness and throat size are marked unavailable unless supplied by later validators.</li>
  </ul>
</body>
</html>
""",
        encoding="utf-8",
    )
    return out
