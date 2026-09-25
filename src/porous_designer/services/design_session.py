"""Describe -> Review -> Download, independent of any user interface (Phase 4.4).

``DesignSession`` wraps the design agent in the three steps every front end
shows (desktop GUI, web API, CLI):

1. **Describe**: ``propose(text, process, printer)`` runs the Planner and
   Designer only and returns a *proposal card*: one plain-language
   sentence, the key numbers with where each came from, the printer check
   and anything the user must confirm. Nothing is generated yet.
2. **Review**: ``approve()`` (checkpoint 1) runs generation, measurement and
   bounded repairs, and returns a *result card* with measured numbers
   against targets, the printer check and the files.
3. **Download**: ``files()`` lists STL / 3MF / STEP, the design report
   (HTML) and the agent trace.

Cards are plain JSON-serialisable dicts, so the GUI and the web page render
the same content.
"""

from __future__ import annotations

import html
import json
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from porous_designer.agentic.design_agent import DesignAgent, DesignAgentResult

LABELS = {
    "domain_shape": ("Part shape", ""),
    "domain_dimensions_mm": ("Part size", "mm"),
    "family": ("Architecture", ""),
    "tpms_variant": ("TPMS variant", ""),
    "porosity": ("Porosity", "%"),
    "pore_mm": ("Pore size", "mm"),
    "cell_mm": ("Unit cell size", "mm"),
    "min_wall_mm": ("Minimum wall", "mm"),
    "min_throat_mm": ("Minimum pore opening", "mm"),
    "open_pores": ("Open, connected pores", ""),
    "permeability_m2": ("Target permeability", "m²"),
    "youngs_relative": ("Target stiffness E*/Es", ""),
    "resolution_mm": ("Voxel resolution", "mm"),
    "process": ("Process", ""),
    "printer_profile": ("Printer", ""),
    "formats": ("File formats", ""),
}
SOURCE_TEXT = {
    "user": "from your request",
    "knowledge_base": "from the literature",
    "designer": "chosen by the designer",
    "default": "default",
}
MEASURED = (
    ("porosity", "Porosity", "%"),
    ("pore_d50_mm", "Median pore size", "mm"),
    ("wall_d50_mm", "Median wall thickness", "mm"),
    ("wall_min_mm", "Thinnest walls (10th percentile)", "mm"),
    ("percolation_diameter_mm", "Largest sphere passing through", "mm"),
    ("closed_void_fraction", "Closed pores (fraction of void)", ""),
    ("specific_surface_per_mm", "Surface area per volume", "1/mm"),
    ("tortuosity", "Tortuosity", ""),
    ("permeability_m2", "Permeability", "m²"),
    ("youngs_relative", "Stiffness E*/Es", ""),
)


def _fmt(value: Any, unit: str) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return " x ".join(_fmt(v, "") for v in value) + (f" {unit}" if unit else "")
    if isinstance(value, float):
        if unit == "%":
            return f"{value:.1%}"
        if unit == "m²" or abs(value) < 1e-3 and value != 0:
            return f"{value:.2e} {unit}".strip()
        return f"{value:.3g} {unit}".strip()
    return f"{value} {unit}".strip() if unit and unit != "%" else str(value)


def _plain_family(intent) -> str:
    fam = intent.get("family") or "porous"
    var = intent.get("tpms_variant")
    name = str(fam).replace("_", " ")
    return f"{name} ({var})" if var and fam in ("gyroid", "diamond", "primitive", "iwp", "neovius", "fischer_koch_s", "lidinoid") else name


def proposal_card(result: DesignAgentResult) -> dict:
    intent = result.intent
    numbers, confirm, citations = [], [], []
    for key, (label, unit) in LABELS.items():
        v = intent.values.get(key)
        if v is None:
            continue
        numbers.append({"key": key, "label": label, "value": _fmt(v.value, unit), "source": SOURCE_TEXT.get(v.source, v.source), "detail": v.detail, "confirm": v.requires_confirmation, "citations": v.citations})
        if v.requires_confirmation:
            confirm.append(f"{label}: {_fmt(v.value, unit)} ({v.detail})")
        citations += [c for c in v.citations if c not in citations]
    notes = [v.value for k, v in intent.values.items() if k.startswith("note_")]
    for k, v in intent.values.items():
        if k.startswith("note_"):
            citations += [c for c in v.citations if c not in citations]
    point = result.design_info.get("design_point") or {}
    predicted = []
    for key, label in (("wall_mm", "Thinnest walls"), ("pore_mm", "Median pore size"), ("throat_mm", "Pore openings"), ("permeability_m2", "Permeability"), ("youngs_relative", "Stiffness E*/Es")):
        if point.get(key) is not None:
            predicted.append({"label": label, "value": _fmt(point[key], "m²" if key == "permeability_m2" else ("mm" if key.endswith("_mm") else ""))})
    printer = result.design_info.get("printer")
    req = result.design_info.get("requirements", {})
    if result.status == "infeasible":
        headline = "This request cannot be printed as stated."
    else:
        dims = intent.get("domain_dimensions_mm") or []
        headline = (
            f"A {_plain_family(intent)} {intent.get('domain_shape', 'part')} of {' x '.join(f'{d:g}' for d in dims)} mm "
            f"with {intent.get('porosity', 0):.0%} porosity"
            + (f", pores about {point['pore_mm']:.2f} mm" if point.get("pore_mm") else "")
            + (f", checked for {printer}" if printer else ", no printer selected")
            + "."
        )
    return {
        "kind": "proposal",
        "status": result.status,
        "headline": headline,
        "numbers": numbers,
        "predicted": predicted,
        "printer": {"id": printer, "min_wall_mm": req.get("min_wall_mm"), "min_opening_mm": req.get("min_opening_mm")},
        "confirm": confirm,
        "notes": notes,
        "unsupported": intent.unsupported,
        "ambiguities": intent.ambiguities,
        "citations": citations,
        "explanation": result.explanation if result.status == "infeasible" else "",
        "alternatives": [{"description": a["description"], "change": a["change"]} for a in result.alternatives],
        "application": intent.application,
    }


def result_card(result: DesignAgentResult) -> dict:
    gen = result.generation
    last = result.iterations[-1]["verification"] if result.iterations else {}
    checks = last.get("checks", {})
    m = dict(last.get("measurements") or {})
    if gen is not None:
        m["porosity"] = getattr(gen, "final_mesh_porosity", None)
    targets = {
        "porosity": result.intent.get("porosity"),
        "pore_d50_mm": result.intent.get("pore_mm") if result.intent.get("family") not in ("sc_spherical_pores", "bcc_spherical_pores", "fcc_spherical_pores", "hcp_spherical_pores") else None,
        "wall_min_mm": result.intent.get("min_wall_mm"),
        "percolation_diameter_mm": result.intent.get("min_throat_mm"),
        "permeability_m2": result.intent.get("permeability_m2"),
        "youngs_relative": result.intent.get("youngs_relative"),
    }
    measured = []
    for key, label, unit in MEASURED:
        if m.get(key) is None:
            continue
        measured.append({"key": key, "label": label, "value": _fmt(m[key], unit), "target": _fmt(targets.get(key), unit) if targets.get(key) is not None else ""})
    printer_checks = [{"name": k, "status": v["status"], "achieved": v.get("achieved"), "requested": v.get("requested")} for k, v in checks.items() if k.startswith("print_")]
    problems = [{"name": k, "status": v["status"], "achieved": v.get("achieved"), "requested": v.get("requested")} for k, v in checks.items() if v["status"] in ("fail", "warning")]
    headline = {
        "delivered": "Design generated, measured and passing every check.",
        "delivered_with_warnings": "Design generated and measured; see the warnings before printing.",
        "needs_user": "The design needs a decision from you.",
        "failed": "The design did not pass its checks.",
        "rejected": "Result not accepted.",
    }.get(result.status, result.status)
    return {
        "kind": "result",
        "status": result.status,
        "headline": headline,
        "summary": result.explanation,
        "measured": measured,
        "printer_checks": printer_checks,
        "problems": problems,
        "iterations": [
            {"iteration": it["iteration"], "failed": it["verification"]["failed"], "warnings": it["verification"]["warnings"], "repairs": it.get("repairs", []), "conflicts": it.get("conflicts", [])}
            for it in result.iterations
        ],
    }


def write_design_report(result: DesignAgentResult, path: Path) -> Path:
    """Self-contained HTML report: intent with sources and citations, measurements, checks, iterations."""
    p, r = proposal_card(result), result_card(result) if result.iterations else None
    e = html.escape

    def table(rows, head):
        body = "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in row) + "</tr>" for row in rows)
        return "<table><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + f"</tr>{body}</table>"

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>AGE design report</title>",
        "<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#222}"
        "table{border-collapse:collapse;width:100%;margin:8px 0 20px}td,th{border:1px solid #ccc;padding:4px 8px;text-align:left;vertical-align:top}"
        "th{background:#f3f3f3}.warn{color:#9a6700}.fail{color:#b00020}.pass{color:#1a7f37}small{color:#666}</style></head><body>",
        "<h1>AGE design report</h1>",
        f"<p><b>Request:</b> {e(result.intent.request)}</p>",
        f"<p><b>Status:</b> {e(result.status)}. {e(p['headline'])}</p>",
        "<h2>Design intent</h2><p><small>Every value shows where it came from. Values marked * need your confirmation.</small></p>",
        table([[n["label"] + (" *" if n["confirm"] else ""), n["value"], n["source"], n["detail"]] for n in p["numbers"]], ["Quantity", "Value", "Source", "Why"]),
    ]
    if p["predicted"]:
        parts.append("<h2>Predicted before generation (property tables)</h2>" + table([[x["label"], x["value"]] for x in p["predicted"]], ["Quantity", "Predicted"]))
    if r:
        parts.append("<h2>Measured on the generated geometry</h2>" + table([[x["label"], x["value"], x["target"]] for x in r["measured"]], ["Quantity", "Measured", "Target"]))
        if r["printer_checks"]:
            parts.append("<h2>Printer check</h2>" + table([[c["name"], c["status"], c["requested"], c["achieved"]] for c in r["printer_checks"]], ["Check", "Status", "Required", "Achieved"]))
        parts.append("<h2>Iterations</h2>" + table([[it["iteration"], ", ".join(it["failed"]) or "-", ", ".join(it["warnings"]) or "-", "; ".join(f"{x['rule']}: {x['from']} -> {x['to']}" for x in it["repairs"]) or "-"] for it in r["iterations"]], ["#", "Failed", "Warnings", "Repair"]))
    if p["explanation"]:
        parts.append(f"<h2>Why it is infeasible</h2><pre>{e(p['explanation'])}</pre>")
    if p["notes"]:
        parts.append("<h2>Notes</h2><ul>" + "".join(f"<li>{e(n)}</li>" for n in p["notes"]) + "</ul>")
    if p["citations"]:
        parts.append("<h2>References</h2><ol>" + "".join(f"<li>{e(c)}</li>" for c in p["citations"]) + "</ol>")
    parts.append(
        "<h2>Limitations</h2><p>Sizes, permeability and stiffness are computed on the voxelised geometry (Phase 4.2 metrology); "
        "printer limits are generic unless a calibrated profile is used. Physical validation of printed parts is required.</p>"
    )
    parts.append("</body></html>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts), encoding="utf-8")
    return path


@dataclass
class DesignSession:
    """One Describe -> Review -> Download round trip."""

    output_dir: Path | None = None
    provider: Any = None
    settings: Any = None
    max_iterations: int = 3
    generate: Callable | None = None
    on_event: Callable[[str, str], None] | None = None
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: str = "new"  # new | proposed | infeasible | queued | running | done | error
    stage: str = ""
    message: str = ""
    result: DesignAgentResult | None = None
    error: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _agent(self, process: str | None, printer: str | None) -> DesignAgent:
        def event(stage, message):
            self.stage, self.message = stage, message
            if self.on_event:
                self.on_event(stage, message)

        return DesignAgent(
            provider=self.provider,
            settings=self.settings,
            output_dir=self.output_dir,
            max_iterations=self.max_iterations,
            printer_profile=printer or None,
            process=process or None,
            generate=self.generate,
            approve_final=lambda _r: True,
            on_event=event,
        )

    def propose(self, text: str, *, process: str | None = None, printer: str | None = None) -> dict:
        self._agent_obj = self._agent(process, printer)
        self.result = self._agent_obj.propose(text)
        self.state = "infeasible" if self.result.status == "infeasible" else "proposed"
        if self.state == "infeasible":
            self._agent_obj._finish(self.result)
            self._write_report()
        return proposal_card(self.result)

    def approve(self) -> dict:
        """Checkpoint 1 approved: generate, measure, repair. Blocking; call from a worker thread."""
        if self.state not in ("proposed", "queued") or self.result is None:
            raise RuntimeError(f"nothing to approve (state {self.state})")
        with self._lock:
            self.state = "running"
            try:
                from porous_designer.agentic.design_agent import TraceStep

                self.result.trace.append(TraceStep("human", "approve_intent", "approved", {}))
                self._agent_obj.execute(self.result)
                self._write_report()
                self.state = "done"
            except Exception as exc:  # reported to the front end
                self.state, self.error = "error", f"{type(exc).__name__}: {exc}"
                raise
        return result_card(self.result)

    def _write_report(self) -> None:
        folder = self.result.trace_path.parent if self.result.trace_path else Path(self.output_dir or ".")
        self.report_path = write_design_report(self.result, folder / "design_report.html")

    def files(self) -> dict[str, Path]:
        out: dict[str, Path] = {}
        if self.result is None:
            return out
        gen = self.result.generation
        if gen is not None:
            for key, path in (("stl", gen.stl_path), ("3mf", gen.threemf_path), ("step", gen.step_path)):
                if path and Path(path).exists():
                    out[key] = Path(path)
        report = getattr(self, "report_path", None)
        if report and Path(report).exists():
            out["report"] = Path(report)
        if self.result.trace_path and self.result.trace_path.exists():
            out["trace"] = self.result.trace_path
        return out

    def snapshot(self) -> dict:
        return {"result": self.result.snapshot(), "output_dir": str(self.output_dir) if self.output_dir else None, "max_iterations": self.max_iterations}

    def to_dict(self) -> dict:
        d = {"session_id": self.session_id, "state": self.state, "stage": self.stage, "message": self.message, "error": self.error}
        if self.result is not None:
            d["proposal"] = proposal_card(self.result)
            if self.state == "done":
                d["result"] = result_card(self.result)
                d["files"] = sorted(self.files())
        return json.loads(json.dumps(d, default=str))


def run_approved_snapshot(snapshot: dict, *, on_event: Callable[[str, str], None] | None = None, generate: Callable | None = None) -> dict:
    """Execute an approved proposal from ``DesignSession.snapshot()`` (e.g. in a GUI child process).

    Returns JSON-serialisable cards and file paths.
    """
    session = DesignSession(output_dir=Path(snapshot["output_dir"]) if snapshot.get("output_dir") else None, max_iterations=snapshot.get("max_iterations", 3), generate=generate, on_event=on_event)
    session.result = DesignAgentResult.from_snapshot(snapshot["result"])
    session._agent_obj = session._agent(None, None)
    session.state = "proposed"
    card = session.approve()
    return {
        "state": session.state,
        "status": session.result.status,
        "result_card": card,
        "proposal_card": proposal_card(session.result),
        "files": {k: str(v) for k, v in session.files().items()},
    }


def render_card_html(card: dict) -> str:
    """Compact HTML for a proposal or result card (Qt rich text and simple browsers)."""
    e = html.escape
    out = [f"<h3>{e(card.get('headline', ''))}</h3>"]
    if card.get("kind") == "proposal":
        if card["status"] == "infeasible":
            out.append("<p>" + e(card["explanation"]).replace("\n", "<br>") + "</p>")
            if card["alternatives"]:
                out.append("<p><b>Try instead:</b></p><ul>" + "".join(f"<li>{e(a['description'])}</li>" for a in card["alternatives"]) + "</ul>")
            return "".join(out)
        out.append("<table cellspacing='0' cellpadding='4' width='100%'><tr><th align='left'>Quantity</th><th align='left'>Value</th><th align='left'>Source</th></tr>")
        for n in card["numbers"]:
            out.append(f"<tr><td>{e(n['label'])}{' *' if n['confirm'] else ''}</td><td>{e(n['value'])}</td><td><small>{e(n['source'])}{(' - ' + e(n['detail'])) if n['detail'] else ''}</small></td></tr>")
        out.append("</table>")
        if card["predicted"]:
            out.append("<p><small>Predicted: " + ", ".join(f"{e(x['label'])} {e(x['value'])}" for x in card["predicted"]) + ".</small></p>")
        pr = card["printer"]
        if pr.get("id"):
            out.append(f"<p><small>Printer limits ({e(pr['id'])}): walls at least {e(str(pr.get('min_wall_mm')))} mm, openings at least {e(str(pr.get('min_opening_mm')))} mm.</small></p>")
        if card["confirm"]:
            out.append("<p><b>Please check (*):</b></p><ul>" + "".join(f"<li>{e(x)}</li>" for x in card["confirm"]) + "</ul>")
        for x in card["unsupported"] + card["ambiguities"]:
            out.append(f"<p style='color:#9a6700'>{e(x)}</p>")
        for x in card["notes"]:
            out.append(f"<p><small>Note: {e(x)}</small></p>")
        if card["citations"]:
            out.append("<p><small><b>References</b></small></p><ol>" + "".join(f"<li><small>{e(c)}</small></li>" for c in card["citations"]) + "</ol>")
        return "".join(out)
    if card.get("summary"):
        out.append(f"<p>{e(card['summary'])}</p>")
    out.append("<table cellspacing='0' cellpadding='4' width='100%'><tr><th align='left'>Measured</th><th align='left'>Value</th><th align='left'>Target</th></tr>")
    for m in card["measured"]:
        out.append(f"<tr><td>{e(m['label'])}</td><td>{e(m['value'])}</td><td>{e(m['target'])}</td></tr>")
    out.append("</table>")
    colours = {"pass": "#1a7f37", "warning": "#9a6700", "fail": "#b00020"}
    if card["printer_checks"]:
        out.append("<p><b>Printer check:</b> " + " &nbsp; ".join(f"<span style='color:{colours.get(c['status'], '#444')}'>{e(c['name'].replace('print_', ''))}: {e(c['status'])}</span>" for c in card["printer_checks"]) + "</p>")
    repairs = [r for it in card["iterations"] for r in it["repairs"]]
    if repairs:
        out.append("<p><small>Automatic repairs: " + "; ".join(f"{e(r['rule'])} {e(str(r['from']))} -> {e(str(r['to']))}" for r in repairs) + "</small></p>")
    return "".join(out)
