"""AGE-Bench metrics: aggregate runner rows into comparison tables."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from porous_designer.bench.prompts import load_prompts


PRINT_ADVISORY = {"print_file_size", "print_robust_wall"}  # recommendations, not printability limits


def _rate(num: int, den: int) -> float | None:
    return num / den if den else None


def summarise(rows: list[dict]) -> dict:
    cases = {c.id: c for c in load_prompts()}
    rows = [r for r in rows if r["id"] in cases]
    failed = [r for r in rows if r["status"] in ("error", "provider_failed")]
    out: dict = {"n": len(rows), "errors": sum(r["status"] == "error" for r in rows), "provider_failed": sum(r["status"] == "provider_failed" for r in rows)}
    rows = [r for r in rows if r not in failed]  # scored on answered prompts only; failures are reported above
    out["n_scored"] = len(rows)
    exp_fields = sum(len(cases[r["id"]].expected) for r in rows)
    correct = sum(len(r["score"]["correct"]) for r in rows)
    wrong = sum(len(r["score"]["wrong"]) for r in rows)
    invented = [r for r in rows if r["score"]["invented"]]
    out["extraction_field_accuracy"] = _rate(correct, exp_fields)
    out["extraction_wrong_rate"] = _rate(wrong, exp_fields)
    out["extraction_exact_match"] = _rate(sum(not r["score"]["wrong"] and not r["score"]["missing"] and not r["score"]["invented"] for r in rows), len(rows))
    out["hallucination_rate"] = _rate(len(invented), len(rows))  # prompts with >= 1 value attributed to the user but not in the request
    out["invented_per_prompt"] = _rate(sum(len(r["score"]["invented"]) for r in rows), len(rows))
    t3 = [r for r in rows if cases[r["id"]].tier == 3]
    if t3:
        out["application_accuracy"] = _rate(sum((r.get("application") or None) == cases[r["id"]].application for r in t3), len(t3))
    t6 = [r for r in rows if cases[r["id"]].out_of_scope]
    if t6:
        out["out_of_scope_flagged"] = _rate(sum(bool(r.get("unsupported")) for r in t6), len(t6))
    labelled = [r for r in rows if cases[r["id"]].expect_feasible is not None and "predicted_feasible" in r]
    if labelled:
        truth = [cases[r["id"]].expect_feasible for r in labelled]
        pred = [r["predicted_feasible"] for r in labelled]
        out["feasibility_accuracy"] = _rate(sum(t == p for t, p in zip(truth, pred)), len(labelled))
        inf = [p for t, p in zip(truth, pred) if t is False]
        fea = [p for t, p in zip(truth, pred) if t is True]
        out["infeasible_detected"] = _rate(sum(not p for p in inf), len(inf))
        out["false_infeasible"] = _rate(sum(not p for p in fea), len(fea))
    impossible = [r for r in rows if cases[r["id"]].expect_feasible is False and r.get("mode") == "full"]
    if impossible:
        # geometry delivered for a request that cannot be met as stated (it silently answers another question)
        out["impossible_delivered"] = _rate(sum(r["status"] in ("delivered", "delivered_with_warnings") for r in impossible), len(impossible))
    full = [r for r in rows if r.get("iterations")]
    if full:
        out["n_generated"] = len(full)
        out["constraint_satisfaction"] = _rate(sum(r["status"] == "delivered" or (r["status"] == "delivered_with_warnings" and not any(v == "fail" for v in (r.get("checks") or {}).values())) for r in full), len(full))
        pe = [abs(r["porosity_measured"] - r["porosity_target"]) for r in full if r.get("porosity_measured") is not None and r.get("porosity_target") is not None]
        out["porosity_abs_error_mean"] = statistics.fmean(pe) if pe else None
        re_ = [abs(r["measurements"]["pore_d50_mm"] - r["pore_target_mm"]) / r["pore_target_mm"] for r in full if r.get("pore_target_mm") and (r.get("measurements") or {}).get("pore_d50_mm")]
        out["pore_rel_error_mean"] = statistics.fmean(re_) if re_ else None
        pr = [r for r in full if any(k.startswith("print_") for k in (r.get("checks") or {}))]
        # printable: no print_* failure or warning, except the advisory ones
        out["n_with_printer"] = len(pr)
        out["printability_pass_rate"] = _rate(sum(all(v == "pass" for k, v in r["checks"].items() if k.startswith("print_") and k not in PRINT_ADVISORY) for r in pr), len(pr))
        out["iterations_mean"] = statistics.fmean(r["iterations"] for r in full)
    times = [r.get("time_s") for r in rows if r.get("time_s") is not None]
    out["time_s_median"] = statistics.median(times) if times else None
    conf = [r["confirmations"] for r in rows if "confirmations" in r]
    if conf:
        out["user_effort_mean"] = 2 + statistics.fmean(conf)  # two checkpoints + values to confirm
    return out


def load_rows(path: Path) -> list[dict]:
    """Rows of a run file; if a prompt appears more than once (resumed runs) the last row counts."""
    rows = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row
    return list(rows.values())


def summarise_file(path: Path, *, by_tier: bool = True) -> dict:
    rows = load_rows(path)
    result = {"overall": summarise(rows)}
    if by_tier:
        tiers = defaultdict(list)
        for r in rows:
            tiers[r["tier"]].append(r)
        result["by_tier"] = {t: summarise(v) for t, v in sorted(tiers.items())}
    return result


KEYS = [
    ("extraction_field_accuracy", "field acc."),
    ("extraction_exact_match", "exact"),
    ("hallucination_rate", "invented"),
    ("application_accuracy", "application"),
    ("out_of_scope_flagged", "out-of-scope"),
    ("feasibility_accuracy", "feasibility"),
    ("infeasible_detected", "infeasible found"),
    ("false_infeasible", "false infeasible"),
    ("impossible_delivered", "impossible delivered"),
    ("constraint_satisfaction", "constraints met"),
    ("porosity_abs_error_mean", "porosity err."),
    ("pore_rel_error_mean", "pore err."),
    ("printability_pass_rate", "printable"),
    ("iterations_mean", "iter."),
    ("time_s_median", "time s"),
    ("user_effort_mean", "effort"),
]


def markdown_table(summaries: dict[str, dict]) -> str:
    """``summaries``: system name -> ``summarise`` output."""
    used = [(k, label) for k, label in KEYS if any(s.get(k) is not None for s in summaries.values())]
    head = "| system | n | " + " | ".join(label for _, label in used) + " |"
    sep = "|---|---|" + "|".join("---" for _ in used) + "|"
    lines = [head, sep]
    for name, s in summaries.items():
        cells = []
        for k, _ in used:
            v = s.get(k)
            cells.append("-" if v is None else (f"{v:.1f}" if k in ("time_s_median", "iterations_mean", "user_effort_mean") else (f"{v:.3f}" if k.endswith("error_mean") else f"{v:.0%}")))
        lines.append(f"| {name} | {s.get('n_scored', s['n'])}/{s['n']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
