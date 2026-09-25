"""AGE-Bench prompt set.

Every case is generated from a template with seeded random choices, so the
set is reproducible (``build_prompts(seed)``) and every stated value is known:

``expected``         intent values the request states (the ground truth for extraction)
``allowed``          values a system may add without it counting as invented
                     (e.g. the midpoint of a stated porosity range)
``forbidden``        quantities the request does not state; a system that
                     reports them as *stated by the user* has invented them
``expect_feasible``  True / False where physically decidable, else None
``application``      the application a lay request refers to (tier 3)
``out_of_scope``     the request asks for something AGE does not do (tier 6)

Tiers
-----
1 explicit      engineering wording, all main parameters stated
2 partial       some parameters left open (the agent must choose them)
3 application   lay / clinical wording; values must come from the literature
4 constrained   walls, openings, stiffness or permeability targets, printers
5 infeasible    physically impossible with the stated printer or part size
6 out_of_scope  scan-to-part, inverse / topology optimisation, multi-material, ...
7 paraphrase    held-out everyday wording (see below)

Tiers 1-6 use wording the deterministic parser was developed with. Tier 7 was
written afterwards and the parser was *not* changed for it: it measures how
the rule-based planner degrades on unfamiliar wording, and is where a grounded
LLM extractor is expected to help.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "age_bench_v1.jsonl"

TPMS = [("gyroid", "gyroid"), ("diamond", "diamond"), ("primitive", "Schwarz primitive"), ("iwp", "IWP"), ("neovius", "Neovius"), ("fischer_koch_s", "Fischer-Koch S"), ("lidinoid", "lidinoid")]
STRUTS = [("strut_cubic", "simple cubic strut lattice"), ("strut_bcc", "BCC strut lattice"), ("strut_octet", "octet truss"), ("strut_kelvin", "Kelvin cell lattice")]
FOAMS = [("voronoi_foam", "Voronoi foam")]
SPHERES = [("sc_spherical_pores", "simple cubic spherical pores"), ("bcc_spherical_pores", "BCC spherical pores"), ("fcc_spherical_pores", "FCC spherical pores"), ("hcp_spherical_pores", "HCP spherical pores")]
PROCESSES = [
    ("sla", ["resin printer", "SLA printer", "MSLA resin printer"]),
    ("dlp", ["DLP printer"]),
    ("fdm", ["FDM printer", "filament printer"]),
    ("volumetric", ["volumetric printer", "tomographic volumetric printer"]),
    ("bioprinting", ["extrusion bioprinter"]),
    ("sls", ["SLS printer"]),
    ("lpbf", ["laser powder bed (LPBF) machine"]),
]


@dataclass
class Case:
    id: str
    tier: int
    text: str
    expected: dict = field(default_factory=dict)
    allowed: list = field(default_factory=list)
    forbidden: list = field(default_factory=list)
    expect_feasible: bool | None = None
    application: str | None = None
    out_of_scope: bool = False
    tags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# phrase builders
# ---------------------------------------------------------------------------


def _num(v: float) -> str:
    return f"{v:g}"


def _domain(r: random.Random, *, small: bool = False) -> tuple[str, dict]:
    kind = r.choice(["box", "box", "cube", "cylinder", "cylinder", "sphere"])
    lo, hi = (4, 12) if small else (6, 20)
    if kind == "box":
        d = [float(r.randint(lo, hi)) for _ in range(3)]
        text = r.choice(["{a} x {b} x {c} mm box", "{a} x {b} x {c} mm block", "box of {a} x {b} x {c} mm", "{a} by {b} by {c} mm cuboid"]).format(a=_num(d[0]), b=_num(d[1]), c=_num(d[2]))
        return text, {"domain_shape": "box", "domain_dimensions_mm": d}
    if kind == "cube":
        a = float(r.randint(lo, hi))
        text = r.choice(["{a} mm cube", "cube of {a} mm"]).format(a=_num(a))
        return text, {"domain_shape": "box", "domain_dimensions_mm": [a, a, a]}
    if kind == "cylinder":
        dia, h = float(r.randint(lo, hi)), float(r.randint(max(2, lo // 2), hi))
        text = r.choice(["cylinder {d} mm in diameter and {h} mm tall", "cylindrical plug with diameter {d} mm and height {h} mm", "{d} mm diameter, {h} mm high cylinder"]).format(d=_num(dia), h=_num(h))
        return text, {"domain_shape": "cylinder", "domain_dimensions_mm": [dia, h]}
    dia = float(r.randint(lo, hi))
    return f"sphere of {_num(dia)} mm diameter", {"domain_shape": "sphere", "domain_dimensions_mm": [dia]}


def _porosity(r: random.Random, lo=0.5, hi=0.8) -> tuple[str, dict, list]:
    if r.random() < 0.2:
        a = round(r.uniform(lo, hi - 0.1) * 20) / 20
        b = round(a + 0.1, 2)
        text = r.choice(["{a}-{b}% porosity", "porosity between {a}% and {b}%"]).format(a=int(round(a * 100)), b=int(round(b * 100)))
        return text, {"porosity_min": a, "porosity_max": b}, ["porosity"]
    p = round(r.uniform(lo, hi) * 20) / 20
    text = r.choice(["{p}% porosity", "porosity of {p}%", "{p}% porous"]).format(p=int(round(p * 100)))
    return text, {"porosity": p}, []


def _family(r: random.Random, pool=None) -> tuple[str, str, dict]:
    group = r.choice(pool or ["tpms", "tpms", "tpms", "strut", "foam", "sphere"])
    if group == "tpms":
        key, name = r.choice(TPMS)
        exp = {"family": key}
        if r.random() < 0.35:
            var = r.choice(["sheet", "network"])
            name = f"{var} {name}"
            exp["tpms_variant"] = var
        return group, name, exp
    key, name = r.choice({"strut": STRUTS, "foam": FOAMS, "sphere": SPHERES}[group])
    return group, name, {"family": key}


def _length(r: random.Random, group: str) -> tuple[str, dict]:
    if group == "sphere":
        d = r.choice([0.6, 0.8, 1.0, 1.2, 1.5])
        text = r.choice(["pore diameter {d} mm", "{d} mm pores", "pores of {um} um"]).format(d=_num(d), um=int(d * 1000))
        return text, {"pore_mm": d}
    c = r.choice([2.0, 2.5, 3.0, 3.5, 4.0])
    text = r.choice(["{c} mm unit cell", "unit cell size of {c} mm", "cell size {c} mm"]).format(c=_num(c))
    return text, {"cell_mm": c}


# Porosity above which neighbouring spherical pores overlap and the pore space is open
# (below it the spheres are isolated: SC 52 %, BCC 68 %, FCC/HCP 74 % packing).
OPEN_SPHERE_POROSITY = {"sc_spherical_pores": 0.55, "bcc_spherical_pores": 0.72, "fcc_spherical_pores": 0.78, "hcp_spherical_pores": 0.78}


def _sphere_label(fam: dict, por: dict, feasible):
    """Open-pore sphere packings below their percolation porosity are not decidable as 'feasible'."""
    limit = OPEN_SPHERE_POROSITY.get(fam.get("family"))
    if limit is None or feasible is not True:
        return feasible
    top = por.get("porosity_max", por.get("porosity", 0.7))
    return True if top >= limit + 0.02 else None


def _join(parts: list[str], r: random.Random) -> str:
    lead = r.choice(["Generate a", "Design a", "Create a", "Make a", "I need a"])
    body = ", ".join(p for p in parts if p)
    return f"{lead} {body}."


# ---------------------------------------------------------------------------
# tiers
# ---------------------------------------------------------------------------


def tier1(r: random.Random, n: int) -> list[Case]:
    out = []
    for i in range(n):
        group, fam_text, fam = _family(r)
        dom_text, dom = _domain(r)
        por_text, por, allowed = _porosity(r)
        len_text, length = _length(r, group)
        exp = {**fam, **dom, **por, **length}
        # a stated part must hold >= 2 cells: keep ground truth feasible when no printer is named
        if "cell_mm" in length and min(dom["domain_dimensions_mm"]) < 2 * length["cell_mm"]:
            feasible = None
        else:
            feasible = True
        extras = []
        if r.random() < 0.25:
            extras.append(r.choice(["export STL and 3MF", "STL output"]))
            exp["formats"] = ["3mf", "stl"] if "3MF" in extras[-1] else ["stl"]
        parts = [f"{dom_text} {fam_text} scaffold" if r.random() < 0.5 else f"{fam_text} scaffold, {dom_text}", por_text, len_text, *extras]
        r.shuffle(parts[1:])
        out.append(Case(f"t1_{i:03d}", 1, _join(parts, r), exp, allowed, [], _sphere_label(fam, por, feasible)))
    return out


def tier2(r: random.Random, n: int) -> list[Case]:
    out = []
    for i in range(n):
        group, fam_text, fam = _family(r)
        dom_text, dom = _domain(r)
        por_text, por, allowed = _porosity(r)
        drop = r.choice(["length", "length", "porosity", "family", "length+porosity"])
        exp, forbidden, parts = {**dom}, [], []
        if "family" in drop:
            parts.append(f"porous scaffold, {dom_text}")
            forbidden.append("family")
        else:
            parts.append(f"{fam_text} scaffold, {dom_text}")
            exp.update(fam)
        if "porosity" in drop:
            forbidden += ["porosity"]
        else:
            parts.append(por_text)
            exp.update(por)
        if "length" in drop or group != "sphere":
            forbidden += ["cell_mm"] if group != "sphere" or "family" in drop else ["pore_mm"]
        if "length" not in drop:
            len_text, length = _length(r, group if "family" not in drop else "tpms")
            parts.append(len_text)
            exp.update(length)
            forbidden = [f for f in forbidden if f not in length]
        forbidden += ["min_wall_mm", "min_throat_mm"]
        feasible = True if "cell_mm" not in exp else None
        if "family" in exp and exp["family"] in OPEN_SPHERE_POROSITY:
            feasible = _sphere_label(exp, por if "porosity" not in drop else {"porosity": 1.0}, feasible)
        out.append(Case(f"t2_{i:03d}", 2, _join(parts, r), exp, allowed, sorted(set(forbidden)), feasible))
    return out


APPLICATION_TEMPLATES = [
    ("bone", "I need a bone graft to fill a {dom} defect, printed on our {proc}."),
    ("bone", "Porous implant for a trabecular bone defect, {dom}, {proc}."),
    ("bone", "Scaffold for an orthopaedic bone defect in a rabbit femur, {dom}."),
    ("bone", "Osteogenic scaffold, {dom}, to be printed with a {proc}."),
    ("skin", "A dermal substitute patch, {dom}, for wound healing, printed on a {proc}."),
    ("skin", "Something to fill a chronic wound, about {dom}."),
    ("skin", "Wound dressing scaffold {dom} for our {proc}."),
    ("collagen_bone_culture", "Collagen scaffold for bone cell culture, {dom}."),
    (None, "A spongy block, {dom}, with lots of little holes, printed on a {proc}."),
    (None, "Lightweight porous insert, {dom}, for a {proc}."),
]


def tier3(r: random.Random, n: int) -> list[Case]:
    out = []
    for i in range(n):
        app, tmpl = r.choice(APPLICATION_TEMPLATES)
        dom_text, dom = _domain(r)
        proc_key, words = r.choice(PROCESSES[:3] + PROCESSES[3:5])
        text = tmpl.format(dom=dom_text, proc=r.choice(words))
        exp = {**dom}
        if "{proc}" in tmpl:
            exp["process"] = proc_key
        forbidden = ["porosity", "pore_mm", "cell_mm", "min_wall_mm", "min_throat_mm"]
        if "trabecular" in tmpl:
            exp["family"] = "voronoi_foam"  # the controlled vocabulary maps 'trabecular' to a Voronoi foam
        else:
            forbidden.append("family")
        out.append(Case(f"t3_{i:03d}", 3, text, exp, [], forbidden, None, application=app))
    return out


def tier4(r: random.Random, n: int) -> list[Case]:
    out = []
    for i in range(n):
        group, fam_text, fam = _family(r, ["tpms", "tpms", "strut"])
        dom_text, dom = _domain(r)
        por_text, por, allowed = _porosity(r, 0.5, 0.75)
        exp = {**fam, **dom, **por}
        parts = [f"{fam_text} scaffold, {dom_text}", por_text]
        kind = r.choice(["wall", "throat", "printer", "stiffness", "permeability", "wall+printer"])
        feasible = None
        if "wall" in kind:
            w = r.choice([0.3, 0.4, 0.5])
            parts.append(r.choice(["walls of at least {w} mm", "minimum wall thickness {w} mm", "strut diameter at least {w} mm" if group == "strut" else "walls at least {w} mm"]).format(w=_num(w)))
            exp["min_wall_mm"] = w
        if kind == "throat":
            t = r.choice([0.4, 0.5, 0.6])
            parts.append(r.choice(["pore openings of at least {t} mm", "minimum throat size {t} mm"]).format(t=_num(t)))
            exp["min_throat_mm"] = t
        if "printer" in kind:
            proc_key, words = r.choice(PROCESSES[:3])
            parts.append(f"printed on a {r.choice(words)}")
            exp["process"] = proc_key
        if kind == "stiffness":
            e = r.choice([0.05, 0.08, 0.1, 0.15])
            parts = [p for p in parts if p != por_text]
            [exp.pop(k, None) for k in ("porosity", "porosity_min", "porosity_max")]
            parts.append(r.choice(["relative stiffness of {e}", "{p}% of the solid stiffness"]).format(e=_num(e), p=_num(e * 100)))
            exp["youngs_relative"] = e
        if kind == "permeability":
            k = r.choice([1e-9, 2e-9, 5e-9])
            parts.append(f"permeability of {k:.0e} m2".replace("e-0", "e-"))
            exp["permeability_m2"] = k
        out.append(Case(f"t4_{i:03d}", 4, _join(parts, r), exp, allowed, [], feasible, tags=[kind]))
    return out


def tier5(r: random.Random, n: int) -> list[Case]:
    out = []
    kinds = ["fdm_tiny_pores", "cell_bigger_than_part", "vial_too_small", "thick_walls_small_pores", "extreme_porosity", "sla_micro_pores"]
    for i in range(n):
        kind = kinds[i % len(kinds)]
        group, fam_text, fam = _family(r, ["tpms"])
        if kind == "fdm_tiny_pores":
            dom_text, dom = _domain(r)
            p = r.choice([0.1, 0.15, 0.2])
            text = _join([f"{fam_text} scaffold, {dom_text}", "85% porosity", f"pore size {_num(p)} mm", f"printed on an {r.choice(['FDM printer', 'filament printer'])}"], r)
            exp = {**fam, **dom, "porosity": 0.85, "pore_mm": p, "process": "fdm"}
        elif kind == "cell_bigger_than_part":
            a = float(r.randint(3, 6))
            c = float(r.randint(int(a) + 2, 12))
            text = _join([f"{fam_text} scaffold, {_num(a)} mm cube", "70% porosity", f"{_num(c)} mm unit cell"], r)
            exp = {**fam, "domain_shape": "box", "domain_dimensions_mm": [a, a, a], "porosity": 0.7, "cell_mm": c}
        elif kind == "vial_too_small":
            a = float(r.randint(25, 40))
            text = _join([f"{fam_text} scaffold, {_num(a)} x {_num(a)} x {_num(a)} mm", "70% porosity", "printed on our volumetric printer"], r)
            exp = {**fam, "domain_shape": "box", "domain_dimensions_mm": [a, a, a], "porosity": 0.7, "process": "volumetric"}
        elif kind == "thick_walls_small_pores":
            dom_text, dom = _domain(r)
            text = _join([f"{fam_text} scaffold, {dom_text}", "85% porosity", "0.3 mm pores", "walls of at least 1 mm"], r)
            exp = {**fam, **dom, "porosity": 0.85, "pore_mm": 0.3, "min_wall_mm": 1.0}
        elif kind == "extreme_porosity":
            dom_text, dom = _domain(r)
            p = r.choice([0.97, 0.98, 0.99])
            text = _join([f"{fam_text} scaffold, {dom_text}", f"{int(p * 100)}% porosity", "printed on a resin printer"], r)
            exp = {**fam, **dom, "porosity": p, "process": "sla"}
        else:
            dom_text, dom = _domain(r)
            p = r.choice([0.05, 0.08])
            text = _join([f"{fam_text} scaffold, {dom_text}", "75% porosity", f"pore size {_num(p)} mm", "printed on a resin printer"], r)
            exp = {**fam, **dom, "porosity": 0.75, "pore_mm": p, "process": "sla"}
        out.append(Case(f"t5_{i:03d}", 5, text, exp, [], ["min_throat_mm"], False, tags=[kind]))
    return out


OUT_OF_SCOPE = [
    ("scan", "Design a scaffold that matches the CT scan of my patient's mandible defect."),
    ("scan", "Use the MRI segmentation of the cartilage lesion to shape a porous implant."),
    ("inverse", "Optimise the lattice topology for minimum weight under a 500 N compressive load, {dom}."),
    ("inverse", "Find the architecture that maximises permeability for a given stiffness, {dom}."),
    ("multimaterial", "Make a {dom} scaffold from two materials: a soft shell and a stiff core."),
    ("degradation", "A {dom} gyroid scaffold that fully degrades within 8 weeks in vivo."),
    ("conductive", "A conductive porous electrode, {dom}, with 70% porosity."),
    ("drug", "Porous {dom} implant that releases antibiotic over two weeks."),
]


def tier6(r: random.Random, n: int) -> list[Case]:
    out = []
    for i in range(n):
        topic, tmpl = OUT_OF_SCOPE[i % len(OUT_OF_SCOPE)]
        dom_text, dom = _domain(r)
        text = tmpl.format(dom=dom_text)
        exp = {**dom} if "{dom}" in tmpl else {}
        if "gyroid" in tmpl:
            exp["family"] = "gyroid"
        if "70% porosity" in tmpl:
            exp["porosity"] = 0.7
        out.append(Case(f"t6_{i:03d}", 6, text, exp, [], ["pore_mm", "cell_mm", "min_wall_mm", "youngs_relative", "permeability_m2"], None, out_of_scope=True, tags=[topic]))
    return out


def _t7_domain(r: random.Random) -> tuple[str, dict]:
    kind = r.choice(["cube", "box", "puck", "ball"])
    if kind == "cube":
        a = float(r.randint(6, 16))
        return r.choice([f"about {_num(a)} mm on each side", f"a {_num(a)}-millimetre cube", f"{_num(a)} mm along every edge"]), {"domain_shape": "box", "domain_dimensions_mm": [a, a, a]}
    if kind == "box":
        d = [float(r.randint(6, 20)) for _ in range(3)]
        return f"{_num(d[0])} mm long, {_num(d[1])} mm wide and {_num(d[2])} mm high", {"domain_shape": "box", "domain_dimensions_mm": d}
    if kind == "puck":
        dia, h = float(r.randint(8, 20)), float(r.randint(2, 8))
        return r.choice([f"a puck {_num(dia)} mm across and {_num(h)} mm thick", f"a round disc, {_num(dia)} mm wide, {_num(h)} mm deep"]), {"domain_shape": "cylinder", "domain_dimensions_mm": [dia, h]}
    dia = float(r.randint(8, 16))
    return f"a ball {_num(dia)} mm across", {"domain_shape": "sphere", "domain_dimensions_mm": [dia]}


def _t7_porosity(r: random.Random) -> tuple[str, dict]:
    p = round(r.uniform(0.55, 0.8) * 20) / 20
    kind = r.choice(["empty", "void", "solid", "percent", "half"])
    if kind == "half":
        return "half solid, half empty", {"porosity": 0.5}
    return {
        "empty": f"about {int(p * 100)}% empty space",
        "void": f"a void fraction of {p:.2f}",
        "solid": f"only {int(round((1 - p) * 100))}% solid material",
        "percent": f"{int(p * 100)} percent open volume",
    }[kind], {"porosity": p}


def _t7_length(r: random.Random) -> tuple[str, dict]:
    c = r.choice([2.0, 2.5, 3.0])
    return r.choice([f"repeating every {_num(c)} mm", f"with {_num(c)}-millimetre cells", f"a pattern period of {_num(c)} mm"]), {"cell_mm": c}


T7_TEMPLATES = [
    "Could you make me a {family} thing, {dom}, with {por}, {len}?",
    "{dom_cap}. {family_cap} inside, {por}, {len}.",
    "I'm after {family} infill for a part that is {dom}; aim for {por}, {len}.",
    "Print-ready {family}: {dom}, {por}, {len}.",
    "We want {por} in a {family} structure, {dom}, {len}.",
]


def tier7(r: random.Random, n: int) -> list[Case]:
    out = []
    for i in range(n):
        group, fam_text, fam = _family(r, ["tpms", "tpms", "strut", "foam"])
        dom_text, dom = _t7_domain(r)
        por_text, por = _t7_porosity(r)
        len_text, length = _t7_length(r)
        tmpl = T7_TEMPLATES[i % len(T7_TEMPLATES)]
        text = tmpl.format(family=fam_text, family_cap=fam_text[0].upper() + fam_text[1:], dom=dom_text, dom_cap=dom_text[0].upper() + dom_text[1:], por=por_text, len=len_text)
        out.append(Case(f"t7_{i:03d}", 7, text, {**fam, **dom, **por, **length}, [], ["min_wall_mm", "min_throat_mm", "pore_mm"], None, tags=["held_out"]))
    return out


TIER_SIZES = {1: 150, 2: 80, 3: 60, 4: 60, 5: 48, 6: 32, 7: 40}


def build_prompts(seed: int = 2026, sizes: dict[int, int] | None = None) -> list[Case]:
    sizes = sizes or TIER_SIZES
    r = random.Random(seed)
    makers = {1: tier1, 2: tier2, 3: tier3, 4: tier4, 5: tier5, 6: tier6, 7: tier7}
    cases: list[Case] = []
    for tier in sorted(sizes):
        cases += makers[tier](r, sizes[tier])
    return cases


def write_prompts(path: Path = DATA_FILE, seed: int = 2026) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for case in build_prompts(seed):
            fh.write(json.dumps(case.to_dict()) + "\n")
    return path


def load_prompts(path: Path = DATA_FILE) -> list[Case]:
    if not path.exists():
        write_prompts(path)
    return [Case(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
