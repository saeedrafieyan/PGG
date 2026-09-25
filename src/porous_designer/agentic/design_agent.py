"""Design agent (Phase 4.3): plan -> design -> verify -> repair, with two human checkpoints.

Roles
-----
Planner   turns the request into a typed ``DesignIntent``. Values come only
          from the request (deterministic parser, optionally the grounded
          OpenRouter extraction), from the cited knowledge base, or from
          declared defaults - each with its source.
Designer  chooses what the request leaves open (family, porosity, cell size,
          resolution) from the measured property tables, checks feasibility
          against the printer before anything is generated, and explains
          conflicts with numbers and the nearest feasible alternatives.
Verifier  runs the deterministic kernel and the Phase 4.2 measurements; the
          validation checks are the only judge of numbers (no LLM).
Repairer  applies bounded, logged rules to failed checks. It only changes
          values the designer chose; a fix that would change a user-stated
          value is returned to the user instead.

Checkpoints: *approve intent/design* before generation and *approve final*
after verification. Every step is recorded in ``agent_trace.json``.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from porous_designer.agentic.contracts import ParsedRequestResult
from porous_designer.agentic.request_parser_agent import RequestParserAgent
from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily, TPMSVariant
from porous_designer.domain.specification import (
    ConstraintsSpec,
    DesignSpecification,
    DomainSpec,
    ExportSpec,
    GenerationSpec,
    ManufacturingSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
)
from porous_designer.knowledge.applications import ApplicationMatch, cite, match_application
from porous_designer.knowledge.feasibility import (
    Requirements,
    cell_for_targets,
    evaluate,
    nearest_alternatives,
    porosity_for_stiffness,
    smallest_printable_pore,
)
from porous_designer.knowledge.property_tables import porosity_range, properties_at, table_key
from porous_designer.printability.profiles import PrinterProfile, all_profiles, profile_for

AGENT_VERSION = "4.3.0"
LAYERED = {"fdm", "sla", "dlp", "bioprinting", "lpbf", "sls"}

# Designer preference when the request names no family (most self-supporting first).
FAMILY_PREFERENCE: list[tuple[StructureFamily, TPMSVariant]] = [
    (StructureFamily.GYROID, TPMSVariant.SHEET),
    (StructureFamily.DIAMOND, TPMSVariant.SHEET),
    (StructureFamily.PRIMITIVE, TPMSVariant.SHEET),
    (StructureFamily.IWP, TPMSVariant.SHEET),
    (StructureFamily.NEOVIUS, TPMSVariant.SHEET),
    (StructureFamily.GYROID, TPMSVariant.NETWORK),
    (StructureFamily.DIAMOND, TPMSVariant.NETWORK),
    (StructureFamily.STRUT_KELVIN, TPMSVariant.SHEET),
    (StructureFamily.STRUT_OCTET, TPMSVariant.SHEET),
    (StructureFamily.STRUT_BCC, TPMSVariant.SHEET),
    (StructureFamily.STRUT_CUBIC, TPMSVariant.SHEET),
    (StructureFamily.VORONOI_FOAM, TPMSVariant.SHEET),
]
EXTRUSION_PREFERENCE = [(StructureFamily.STRUT_CUBIC, TPMSVariant.SHEET), (StructureFamily.STRUT_BCC, TPMSVariant.SHEET)]


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------


@dataclass
class Value:
    value: Any
    source: str  # user | knowledge_base | designer | default
    detail: str = ""
    citations: list[str] = field(default_factory=list)
    requires_confirmation: bool = False

    @property
    def free(self) -> bool:
        """The agent may change it (it was not stated by the user)."""
        return self.source != "user"


@dataclass
class DesignIntent:
    request: str
    values: dict[str, Value] = field(default_factory=dict)
    application: str | None = None
    unsupported: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    parser: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default=None):
        v = self.values.get(key)
        return v.value if v is not None else default

    def set(self, key: str, value: Any, source: str, detail: str = "", *, citations=None, confirm: bool = False) -> None:
        self.values[key] = Value(value, source, detail, list(citations or []), confirm)

    def is_free(self, key: str) -> bool:
        v = self.values.get(key)
        return v is None or v.free

    @classmethod
    def from_dict(cls, d: dict) -> "DesignIntent":
        intent = cls(request=d["request"], application=d.get("application"), unsupported=list(d.get("unsupported", [])), ambiguities=list(d.get("ambiguities", [])), parser=dict(d.get("parser", {})))
        intent.values = {k: Value(**v) for k, v in d.get("values", {}).items()}
        return intent

    def to_dict(self) -> dict:
        return {
            "request": self.request,
            "application": self.application,
            "values": {k: asdict(v) for k, v in self.values.items()},
            "unsupported": self.unsupported,
            "ambiguities": self.ambiguities,
            "parser": self.parser,
        }


# ---------------------------------------------------------------------------
# Result / trace
# ---------------------------------------------------------------------------


@dataclass
class TraceStep:
    role: str
    action: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    time: str = field(default_factory=lambda: _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"))


@dataclass
class DesignAgentResult:
    status: str  # proposed | delivered | delivered_with_warnings | infeasible | needs_user | failed | rejected
    intent: DesignIntent
    specification: DesignSpecification | None = None
    explanation: str = ""
    alternatives: list[dict] = field(default_factory=list)
    iterations: list[dict] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)
    generation: Any = None  # final GenerationResult
    design_info: dict[str, Any] = field(default_factory=dict)
    trace_path: Path | None = None
    agent_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def snapshot(self) -> dict:
        """Picklable state of a proposal, to continue in another process (GUI worker)."""
        return {
            "status": self.status,
            "agent_id": self.agent_id,
            "intent": self.intent.to_dict(),
            "specification": self.specification.model_dump(mode="json") if self.specification else None,
            "design_info": json.loads(json.dumps(self.design_info, default=str)),
            "alternatives": self.alternatives,
            "trace": [asdict(t) for t in self.trace],
        }

    @classmethod
    def from_snapshot(cls, d: dict) -> "DesignAgentResult":
        return cls(
            status=d["status"],
            intent=DesignIntent.from_dict(d["intent"]),
            specification=DesignSpecification.model_validate(d["specification"]) if d.get("specification") else None,
            design_info=d.get("design_info", {}),
            alternatives=d.get("alternatives", []),
            trace=[TraceStep(**t) for t in d.get("trace", [])],
            agent_id=d.get("agent_id") or uuid.uuid4().hex[:12],
        )

    def to_dict(self) -> dict:
        gen = self.generation
        return {
            "agent_version": AGENT_VERSION,
            "agent_id": self.agent_id,
            "status": self.status,
            "explanation": self.explanation,
            "intent": self.intent.to_dict(),
            "specification": self.specification.model_dump(mode="json") if self.specification else None,
            "alternatives": self.alternatives,
            "design_point": self.design_info.get("design_point"),
            "printer": self.design_info.get("printer"),
            "iterations": self.iterations,
            "final_run": None if gen is None else {"run_dir": str(gen.run_dir), "success": gen.success, "stl": str(gen.stl_path) if gen.stl_path else None, "measurements": gen.measurements},
            "trace": [asdict(s) for s in self.trace],
        }


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------


class DesignAgent:
    def __init__(
        self,
        *,
        provider=None,
        settings=None,
        output_dir: str | Path | None = None,
        max_iterations: int = 3,
        approve_intent: Callable[[DesignIntent, DesignSpecification, dict], bool] | None = None,
        approve_final: Callable[[DesignAgentResult], bool] | None = None,
        auto_approve: bool = False,
        printer_profile: str | None = None,
        process: str | None = None,
        generate: Callable | None = None,
        on_event: Callable[[str, str], None] | None = None,
        use_knowledge: bool = True,
        use_feasibility: bool = True,
        voxel_budget: int = 60_000_000,
    ) -> None:
        from porous_designer.paths import runs_dir

        self.parser = RequestParserAgent(provider, settings=settings)
        self.output_dir = Path(output_dir) if output_dir else runs_dir() / "agent"
        self.max_iterations = max_iterations
        self.approve_intent = approve_intent
        self.approve_final = approve_final
        self.auto_approve = auto_approve
        self.printer_override = printer_profile
        self.process_override = process
        if generate is None:
            from porous_designer.services.generation_service import generate_porous_stl

            generate = generate_porous_stl
        self._generate = generate
        self.on_event = on_event
        # Ablation switches (AGE-Bench): literature presets, table-based designer.
        self.use_knowledge = use_knowledge
        self.use_feasibility = use_feasibility
        self.voxel_budget = voxel_budget
        self._kb_porosity_range = None
        self._kb_pore_range = None

    # -- planner ------------------------------------------------------------------
    def plan(self, request: str, trace: list[TraceStep]) -> DesignIntent:
        self._kb_porosity_range = None
        self._kb_pore_range = None
        parsed: ParsedRequestResult = self.parser.parse(request)
        intent = DesignIntent(request=request)
        intent.parser = {"mode": parsed.provider_mode, "version": parsed.parser_version, "provider_failed": parsed.provider_failed}
        mapping = {
            "domain.shape": "domain_shape",
            "domain.dimensions_mm": "domain_dimensions_mm",
            "structure.family": "family",
            "structure.tpms_variant": "tpms_variant",
            "structure.unit_cell_size_mm": "cell_mm",
            "structure.pore_diameter_mm": "pore_mm",
            "targets.porosity_target.target": "porosity",
            "targets.porosity_target.min_value": "porosity_min",
            "targets.porosity_target.max_value": "porosity_max",
            "constraints.minimum_wall_thickness_mm": "min_wall_mm",
            "constraints.minimum_throat_size_mm": "min_throat_mm",
            "constraints.require_open_pores": "open_pores",
            "generation.final_resolution_mm": "resolution_mm",
            "export.formats": "formats",
            "manufacturing.process": "process",
        }
        for f in parsed.extracted_fields:
            key = mapping.get(f.field_path)
            if key is None or f.status == "unsupported":
                continue
            intent.set(key, f.value, "user", f"from the request: \"{f.source_text}\"", confirm=f.requires_confirmation)
        intent.unsupported = [f"{u.feature}: {u.source_text}" for u in parsed.unsupported_requests]
        intent.ambiguities = [f"{a.source_phrase}: {a.explanation}" for a in parsed.ambiguities]
        self._extract_extra(request, intent)
        self._detect_out_of_scope(request, intent)
        if self.process_override:
            intent.set("process", self.process_override, "user", "selected in the tool")
        if self.printer_override:
            intent.set("printer_profile", self.printer_override, "user", "selected in the tool")

        app = match_application(request) if self.use_knowledge else None
        if app is not None:
            intent.application = app.key
            self._apply_application(intent, app)
        trace.append(TraceStep("planner", "parse", f"{len(parsed.extracted_fields)} value(s) extracted ({parsed.provider_mode}); application: {intent.application or 'none'}", {"intent": intent.to_dict()}))
        return intent

    PROCESS_WORDS = [
        (r"xolograph", "volumetric", "generic_volumetric_xolography"),
        (r"volumetric|tomographic|\bcal\b|computed axial", "volumetric", None),
        (r"\bfdm\b|\bfff\b|filament|fused deposition", "fdm", None),
        (r"\bdlp\b", "dlp", None),
        (r"\bsla\b|\bmsla\b|resin|stereolithograph|vat photopolymer", "sla", None),
        (r"bioprint", "bioprinting", None),
        (r"\bsls\b|selective laser sintering", "sls", None),
        (r"\blpbf\b|\bslm\b|laser powder bed|metal print", "lpbf", None),
    ]

    OUT_OF_SCOPE = [
        (r"\b(?:ct|micro-?ct|mri|scan|scans|scanned|segmentation|dicom)\b", "scan-to-part", "geometry from a patient scan is not supported yet; give the part size, or a closed mesh of the part (domain.mesh_path)"),
        (r"\boptimi[sz]e|\boptimi[sz]ation|\bmaximi[sz]e|\bminimi[sz]e|inverse design|topology", "inverse design / optimisation", "AGE designs forward from stated targets; it does not search for an optimal architecture"),
        (r"two materials|multi-?material|shell and a [a-z ]*core|\bbi-?material", "multi-material", "a single material phase is generated"),
        (r"degrad|resorb|dissolv", "degradation", "material degradation is not modelled"),
        (r"conductiv|electrode|electrical", "electrical properties", "electrical properties are not modelled"),
        (r"\bdrug|antibiotic|\belut|\brelease", "drug release", "drug release is not modelled"),
    ]

    def _detect_out_of_scope(self, request: str, intent: DesignIntent) -> None:
        import re

        low = request.lower()
        for pattern, feature, why in self.OUT_OF_SCOPE:
            m = re.search(pattern, low)
            if m:
                intent.unsupported.append(f"{feature}: \"{request[m.start():m.end()]}\" - {why}")

    def _extract_extra(self, request: str, intent: DesignIntent) -> None:
        """Values the Phase 3 parser does not cover: process, permeability, relative stiffness.

        Every value is taken from a matched phrase of the request (quoted in
        the detail); nothing is inferred.
        """
        import re

        low = request.lower()
        if intent.get("process") is None:
            for pattern, process, profile in self.PROCESS_WORDS:
                m = re.search(pattern, low)
                if m:
                    phrase = f'from the request: "{request[m.start():m.end()]}"'
                    intent.set("process", process, "user", phrase)
                    if profile and intent.get("printer_profile") is None:
                        intent.set("printer_profile", profile, "user", phrase)
                    break
        num = r"(\d+(?:\.\d+)?(?:\s*[x×]\s*10\^?\s*-?\d+|e-?\d+)?)"
        m = re.search(r"permeability[^0-9]{0,30}" + num + r"\s*(m2|m\^2|m²|darcy|d\b|mm2|mm\^2|mm²)", low)
        if m:
            raw = m.group(1).replace(" ", "").replace("×", "x")
            if "x10" in raw:
                base, exp = raw.split("x10")
                value = float(base) * 10 ** float(exp.replace("^", ""))
            else:
                value = float(raw)
            unit = m.group(2)
            factor = {"darcy": 9.869233e-13, "d": 9.869233e-13}.get(unit, 1e-6 if unit.startswith("mm") else 1.0)
            intent.set("permeability_m2", value * factor, "user", f'from the request: "{request[m.start():m.end()]}"')
        m = re.search(r"(?:relative stiffness|relative modulus|e\*/es|e/es)[^0-9]{0,12}(\d+(?:\.\d+)?)\s*(%?)", low) or re.search(
            r"(\d+(?:\.\d+)?)\s*(%)\s*of (?:the )?(?:solid|bulk|dense) (?:material'?s? )?(?:stiffness|modulus)", low
        )
        if m:
            value = float(m.group(1)) / (100.0 if m.group(2) == "%" or float(m.group(1)) > 1 else 1.0)
            intent.set("youngs_relative", value, "user", f'from the request: "{request[m.start():m.end()]}"')

    def _apply_application(self, intent: DesignIntent, app: ApplicationMatch) -> None:
        p = app.preset
        if "porosity" in p and intent.is_free("porosity"):
            por = p["porosity"]
            intent.set("porosity", por["typical"], "knowledge_base", f"{app.label}: typical porosity; {por.get('note', '')}", citations=cite(por.get("source")))
            if por.get("range"):
                self._kb_porosity_range = tuple(por["range"])
        if "pore_size_mm" in p and intent.is_free("pore_mm") and intent.is_free("cell_mm"):
            ps = p["pore_size_mm"]
            intent.set("pore_mm", ps["typical"], "knowledge_base", f"{app.label}: typical pore size; {ps.get('note', '')}", citations=cite(ps.get("source")))
            if ps.get("range"):
                self._kb_pore_range = tuple(ps["range"])
        if "open_pores" in p and intent.is_free("open_pores"):
            intent.set("open_pores", bool(p["open_pores"]["value"]), "knowledge_base", p["open_pores"].get("note", ""), citations=cite(p["open_pores"].get("source")))
        for key in ("stiffness", "curvature"):
            if key in p:
                intent.values.setdefault(f"note_{key}", Value(p[key]["note"], "knowledge_base", "", cite(p[key].get("source"))))

    # -- designer -------------------------------------------------------------------
    def printer(self, intent: DesignIntent) -> PrinterProfile | None:
        return profile_for(intent.get("process"), intent.get("printer_profile") or "")

    def requirements(self, intent: DesignIntent, printer: PrinterProfile | None, domain_min_mm: float) -> Requirements:
        walls = [v for v in (intent.get("min_wall_mm"), printer.min_wall_mm if printer else None) if v]
        opens = [v for v in (intent.get("min_throat_mm"), printer.min_hole_mm if printer else None) if v]
        family = intent.get("family")
        sphere = family is not None and StructureFamily(family).is_sphere_lattice
        return Requirements(
            porosity=intent.get("porosity"),
            pore_mm=None if sphere else intent.get("pore_mm"),
            min_wall_mm=max(walls) if walls else None,
            min_opening_mm=max(opens) if opens else None,
            permeability_m2=intent.get("permeability_m2"),
            youngs_relative=intent.get("youngs_relative"),
            max_cell_mm=domain_min_mm / 2.0,
        )

    def _domain(self, intent: DesignIntent) -> DomainSpec:
        shape = intent.get("domain_shape")
        dims = intent.get("domain_dimensions_mm")
        if not shape or not dims:
            intent.set("domain_shape", "box", "default", "no part size stated: a 10 mm cube is assumed", confirm=True)
            intent.set("domain_dimensions_mm", [10.0, 10.0, 10.0], "default", "no part size stated", confirm=True)
            shape, dims = "box", [10.0, 10.0, 10.0]
        return DomainSpec(shape=DomainShape(shape), dimensions_mm=[float(v) for v in dims])

    def _candidates(self, intent: DesignIntent, printer: PrinterProfile | None) -> list[tuple[StructureFamily, TPMSVariant]]:
        if not intent.is_free("family"):
            fam = StructureFamily(intent.get("family"))
            var = TPMSVariant(intent.get("tpms_variant") or "sheet") if fam.is_tpms else TPMSVariant.SHEET
            return [(fam, var)]
        order = list(FAMILY_PREFERENCE)
        if printer is not None and printer.process == "bioprinting":
            order = EXTRUSION_PREFERENCE + [c for c in order if c not in EXTRUSION_PREFERENCE]
        if intent.application:
            from porous_designer.knowledge.applications import knowledge

            preferred = knowledge()["applications"][intent.application].get("preferred_families", [])
            order.sort(key=lambda c: preferred.index(c[0].value) if c[0].value in preferred else len(preferred))
        if intent.get("youngs_relative") and intent.get("porosity"):
            phi = intent.get("porosity")

            def stiffness(c):
                p = properties_at(c[0], c[1], phi)
                return -(p.values.get("youngs_relative", 0.0) if p else 0.0)

            order.sort(key=stiffness)
        return [c for c in order if porosity_range(*c) is not None] or order

    @staticmethod
    def _porosity_for_family(intent: DesignIntent, fam: StructureFamily, var: TPMSVariant) -> float | None:
        """The porosity to evaluate for this family.

        A stated single value is used as is. A stated range, a default, or a designer
        midpoint is moved to the nearest porosity the family can reach with open pores
        (e.g. open spherical pores need at least ~78 % porosity in FCC/HCP packings).
        """
        v = intent.values.get("porosity")
        if v is None:
            return None
        rng = porosity_range(fam, var)
        if rng is None or v.source == "user" and intent.get("porosity_min") is None:
            return v.value
        lo, hi = rng[0] + 0.01, rng[1] - 0.01
        if intent.get("porosity_min") is not None and intent.get("porosity_max") is not None:
            lo, hi = max(lo, intent.get("porosity_min")), min(hi, intent.get("porosity_max"))
            if lo > hi:
                return v.value  # the stated range is outside the family: report it as infeasible
        return float(min(max(v.value, lo), hi))

    def _rank(self, intent: DesignIntent, printer, req: Requirements, domain_min: float, *, closest_pore: float | None = None):
        """Evaluate candidate architectures in preference order; the first feasible one wins.

        With ``closest_pore`` every candidate is evaluated and the feasible one whose
        (smallest printable) median pore is nearest to it wins.
        """
        ranking, chosen, feasible = [], None, []
        for fam, var in self._candidates(intent, printer):
            phi = self._porosity_for_family(intent, fam, var)
            if phi is None and intent.get("youngs_relative"):
                phi = porosity_for_stiffness(fam, var, intent.get("youngs_relative"))
                if phi is None:
                    ranking.append({"family": table_key(fam, var), "feasible": False, "issues": ["target stiffness outside this family's range"]})
                    continue
            r = Requirements(**{**req.to_dict(), "porosity": phi})
            if fam.is_sphere_lattice:
                r.pore_mm = None
                cell = float(intent.get("pore_mm") or 1.0)
                why = "generating sphere (pore) diameter"
            elif not intent.is_free("cell_mm"):
                cell, why = float(intent.get("cell_mm")), "stated in the request"
            else:
                cell, why = cell_for_targets(fam, var, phi, r)
                if cell is None:
                    cell, why = min(2.0, domain_min / 3.0), "default 2 mm cell (at least three cells across the part)"
            point = evaluate(fam, var, phi, cell, r)
            ranking.append({"family": table_key(fam, var), "porosity": phi, "cell_mm": cell, "cell_reason": why, **point.to_dict()})
            if point.feasible:
                feasible.append((fam, var, phi, cell, why, point))
                if closest_pore is None:
                    break
        if feasible:
            chosen = feasible[0] if closest_pore is None else min(feasible, key=lambda c: abs(c[5].pore_mm - closest_pore))
        return chosen, ranking

    def design(self, intent: DesignIntent, trace: list[TraceStep]) -> tuple[DesignSpecification | None, dict]:
        printer = self.printer(intent)
        domain = self._domain(intent)
        domain_min = min(domain.dimensions_mm)
        if intent.get("porosity") is None:
            if intent.get("porosity_min") is not None and intent.get("porosity_max") is not None:
                intent.set("porosity", (intent.get("porosity_min") + intent.get("porosity_max")) / 2, "designer", "midpoint of the requested range", confirm=True)
            elif not intent.get("youngs_relative"):
                intent.set("porosity", 0.7, "default", "no porosity stated: 70 % assumed", confirm=True)
        req = self.requirements(intent, printer, domain_min)
        if not self.use_feasibility:
            return self._naive_design(intent, domain, printer, req, trace)
        fit = self._fits_printer(domain, printer)
        if fit:
            info = {"printer": printer.id, "requirements": req.to_dict(), "ranking": [], "alternatives": [], "explanation": fit}
            info["alternatives"] = [
                {"description": f"print on {p.display_name or p.id}", "change": {"printer_profile": p.id}, "point": {}}
                for p in self._alternative_printers(intent, printer)
                if not self._fits_printer(domain, p)
            ][:4]
            if info["alternatives"]:
                info["explanation"] += "\nNearest feasible options:\n" + "\n".join(f"- {a['description']}" for a in info["alternatives"])
            trace.append(TraceStep("designer", "feasibility", "part does not fit the printer", info))
            return None, info
        chosen, ranking = self._rank(intent, printer, req, domain_min)
        info: dict[str, Any] = {"printer": printer.id if printer else None, "requirements": req.to_dict(), "ranking": ranking}
        pore = intent.values.get("pore_mm")
        if chosen is None and pore is not None and pore.source == "knowledge_base":
            # A literature pore size is guidance, not a user value: fall back to the
            # smallest pores the printer can make, and say so.
            relaxed = Requirements(**{**req.to_dict(), "pore_mm": None})
            chosen, ranking2 = self._rank(intent, printer, relaxed, domain_min, closest_pore=pore.value)
            if chosen is not None:
                literature, achieved = pore.value, chosen[5].pore_mm
                where = printer.display_name if printer else "the printer"
                rng = self._kb_pore_range
                within = rng is not None and rng[0] <= achieved <= rng[1]
                intent.set(
                    "pore_mm",
                    round(achieved, 4),
                    "designer",
                    f"the typical literature pore size {literature:g} mm cannot be printed on {where}; "
                    + (f"{achieved:.2f} mm is the closest printable size and is inside the cited range {rng[0]:g}-{rng[1]:g} mm" if within else f"{achieved:.2f} mm is the closest printable size" + (f" (cited range {rng[0]:g}-{rng[1]:g} mm)" if rng else "")),
                    citations=pore.citations,
                    confirm=True,
                )
                info["relaxed"] = {"pore_mm": {"literature": literature, "used": achieved}}
                info["ranking"] = ranking + ranking2
                req = relaxed
        por = intent.values.get("porosity")
        kb_range = getattr(self, "_kb_porosity_range", None)
        if chosen is None and por is not None and por.source == "knowledge_base" and kb_range and kb_range[0] < por.value:
            # Still infeasible: the lower end of the literature porosity range gives thicker walls.
            relaxed = Requirements(**{**req.to_dict(), "pore_mm": None if pore is not None and pore.source != "user" else req.pore_mm, "porosity": kb_range[0]})
            old = por.value
            intent.set("porosity", kb_range[0], "designer", f"the typical literature porosity {old:.0%} is not printable here; the lower end of the cited range is used", citations=por.citations, confirm=True)
            chosen, ranking3 = self._rank(intent, printer, relaxed, domain_min, closest_pore=pore.value if pore is not None and pore.source == "knowledge_base" else None)
            if chosen is not None:
                if pore is not None and pore.source == "knowledge_base":
                    intent.set("pore_mm", round(chosen[5].pore_mm, 4), "designer", f"the literature pore size {pore.value:g} mm is not printable here; the smallest printable pore is used instead", citations=pore.citations, confirm=True)
                info.setdefault("relaxed", {})["porosity"] = {"literature": old, "used": kb_range[0]}
                info["ranking"] = info["ranking"] + ranking3
                req = relaxed
            else:
                intent.set("porosity", old, "knowledge_base", por.detail, citations=por.citations)
        if chosen is None:
            fam, var = self._candidates(intent, printer)[0]
            phi = intent.get("porosity") or 0.7
            alternatives = nearest_alternatives(
                fam,
                var,
                Requirements(**{**req.to_dict(), "porosity": phi}),
                candidates=[c for c in FAMILY_PREFERENCE if c != (fam, var)],
                printers=self._alternative_printers(intent, printer),
            )
            info["alternatives"] = [a.to_dict() for a in alternatives[:6]]
            info["explanation"] = self._infeasibility_text(fam, var, phi, req, ranking[0] if ranking else {}, printer, alternatives)
            trace.append(TraceStep("designer", "feasibility", "no candidate meets the targets", info))
            return None, info
        fam, var, phi, cell, why, point = chosen
        if intent.is_free("family"):
            reason = "self-supporting on layer-based printers" if printer and printer.process in LAYERED else "default ranking"
            intent.set("family", fam.value, "designer", f"first feasible architecture in the preference order ({reason})")
            if fam.is_tpms:
                intent.set("tpms_variant", var.value, "designer", "sheet TPMS by default")
        if intent.get("porosity") is None:
            intent.set("porosity", round(phi, 4), "designer", "porosity giving the target stiffness (property table)")
        elif phi is not None and abs(phi - intent.get("porosity")) > 1e-6:
            old = intent.values["porosity"]
            within = intent.get("porosity_min") is not None
            intent.set(
                "porosity",
                round(phi, 4),
                "designer",
                (f"chosen inside your range {intent.get('porosity_min'):.0%}-{intent.get('porosity_max'):.0%}" if within else f"{old.value:.0%} ({old.source}) is outside what {table_key(fam, var)} reaches with open pores")
                + f"; {phi:.0%} is the nearest achievable",
                citations=old.citations,
                confirm=True,
            )
        if intent.is_free("cell_mm") and not fam.is_sphere_lattice:
            intent.set("cell_mm", round(cell, 4), "designer", why)
        if intent.is_free("resolution_mm"):
            features = [v for v in (point.wall_mm, point.throat_mm) if v]
            h = min(features) / 4.0 if features else 0.1
            h = self._fit_resources(domain, float(min(0.2, max(0.02, h))))
            intent.set("resolution_mm", round(h, 4), "designer", "thinnest wall/opening spans at least 4 voxels (within the memory budget)")
        spec = self._build_spec(intent, domain, fam, var, point, printer)
        info["design_point"] = point.to_dict()
        trace.append(
            TraceStep(
                "designer",
                "design",
                f"{table_key(fam, var)}, porosity {phi:.0%}, cell {cell:.3f} mm, resolution {spec.generation.final_resolution_mm} mm; "
                f"predicted wall {point.wall_mm:.3f} mm, pore {point.pore_mm:.3f} mm, opening {point.throat_mm:.3f} mm",
                info,
            )
        )
        return spec, info

    @staticmethod
    def _alternative_printers(intent: DesignIntent, printer: PrinterProfile | None) -> list[PrinterProfile]:
        """Other profiles to suggest, restricted to the application's usual processes when the knowledge base lists them."""
        profiles = [p for p in all_profiles().values() if printer is None or p.id != printer.id]
        if intent.application:
            from porous_designer.knowledge.applications import knowledge

            preferred = knowledge()["applications"][intent.application].get("preferred_processes")
            if preferred:
                profiles = [p for p in profiles if p.process in preferred] or profiles
        return profiles

    @staticmethod
    def _fits_printer(domain: DomainSpec, printer: PrinterProfile | None) -> str:
        """Empty string if the part fits the vial / build volume, else the reason."""
        if printer is None:
            return ""
        from porous_designer.implicit.domain_sdf import domain_extents

        ext = domain_extents(domain)
        who = printer.display_name or printer.id
        if printer.vial_diameter_mm:
            radial = max(ext[0], ext[1]) if domain.shape in (DomainShape.CYLINDER, DomainShape.SPHERE) else math.hypot(ext[0], ext[1])
            if radial > printer.vial_diameter_mm or (printer.vial_height_mm and ext[2] > printer.vial_height_mm):
                return f"The part ({' x '.join(f'{e:g}' for e in ext)} mm, footprint {radial:.1f} mm) does not fit the {printer.vial_diameter_mm:g} mm x {printer.vial_height_mm or 0:g} mm vial of {who}."
        elif printer.build_volume_mm:
            bx, by, bz = printer.build_volume_mm
            if not (ext[2] <= bz and ((ext[0] <= bx and ext[1] <= by) or (ext[0] <= by and ext[1] <= bx))):
                return f"The part ({' x '.join(f'{e:g}' for e in ext)} mm) exceeds the {bx:g} x {by:g} x {bz:g} mm build volume of {who}."
        return ""

    def _naive_design(self, intent, domain, printer, req, trace):
        """Ablation: no property tables and no feasibility check; fixed defaults for what is unstated."""
        fam = StructureFamily(intent.get("family") or "gyroid")
        var = TPMSVariant(intent.get("tpms_variant") or "sheet") if fam.is_tpms else TPMSVariant.SHEET
        if intent.get("porosity") is None:
            intent.set("porosity", 0.7, "default", "ablation default")
        if intent.get("family") is None:
            intent.set("family", fam.value, "default", "ablation default")
        if not fam.is_sphere_lattice and intent.get("cell_mm") is None:
            intent.set("cell_mm", 2.0, "default", "ablation default")
        if intent.get("resolution_mm") is None:
            length = float(intent.get("pore_mm") or 1.0) if fam.is_sphere_lattice else float(intent.get("cell_mm"))
            intent.set("resolution_mm", round(self._fit_resources(domain, min(0.2, max(0.02, length / 25.0))), 4), "default", "ablation default (length / 25)")
        point = evaluate(fam, var, intent.get("porosity"), float(intent.get("pore_mm") or 1.0) if fam.is_sphere_lattice else float(intent.get("cell_mm")), req)
        spec = self._build_spec(intent, domain, fam, var, point, printer)
        info = {"printer": printer.id if printer else None, "requirements": req.to_dict(), "ranking": [], "design_point": point.to_dict(), "ablation": "no_feasibility"}
        trace.append(TraceStep("designer", "design", f"ablation: {table_key(fam, var)} with defaults, no feasibility check", info))
        return spec, info

    def _fit_resources(self, domain: DomainSpec, h: float) -> float:
        from porous_designer.implicit.domain_sdf import domain_extents

        ext = domain_extents(domain)
        budget = self.voxel_budget  # grid points: 60 M keeps a Final run within ~16 GB
        while math.prod(e / h + 2 for e in ext) > budget and h < 0.2:
            h *= 1.15
        return h

    def _build_spec(self, intent: DesignIntent, domain: DomainSpec, fam, var, point, printer) -> DesignSpecification:
        structure = {"family": fam}
        if fam.is_sphere_lattice:
            structure["pore_diameter_mm"] = float(intent.get("pore_mm") or 1.0)
        else:
            structure["unit_cell_size_mm"] = float(intent.get("cell_mm"))
            if fam.is_tpms:
                structure["tpms_variant"] = var
        targets = {"porosity_target": PorosityTarget(target=float(intent.get("porosity")), tolerance=0.02)}
        if intent.get("pore_mm") and not fam.is_sphere_lattice:
            targets["pore_size_target_mm"] = float(intent.get("pore_mm"))
        constraints = ConstraintsSpec(
            require_open_pores=bool(intent.get("open_pores", True)),
            minimum_wall_thickness_mm=intent.get("min_wall_mm"),
            minimum_throat_size_mm=intent.get("min_throat_mm"),
        )
        level = "full" if intent.get("permeability_m2") or intent.get("youngs_relative") else "basic"
        h = float(intent.get("resolution_mm"))
        formats = intent.get("formats") or ["stl", "3mf"]
        return DesignSpecification(
            source_text=intent.request,
            domain=domain,
            structure=StructureSpec(**structure),
            targets=TargetsSpec(**targets),
            constraints=constraints,
            manufacturing=ManufacturingSpec(process=(printer.process if printer else (intent.get("process") or "unknown")), printer_profile=printer.id if printer else ""),
            generation=GenerationSpec(preview_resolution_mm=max(h * 2.0, 0.08), final_resolution_mm=h, reference_resolution_mm=h, metrology=level),
            export=ExportSpec(output_directory=str(self.output_dir), output_name="age_design", formats=[ExportFormat(f) for f in formats]),
        )

    def _infeasibility_text(self, fam, var, phi, req, first_row, printer, alternatives) -> str:
        who = printer.display_name if printer else "the stated limits"
        lines = [f"The request cannot be met as stated with {table_key(fam, var)} at {phi:.0%} porosity on {who}."]
        for issue in first_row.get("issues", []):
            lines.append(f"- {issue}")
        if req.pore_mm and req.min_wall_mm:
            d = smallest_printable_pore(fam, var, phi, req.min_wall_mm)
            if d:
                lines.append(f"At {phi:.0%} porosity a {table_key(fam, var)} wall of {req.min_wall_mm:.3f} mm needs pores of at least {d:.3f} mm (pore-to-wall ratio of this architecture).")
        if alternatives:
            lines.append("Nearest feasible options:")
            for a in alternatives[:4]:
                p = a.point
                lines.append(f"- {a.description}: walls {p.wall_mm:.3f} mm, pores {p.pore_mm:.3f} mm, openings {p.throat_mm:.3f} mm.")
        else:
            lines.append("No single change among porosity, pore size, architecture or printer makes it feasible.")
        return "\n".join(lines)

    # -- verifier -----------------------------------------------------------------------
    def verify(self, spec: DesignSpecification, intent: DesignIntent) -> tuple[Any, dict]:
        result = self._generate(spec)
        checks = []
        report = Path(result.run_dir) / "validation_report.json"
        if report.exists():
            checks = json.loads(report.read_text(encoding="utf-8"))["checks"]
        m = result.measurements or {}
        extra = []
        if intent.get("permeability_m2") and m.get("permeability_m2"):
            ratio = m["permeability_m2"] / intent.get("permeability_m2")
            extra.append({"name": "agent_permeability_target", "status": "pass" if 0.7 <= ratio <= 1.4 else "fail", "achieved_value": m["permeability_m2"], "requested_value": intent.get("permeability_m2"), "message": f"measured / target = {ratio:.2f}"})
        if intent.get("youngs_relative") and m.get("youngs_relative"):
            ratio = m["youngs_relative"] / intent.get("youngs_relative")
            extra.append({"name": "agent_stiffness_target", "status": "pass" if 0.8 <= ratio <= 1.25 else "fail", "achieved_value": m["youngs_relative"], "requested_value": intent.get("youngs_relative"), "message": f"measured / target = {ratio:.2f}"})
        checks = checks + extra
        failed = [c for c in checks if c["status"] == "fail"]
        warnings = [c for c in checks if c["status"] == "warning"]
        summary = {
            "run_dir": str(result.run_dir),
            "success": bool(result.success) and not any(c["status"] == "fail" for c in extra),
            "failed": [c["name"] for c in failed],
            "warnings": [c["name"] for c in warnings],
            "measurements": m,
            "messages": list(result.messages),
            "reachable": bool(result.tuning.reachable) if result.tuning is not None else None,
            "checks": {c["name"]: {"status": c["status"], "achieved": c.get("achieved_value"), "requested": c.get("requested_value")} for c in checks},
        }
        return result, summary

    # -- repairer -------------------------------------------------------------------------
    REPAIRABLE_WARNINGS = {"print_min_wall", "print_min_opening", "print_drainage", "print_islands", "pore_size_median"}

    def repair(self, intent: DesignIntent, spec: DesignSpecification, verification: dict) -> tuple[DesignSpecification | None, list[dict], list[str]]:
        """Adjusted specification, the repairs made, and conflicts needing the user."""
        issues = set(verification["failed"]) | (set(verification["warnings"]) & self.REPAIRABLE_WARNINGS)
        checks = verification["checks"]
        repairs: list[dict] = []
        conflicts: list[str] = []
        data = spec.model_dump(mode="json")
        s = data["structure"]
        fam = StructureFamily(s["family"])
        length_key = "pore_diameter_mm" if fam.is_sphere_lattice else "unit_cell_size_mm"
        length_intent = "pore_mm" if fam.is_sphere_lattice else "cell_mm"

        def scale_length(factor: float, why: str) -> bool:
            if not intent.is_free(length_intent):
                conflicts.append(f"{why}; the fix is a larger {'pore' if fam.is_sphere_lattice else 'cell'} size, which the request fixed at {s[length_key]} mm")
                return False
            old = s[length_key]
            s[length_key] = round(old * factor, 4)
            intent.set(length_intent, s[length_key], "designer", f"repaired: {why}")
            repairs.append({"rule": "scale_length", "reason": why, "from": old, "to": s[length_key]})
            return True

        def ratio(name, want):
            got = checks.get(name, {}).get("achieved")
            try:
                return max(1.1, 1.05 * float(want) / float(got)) if got else 1.3
            except (TypeError, ValueError, ZeroDivisionError):
                return 1.3

        wall_names = {"minimum_wall_thickness", "print_min_wall"} & issues
        if wall_names:
            name = sorted(wall_names)[0]
            want = self._required(checks.get(name, {}).get("requested"))
            if not scale_length(ratio(name, want), f"walls {checks[name]['achieved']} mm below {want} mm"):
                if intent.is_free("porosity"):
                    old = data["targets"]["porosity_target"]["target"]
                    data["targets"]["porosity_target"]["target"] = round(max(0.3, old - 0.05), 3)
                    intent.set("porosity", data["targets"]["porosity_target"]["target"], "designer", "repaired: lower porosity for thicker walls")
                    repairs.append({"rule": "lower_porosity", "reason": "walls too thin", "from": old, "to": data["targets"]["porosity_target"]["target"]})
                    conflicts.pop()
        open_names = {"minimum_throat_size", "print_min_opening", "print_drainage"} & issues
        if open_names and not wall_names:
            name = sorted(open_names)[0]
            want = self._required(checks.get(name, {}).get("requested"))
            scale_length(ratio(name, want) if name != "print_drainage" else 1.3, f"openings {checks[name]['achieved']} below {want}")
        if "pore_size_median" in issues and not (wall_names or open_names) and not fam.is_sphere_lattice:
            got = checks["pore_size_median"]["achieved"]
            want = checks["pore_size_median"]["requested"]
            if got and want:
                scale_length(float(want) / float(got), f"median pore {got} mm vs target {want} mm")
        if "print_islands" in issues and fam in (StructureFamily.VORONOI_FOAM, StructureFamily.STRUT_CUBIC, StructureFamily.STRUT_BCC, StructureFamily.STRUT_OCTET, StructureFamily.STRUT_KELVIN):
            if intent.is_free("family"):
                old = s["family"]
                cell = s.get("unit_cell_size_mm") or 2.0
                s.update({"family": StructureFamily.GYROID.value, "tpms_variant": "sheet", "unit_cell_size_mm": cell, "wall_thickness_mm": None})
                intent.set("family", "gyroid", "designer", "repaired: self-supporting TPMS instead of a lattice with unsupported islands")
                repairs.append({"rule": "switch_family", "reason": "unsupported islands", "from": old, "to": "gyroid"})
            else:
                conflicts.append("the requested lattice has unsupported islands on a layer-based printer; a TPMS sheet would be self-supporting")
        if verification.get("reachable") is False:
            msg = " ".join(verification["messages"])
            if "thinner than" in msg:
                if intent.is_free("resolution_mm") and data["generation"]["final_resolution_mm"] > 0.021:
                    old = data["generation"]["final_resolution_mm"]
                    data["generation"]["final_resolution_mm"] = round(max(0.02, old * 0.7), 4)
                    data["generation"]["reference_resolution_mm"] = data["generation"]["final_resolution_mm"]
                    intent.set("resolution_mm", data["generation"]["final_resolution_mm"], "designer", "repaired: finer resolution for thin walls")
                    repairs.append({"rule": "refine_resolution", "reason": "walls thinner than a voxel", "from": old, "to": data["generation"]["final_resolution_mm"]})
                else:
                    scale_length(1.3, "walls thinner than the resolution")
            else:
                conflicts.append("the porosity target is outside what this architecture can reach")
        porosity_failed = {"porosity_voxel", "porosity_mesh_volume"} & set(verification["failed"])
        if porosity_failed and verification.get("reachable") is not False and not any(r["rule"] == "refine_resolution" for r in repairs):
            # The target is reachable in principle but was missed on this grid: thin walls are
            # lost or thickened by the voxels. A finer grid is the fix, within the memory budget.
            old = data["generation"]["final_resolution_mm"]
            new = round(max(0.02, old * 0.7), 4)
            fitted = self._fit_resources(DomainSpec.model_validate(data["domain"]), new) if intent.is_free("resolution_mm") else old
            if intent.is_free("resolution_mm") and fitted < 0.95 * old:
                data["generation"]["final_resolution_mm"] = data["generation"]["reference_resolution_mm"] = round(fitted, 4)
                intent.set("resolution_mm", round(fitted, 4), "designer", "repaired: finer resolution to resolve thin walls")
                repairs.append({"rule": "refine_resolution", "reason": "porosity missed on the voxel grid", "from": old, "to": round(fitted, 4)})
            elif intent.is_free("resolution_mm"):
                conflicts.append(f"the porosity target needs walls thinner than the {old} mm voxels allowed by the memory budget; allow more memory, or use larger pores or cells")
            else:
                conflicts.append(f"the porosity target is missed at the stated resolution of {old} mm")
        for name in ("agent_permeability_target",):
            if name in issues:
                c = checks[name]
                scale_length(math.sqrt(float(c["requested"]) / float(c["achieved"])), "permeability off target")
        if "agent_stiffness_target" in issues and intent.is_free("porosity"):
            c = checks["agent_stiffness_target"]
            old = data["targets"]["porosity_target"]["target"]
            # Correct the table's prediction by the measured model error, then invert the table again.
            want, got = float(c["requested"]), float(c["achieved"])
            var = TPMSVariant(s.get("tpms_variant") or "sheet")
            phi = porosity_for_stiffness(fam, var, want * want / max(got, 1e-9))
            new = round(min(0.95, max(0.3, phi if phi is not None else old - (0.03 if got < want else -0.03))), 3)
            data["targets"]["porosity_target"]["target"] = new
            intent.set("porosity", new, "designer", "repaired: porosity adjusted towards the stiffness target")
            repairs.append({"rule": "adjust_porosity_for_stiffness", "from": old, "to": new})
        if not repairs:
            if issues and not conflicts:
                conflicts.append("no repair rule applies to: " + ", ".join(sorted(issues)))
            return None, repairs, conflicts
        if not any(r["rule"] == "refine_resolution" for r in repairs):
            data["generation"]["final_resolution_mm"] = self._resolution_after(data, intent)
        return DesignSpecification.model_validate(data), repairs, conflicts

    @staticmethod
    def _required(requested) -> float | None:
        if requested is None:
            return None
        text = str(requested).replace(">=", "").strip()
        try:
            return float(text)
        except ValueError:
            return None

    def _resolution_after(self, data: dict, intent: DesignIntent) -> float:
        h = data["generation"]["final_resolution_mm"]
        if not intent.is_free("resolution_mm"):
            return h
        s = data["structure"]
        fam = StructureFamily(s["family"])
        if fam.is_sphere_lattice:
            return h
        var = TPMSVariant(s.get("tpms_variant") or "sheet")
        p = properties_at(fam, var, data["targets"]["porosity_target"]["target"])
        if p is None:
            return h
        cell = s["unit_cell_size_mm"]
        feature = min(p.wall_d10_per_cell * cell, p.throat_per_cell * cell)
        new = float(min(0.2, max(0.02, feature / 4.0)))
        domain = DomainSpec.model_validate(data["domain"])
        return round(self._fit_resources(domain, new), 4)

    # -- run ---------------------------------------------------------------------------------
    def propose(self, request: str) -> DesignAgentResult:
        """Planner + Designer: a proposal (or an infeasibility explanation); nothing is generated."""
        trace: list[TraceStep] = []
        self._event("planning", "Reading the request")
        intent = self.plan(request, trace)
        result = DesignAgentResult(status="proposed", intent=intent, trace=trace)
        self._event("designing", "Choosing the architecture and checking the printer")
        spec, info = self.design(intent, trace)
        result.design_info = info
        result.alternatives = info.get("alternatives", [])
        if spec is None:
            result.status = "infeasible"
            result.explanation = info.get("explanation", "")
        result.specification = spec
        return result

    def execute(self, result: DesignAgentResult) -> DesignAgentResult:
        """Verifier + Repairer on an approved proposal, then the final checkpoint."""
        intent, trace = result.intent, result.trace
        spec = result.specification
        result.status = "failed"
        for iteration in range(1, self.max_iterations + 1):
            self._event("generating", f"Generating and measuring (iteration {iteration} of at most {self.max_iterations})")
            gen, verification = self.verify(spec, intent)
            result.generation = gen
            record = {"iteration": iteration, "specification": spec.model_dump(mode="json"), "verification": verification}
            trace.append(TraceStep("verifier", "verify", f"iteration {iteration}: {'passed' if verification['success'] else 'failed'}; failed {verification['failed'] or 'none'}; warnings {verification['warnings'] or 'none'}", verification))
            actionable = set(verification["failed"]) | (set(verification["warnings"]) & self.REPAIRABLE_WARNINGS)
            if verification["success"] and not actionable:
                result.iterations.append(record)
                result.status = "delivered" if not verification["warnings"] else "delivered_with_warnings"
                break
            if iteration == self.max_iterations:
                result.iterations.append(record)
                result.status = "delivered_with_warnings" if verification["success"] else "failed"
                result.explanation = f"Stopped after {self.max_iterations} iteration(s); remaining issues: {', '.join(sorted(actionable))}."
                break
            self._event("repairing", "Adjusting the design towards the failed checks")
            new_spec, repairs, conflicts = self.repair(intent, spec, verification)
            record["repairs"] = repairs
            record["conflicts"] = conflicts
            result.iterations.append(record)
            trace.append(TraceStep("repairer", "repair", "; ".join(r.get("reason", r["rule"]) + f" ({r['from']} -> {r['to']})" for r in repairs) or "no repair", {"repairs": repairs, "conflicts": conflicts}))
            if new_spec is None:
                result.status = "delivered_with_warnings" if verification["success"] else "needs_user"
                result.explanation = "; ".join(conflicts) or "No automatic repair is possible."
                break
            spec = new_spec
            result.specification = spec
        if result.status in ("delivered", "delivered_with_warnings"):
            ok = self._checkpoint_final(result)
            trace.append(TraceStep("human", "approve_final", "approved" if ok else "rejected", {}))
            if not ok:
                result.status = "rejected"
        if not result.explanation:
            result.explanation = self.summary_text(result)
        self._event("done", result.status)
        return self._finish(result)

    def run(self, request: str) -> DesignAgentResult:
        result = self.propose(request)
        if result.status == "infeasible":
            return self._finish(result)
        approved = self._checkpoint_intent(result.intent, result.specification, result.design_info)
        result.trace.append(TraceStep("human", "approve_intent", "approved" if approved else "rejected", {}))
        if not approved:
            result.status = "rejected" if approved is False else "needs_user"
            result.explanation = "The design was not approved; nothing was generated."
            return self._finish(result)
        return self.execute(result)

    def _event(self, stage: str, message: str) -> None:
        if self.on_event is not None:
            try:
                self.on_event(stage, message)
            except Exception:
                pass

    def _checkpoint_intent(self, intent, spec, info) -> bool | None:
        if self.approve_intent is not None:
            return bool(self.approve_intent(intent, spec, info))
        return True if self.auto_approve else None

    def _checkpoint_final(self, result) -> bool:
        if self.approve_final is not None:
            return bool(self.approve_final(result))
        return True if self.auto_approve else True

    def summary_text(self, result: DesignAgentResult) -> str:
        spec = result.specification
        gen = result.generation
        if spec is None or gen is None:
            return result.explanation
        m = gen.measurements or {}
        s = spec.structure
        name = table_key(s.family, s.tpms_variant) if s.family.is_tpms else s.family.value
        parts = [f"{name} in a {spec.domain.shape.value} {' x '.join(f'{v:g}' for v in spec.domain.dimensions_mm)} mm, porosity {gen.final_mesh_porosity:.1%} (target {spec.targets.porosity_target.target:.0%})."]
        if m:
            parts.append(
                "Measured: "
                + ", ".join(
                    f"{label} {m[key]:.3g}{unit}"
                    for key, label, unit in (
                        ("pore_d50_mm", "median pore", " mm"),
                        ("wall_d50_mm", "median wall", " mm"),
                        ("percolation_diameter_mm", "largest passing sphere", " mm"),
                        ("permeability_m2", "permeability", " m2"),
                        ("youngs_relative", "E*/Es", ""),
                    )
                    if key in m
                )
                + "."
            )
        if len(result.iterations) > 1:
            parts.append(f"{len(result.iterations) - 1} automatic repair(s) applied.")
        return " ".join(parts)

    def _finish(self, result: DesignAgentResult) -> DesignAgentResult:
        folder = self.output_dir / f"agent_{result.agent_id}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "agent_trace.json"
        path.write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")
        result.trace_path = path
        return result
