"""Run a system on AGE-Bench.

Systems
-------
``age``                  the design agent, deterministic parser
``age_llm:<model>``      the design agent with grounded OpenRouter extraction
``age_no_knowledge``     ablation: no literature presets
``age_no_feasibility``   ablation: no property tables / feasibility check, defaults for open values, no repair
``age_no_verifier``      ablation: one generation, no measurement-driven repair
``llm_direct:<model>``   LLM alone returns the design parameters (and a feasibility verdict) as JSON;
                         in ``full`` mode AGE's kernel builds and measures what it proposes, without repair
``llm_code:<model>``     LLM alone writes an implicit-field function (zero-shot code); it is run in a
                         separate, isolated Python process after a static whitelist check (opt-in)

Modes
-----
``extract``  planner only: extraction accuracy, invented values, application and out-of-scope detection
``propose``  planner + designer: adds feasibility detection (no geometry)
``full``     complete run: adds constraint satisfaction, property error, printability, iterations

Rows are appended to a JSONL file and the run can be resumed (``--resume``).
OpenRouter free models allow ~50 requests a day: use ``--limit`` / ``--tiers``.
"""

from __future__ import annotations

import ast
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from porous_designer.bench.prompts import Case, load_prompts

SPHERES = {"sc_spherical_pores", "bcc_spherical_pores", "fcc_spherical_pores", "hcp_spherical_pores"}
COMPARED = ("domain_shape", "domain_dimensions_mm", "family", "tpms_variant", "porosity", "porosity_min", "porosity_max", "pore_mm", "cell_mm", "min_wall_mm", "min_throat_mm", "process", "permeability_m2", "youngs_relative", "formats")


# ---------------------------------------------------------------------------
# comparison of values
# ---------------------------------------------------------------------------


def same(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(b, (list, tuple)):
        if not isinstance(a, (list, tuple)) or len(a) != len(b):
            return False
        if all(isinstance(x, str) for x in b):
            return sorted(map(str, a)) == sorted(map(str, b))
        return all(same(x, y) for x, y in zip(a, b))
    if isinstance(b, bool) or isinstance(a, bool):
        return bool(a) == bool(b)
    if isinstance(b, (int, float)):
        try:
            a = float(a)
        except (TypeError, ValueError):
            return False
        return math.isclose(a, float(b), rel_tol=2e-3, abs_tol=1e-9)
    return str(a).lower() == str(b).lower()


def score_extraction(case: Case, stated: dict[str, Any]) -> dict:
    """``stated``: the values a system attributes to the user's request."""
    correct, wrong, missing = [], [], []
    for key, value in case.expected.items():
        if key not in stated:
            missing.append(key)
        elif same(stated[key], value):
            correct.append(key)
        else:
            wrong.append({"field": key, "expected": value, "got": stated[key]})
    extra = [k for k in stated if k in COMPARED and k not in case.expected and k not in case.allowed]
    invented = [k for k in extra if k in case.forbidden] + [k for k in extra if k not in case.forbidden]
    return {"correct": correct, "wrong": wrong, "missing": missing, "invented": invented, "forbidden_violations": [k for k in extra if k in case.forbidden]}


# ---------------------------------------------------------------------------
# AGE systems
# ---------------------------------------------------------------------------


def _openrouter(model: str | None):
    from porous_designer.agentic.contracts import ProviderMode
    from porous_designer.agentic.provider_config import ExternalCallMode, load_provider_settings
    from porous_designer.agentic.provider_factory import provider_from_settings

    settings = load_provider_settings()
    settings.external_access_enabled = True
    settings.provider_mode = ProviderMode.OPENROUTER
    settings.external_call_mode = ExternalCallMode.ALWAYS
    if model:
        settings.openrouter_model = model
        settings.openrouter_fallback_models = []
    return provider_from_settings(settings), settings


def make_agent(system: str, out_dir: Path, voxel_budget: int):
    from porous_designer.agentic.design_agent import DesignAgent

    kw: dict[str, Any] = {"output_dir": out_dir, "auto_approve": True, "voxel_budget": voxel_budget}
    name, _, model = system.partition(":")
    if name == "age_llm":
        kw["provider"], kw["settings"] = _openrouter(model or None)
    elif name == "age_no_knowledge":
        kw["use_knowledge"] = False
    elif name == "age_no_feasibility":
        kw.update(use_feasibility=False, max_iterations=1)
    elif name == "age_no_verifier":
        kw["max_iterations"] = 1
    elif name != "age":
        raise ValueError(f"unknown AGE system {system}")
    return DesignAgent(**kw)


def run_age_case(agent, case: Case, mode: str) -> dict:
    t0 = time.perf_counter()
    row: dict[str, Any] = {}
    if mode == "extract":
        intent = agent.plan(case.text, [])
        status = "planned"
        result = None
    else:
        result = agent.propose(case.text)
        intent = result.intent
        status = result.status
        if mode == "full" and status != "infeasible":
            result = agent.execute(result)
            status = result.status
    stated = {k: v.value for k, v in intent.values.items() if v.source == "user"}
    row["stated"] = stated
    row["parser"] = intent.parser  # mode, version, provider_failed (an LLM system that fell back is reported as such)
    row["application"] = intent.application
    row["unsupported"] = intent.unsupported
    row["confirmations"] = sum(1 for v in intent.values.values() if v.requires_confirmation)
    row["status"] = status
    if mode != "extract":
        row["predicted_feasible"] = status != "infeasible"
    if result is not None and mode == "full" and result.iterations:
        last = result.iterations[-1]["verification"]
        row["iterations"] = len(result.iterations)
        row["checks"] = {k: v["status"] for k, v in last["checks"].items()}
        row["measurements"] = last["measurements"]
        gen = result.generation
        row["porosity_measured"] = getattr(gen, "final_mesh_porosity", None)
        row["porosity_target"] = result.specification.targets.porosity_target.target if result.specification else None
        row["pore_target_mm"] = intent.get("pore_mm") if intent.get("family") not in SPHERES else None
        row["run_dir"] = last["run_dir"]
    row["time_s"] = time.perf_counter() - t0
    return row


# ---------------------------------------------------------------------------
# LLM-only baselines
# ---------------------------------------------------------------------------

DIRECT_PROMPT = """You design printable porous scaffolds. Read the request and answer with ONE JSON object only, no prose:
{"domain_shape": "box|cylinder|sphere", "domain_dimensions_mm": [..], "family": one of %s,
 "tpms_variant": "sheet|network|null", "porosity": 0-1, "cell_mm": number|null, "pore_mm": number|null,
 "min_wall_mm": number|null, "min_throat_mm": number|null, "process": "fdm|sla|dlp|volumetric|bioprinting|sls|lpbf|null",
 "youngs_relative": number|null, "permeability_m2": number|null,
 "stated_by_user": [names of the fields above that the request itself states],
 "feasible": true|false, "reason": "one sentence"}
Box dimensions are [x, y, z]; cylinder [diameter, height]; sphere [diameter]. Choose sensible values for anything unstated.
Request: """

CODE_PROMPT = """Write a Python function `field(x, y, z)` for this porous part. x, y, z are numpy arrays of coordinates in mm
(the part's bounding box starts at 0). Return a numpy array: negative inside SOLID material, positive in pores and outside the part.
Use only `import numpy as np`. No file access, no other imports. Reply with the code only.
Request: """


def _llm_chat(model: str, prompt: str) -> str:
    from porous_designer.agentic.credentials import lookup_api_key
    from porous_designer.agentic.openrouter import OpenRouterClient
    from porous_designer.agentic.provider_config import CredentialMode

    cred = lookup_api_key("openrouter", CredentialMode.KEYRING)
    if not cred.available or not cred.key:
        raise RuntimeError("OpenRouter key unavailable (python -m porous_designer.cli credentials set)")
    from porous_designer.agentic.openrouter import OpenRouterError

    client = OpenRouterClient(cred.key, timeout_s=120)
    body = {"model": model, "temperature": 0, "seed": 7, "messages": [{"role": "user", "content": prompt}]}
    for attempt in range(3):
        try:
            return client.chat(body, timeout_s=120).content
        except OpenRouterError as exc:  # free models are often rate-limited upstream for a short time
            if attempt == 2 or not (exc.retryable or "rate-limit" in str(exc)):
                raise
            time.sleep(20 * (attempt + 1))
    raise RuntimeError("unreachable")


def _json_object(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start : end + 1])


def _spec_from_direct(params: dict, out_dir: Path, voxel_budget: int):
    from porous_designer.agentic.design_agent import DesignAgent, DesignIntent
    from porous_designer.domain.enums import DomainShape, StructureFamily, TPMSVariant
    from porous_designer.domain.specification import DomainSpec
    from porous_designer.knowledge.feasibility import Requirements, evaluate

    agent = DesignAgent(output_dir=out_dir, auto_approve=True, voxel_budget=voxel_budget, use_feasibility=False, max_iterations=1)
    intent = DesignIntent(request="llm_direct")
    for key in ("family", "tpms_variant", "porosity", "cell_mm", "pore_mm", "min_wall_mm", "min_throat_mm", "resolution_mm"):
        if params.get(key) not in (None, "null"):
            intent.set(key, params[key], "user", "llm_direct")
    fam = StructureFamily(params.get("family") or "gyroid")
    var = TPMSVariant(params.get("tpms_variant") or "sheet") if fam.is_tpms and params.get("tpms_variant") in ("sheet", "network") else TPMSVariant.SHEET
    domain = DomainSpec(shape=DomainShape(params.get("domain_shape") or "box"), dimensions_mm=[float(v) for v in params.get("domain_dimensions_mm") or [10, 10, 10]])
    if intent.get("porosity") is None:
        intent.set("porosity", 0.7, "default", "")
    if not fam.is_sphere_lattice and intent.get("cell_mm") is None:
        intent.set("cell_mm", 2.0, "default", "")
    length = float(intent.get("pore_mm") or 1.0) if fam.is_sphere_lattice else float(intent.get("cell_mm"))
    intent.set("resolution_mm", round(agent._fit_resources(domain, min(0.2, max(0.02, length / 25.0))), 4), "default", "")
    printer = agent.printer(DesignIntent(request="", values={}) if not params.get("process") else _intent_with_process(params["process"]))
    point = evaluate(fam, var, float(intent.get("porosity")), length, Requirements())
    return agent, agent._build_spec(intent, domain, fam, var, point, printer)


def _intent_with_process(process: str):
    from porous_designer.agentic.design_agent import DesignIntent

    i = DesignIntent(request="")
    i.set("process", process, "user", "")
    return i


def run_llm_direct_case(model: str, case: Case, mode: str, out_dir: Path, voxel_budget: int) -> dict:
    t0 = time.perf_counter()
    reply = _llm_chat(model, DIRECT_PROMPT % json.dumps(sorted(["gyroid", "diamond", "primitive", "iwp", "neovius", "fischer_koch_s", "lidinoid", "strut_cubic", "strut_bcc", "strut_octet", "strut_kelvin", "voronoi_foam", *SPHERES])) + case.text)
    params = _json_object(reply)
    stated_names = set(params.get("stated_by_user") or [])
    stated = {k: params[k] for k in stated_names if k in params and params[k] not in (None, "null")}
    row: dict[str, Any] = {"stated": stated, "all_values": params, "predicted_feasible": bool(params.get("feasible", True)), "status": "proposed", "reason": params.get("reason")}
    row["unsupported"] = [params["reason"]] if not params.get("feasible", True) and params.get("reason") else []
    if mode == "full" and row["predicted_feasible"]:
        from porous_designer.services.generation_service import generate_porous_stl

        agent, spec = _spec_from_direct(params, out_dir, voxel_budget)
        gen = generate_porous_stl(spec)
        report = json.loads((Path(gen.run_dir) / "validation_report.json").read_text(encoding="utf-8"))
        row["checks"] = {c["name"]: c["status"] for c in report["checks"]}
        row["measurements"] = gen.measurements
        row["porosity_measured"] = gen.final_mesh_porosity
        row["porosity_target"] = spec.targets.porosity_target.target
        row["pore_target_mm"] = params.get("pore_mm") if params.get("family") not in SPHERES else None
        row["iterations"] = 1
        row["status"] = "delivered" if gen.success else "failed"
    row["time_s"] = time.perf_counter() - t0
    return row


NP_ALLOWED = {
    "sin", "cos", "tan", "arcsin", "arccos", "arctan", "arctan2", "sinh", "cosh", "tanh", "sqrt", "cbrt", "square", "power",
    "exp", "log", "log2", "log10", "abs", "absolute", "fabs", "sign", "floor", "ceil", "round", "rint", "trunc", "mod", "fmod",
    "remainder", "minimum", "maximum", "fmin", "fmax", "clip", "where", "hypot", "pi", "e", "inf", "zeros_like", "ones_like",
    "full_like", "zeros", "ones", "full", "stack", "array", "asarray", "linspace", "arange", "meshgrid", "min", "max", "amin",
    "amax", "sum", "mean", "float32", "float64", "logical_and", "logical_or", "logical_not", "isfinite", "nan_to_num", "dot",
    "einsum", "sort", "argmin", "argmax", "take_along_axis", "expand_dims", "broadcast_to", "concatenate", "outer", "random", "linalg", "norm",
}
NP_RANDOM_ALLOWED = {"default_rng", "seed", "rand", "uniform", "random", "normal", "integers"}
ARRAY_DENIED = {"tofile", "dump", "dumps", "ctypes", "data", "base", "tobytes", "__array_interface__"}
FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr", "delattr", "input", "breakpoint", "exit", "quit", "help", "memoryview", "type", "object", "super"}


def check_code(code: str) -> str | None:
    """Static whitelist for LLM code: numpy only, no dunders, no I/O builtins. None if acceptable."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"syntax error: {exc}"
    has_field = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if any(n.split(".")[0] != "numpy" for n in names):
                return f"import not allowed: {names}"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return f"private attribute: {node.attr}"
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in ("np", "numpy") and node.attr not in NP_ALLOWED:
            return f"numpy function not allowed: np.{node.attr}"
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) and node.value.attr == "random" and node.attr not in NP_RANDOM_ALLOWED:
            return f"numpy function not allowed: random.{node.attr}"
        elif isinstance(node, ast.Attribute) and node.attr in ARRAY_DENIED:
            return f"attribute not allowed: {node.attr}"
        elif isinstance(node, ast.Name) and (node.id in FORBIDDEN_NAMES or node.id.startswith("__")):
            return f"name not allowed: {node.id}"
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.With, ast.AsyncWith, ast.Await)):
            return f"statement not allowed: {type(node).__name__}"
        elif isinstance(node, ast.FunctionDef) and node.name == "field":
            has_field = True
    return None if has_field else "no function named field"


CHILD = r"""
import sys, numpy as np
ns = {"np": np, "numpy": np, "__builtins__": {"range": range, "len": len, "abs": abs, "min": min, "max": max, "float": float, "int": int, "round": round, "sum": sum, "zip": zip, "enumerate": enumerate, "list": list, "tuple": tuple, "dict": dict, "True": True, "False": False, "None": None, "__import__": __import__}}
code = open(sys.argv[1], encoding="utf-8").read()
exec(compile(code, "llm_code", "exec"), ns)
g = np.load(sys.argv[2])
out = np.asarray(ns["field"](g["x"], g["y"], g["z"]), dtype=np.float32)
np.save(sys.argv[3], out)
"""


def run_llm_code_case(model: str, case: Case, mode: str, out_dir: Path, voxel_budget: int, *, allow: bool) -> dict:
    t0 = time.perf_counter()
    reply = _llm_chat(model, CODE_PROMPT + case.text)
    code = reply.strip()
    if "```" in code:
        blocks = code.split("```")
        code = max(blocks[1::2], key=len)
        code = code[len("python") :] if code.startswith("python") else code
    row: dict[str, Any] = {"stated": {}, "code_chars": len(code), "status": "code"}
    problem = check_code(code)
    row["code_check"] = problem or "ok"
    if problem or mode != "full" or not allow:
        row["time_s"] = time.perf_counter() - t0
        return row
    import numpy as np

    from porous_designer.metrology import morphology as mm

    dims = case.expected.get("domain_dimensions_mm") or [10.0, 10.0, 10.0]
    shape = case.expected.get("domain_shape", "box")
    ext = {"box": dims, "cylinder": [dims[0], dims[0], dims[-1]], "sphere": [dims[0]] * 3}[shape]
    h = max(0.02, (float(np.prod(ext)) / min(voxel_budget, 8_000_000)) ** (1 / 3))
    axes = [np.arange(int(e / h)) * h + h / 2 for e in ext]
    x, y, z = np.meshgrid(*axes, indexing="ij")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "code.py").write_text(code, encoding="utf-8")
        np.savez(tmp / "grid.npz", x=x.astype(np.float32), y=y.astype(np.float32), z=z.astype(np.float32))
        try:
            proc = subprocess.run([sys.executable, "-I", "-c", CHILD, str(tmp / "code.py"), str(tmp / "grid.npz"), str(tmp / "out.npy")], cwd=tmp, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            row["status"] = "failed"
            row["error"] = "timeout"
            row["time_s"] = time.perf_counter() - t0
            return row
        if proc.returncode != 0 or not (tmp / "out.npy").exists():
            row["status"] = "failed"
            row["error"] = proc.stderr[-500:]
            row["time_s"] = time.perf_counter() - t0
            return row
        values = np.load(tmp / "out.npy")
    if values.shape != x.shape:
        row.update(status="failed", error=f"field returned shape {values.shape}")
        row["time_s"] = time.perf_counter() - t0
        return row
    c = [e / 2 for e in ext]
    inside = np.ones(x.shape, bool)
    if shape == "cylinder":
        inside = (x - c[0]) ** 2 + (y - c[1]) ** 2 <= (dims[0] / 2) ** 2
    elif shape == "sphere":
        inside = (x - c[0]) ** 2 + (y - c[1]) ** 2 + (z - c[2]) ** 2 <= (dims[0] / 2) ** 2
    solid = (values < 0) & inside
    porosity = 1.0 - solid.sum() / max(inside.sum(), 1)
    crop = mm.central_crop(solid.shape, 1_500_000)
    pore = mm.size_distribution((~solid & inside)[crop], h, "pore")
    wall = mm.size_distribution(solid[crop], h, "wall")
    target = case.expected.get("porosity") or (0.5 * (case.expected["porosity_min"] + case.expected["porosity_max"]) if "porosity_min" in case.expected else None)
    row.update(
        status="delivered",
        iterations=1,
        porosity_measured=float(porosity),
        porosity_target=target,
        pore_target_mm=case.expected.get("pore_mm"),
        measurements={"pore_d50_mm": pore.d50, "wall_d50_mm": wall.d50, "wall_min_mm": wall.d10},
        voxel_mm=h,
    )
    row["time_s"] = time.perf_counter() - t0
    return row


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------


def select(cases: list[Case], *, tiers: list[int] | None = None, limit: int | None = None, per_tier: int | None = None) -> list[Case]:
    if tiers:
        cases = [c for c in cases if c.tier in tiers]
    if per_tier:
        picked, count = [], {}
        for c in cases:
            if count.get(c.tier, 0) < per_tier:
                picked.append(c)
                count[c.tier] = count.get(c.tier, 0) + 1
        cases = picked
    return cases[:limit] if limit else cases


def run_bench(
    system: str,
    *,
    mode: str = "extract",
    output: Path,
    tiers: list[int] | None = None,
    limit: int | None = None,
    per_tier: int | None = None,
    resume: bool = True,
    voxel_budget: int | None = None,
    allow_llm_code: bool = False,
    log: Callable[[str], None] = print,
) -> Path:
    # The design budget is the agent's default (60 M grid points); full mode caps it so a
    # benchmark slice finishes in minutes. The cap is part of the recorded row.
    voxel_budget = voxel_budget or (8_000_000 if mode == "full" else 60_000_000)
    cases = select(load_prompts(), tiers=tiers, limit=limit, per_tier=per_tier)
    output.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if not resume and output.exists():
        output.unlink()
    if resume and output.exists():
        # errored prompts (and LLM calls that fell back) are retried on resume
        done = {r["id"] for r in (json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line.strip()) if r.get("status") not in ("error", "provider_failed")}
    run_dir = output.parent / (output.stem + "_runs")
    agent = make_agent(system, run_dir, voxel_budget) if system.split(":")[0].startswith("age") else None
    name, _, model = system.partition(":")
    with output.open("a", encoding="utf-8") as fh:
        for i, case in enumerate(cases, 1):
            if case.id in done:
                continue
            base = {"id": case.id, "tier": case.tier, "system": system, "mode": mode, "voxel_budget": voxel_budget}
            try:
                if agent is not None:
                    row = run_age_case(agent, case, mode)
                elif name == "llm_direct":
                    row = run_llm_direct_case(model, case, mode, run_dir, voxel_budget)
                elif name == "llm_code":
                    row = run_llm_code_case(model, case, mode, run_dir, voxel_budget, allow=allow_llm_code)
                else:
                    raise ValueError(f"unknown system {system}")
                row["error"] = row.get("error")
            except Exception as exc:  # recorded, the run continues
                row = {"status": "error", "error": f"{type(exc).__name__}: {exc}", "stated": {}}
            row.update(base)
            if name == "age_llm" and (row.get("parser") or {}).get("provider_failed"):
                row["status"] = "provider_failed"  # the deterministic fallback answered, not the LLM
            row["score"] = score_extraction(case, row.get("stated") or {})
            fh.write(json.dumps(row, default=str) + "\n")
            fh.flush()
            log(f"[{i}/{len(cases)}] {case.id} {row['status']} ({row.get('time_s', 0):.1f} s)")
    return output
