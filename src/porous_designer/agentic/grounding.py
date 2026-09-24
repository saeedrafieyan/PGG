"""Evidence-grounded LLM extraction: schema, validation, and verification.

The language model never produces specification values directly. It returns
a flat, strictly-typed record in which every non-null value carries a
verbatim ``quote`` from the user's request, the number exactly as written,
and the unit exactly as written. Deterministic code then checks that:

* the quote really occurs in the request (after light normalisation),
* every claimed number occurs in the quote,
* the claimed unit is written in the quote,
* a claimed category (structure family, domain shape, ...) is named in the
  quote, or else is flagged as an interpretation that needs confirmation.

Only values that pass become proposed fields; unit conversion happens here,
not in the model. Everything that fails is reported as a rejected value so
the user is asked instead of receiving a hallucinated default.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from porous_designer.agentic.contracts import (
    AmbiguityItem,
    Assumption,
    ExtractedField,
    FieldSource,
    MissingRequirement,
    ParsedRequestResult,
    UnsupportedRequest,
)
from porous_designer.agentic.terminology import (
    DOMAIN_ALIASES,
    EXPORT_ALIASES,
    PROCESS_ALIASES,
    STRUCTURE_ALIASES,
    normalize_text,
)
from porous_designer.agentic.unit_normalization import length_to_mm
from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily

GROUNDED_PARSER_VERSION = "4.0.1-grounded"
SCHEMA_NAME = "AGEGroundedExtraction"

LENGTH_UNIT_CODES = ("mm", "cm", "m", "um")
_UNIT_EVIDENCE = {
    "mm": r"mm|millimet(?:er|re)s?",
    "cm": r"cm|centimet(?:er|re)s?",
    "m": r"m|met(?:er|re)s?",
    "um": r"[µμ]m|um|microns?|micromet(?:er|re)s?",
}
_UNIT_CODE_TO_PARSER_UNIT = {"mm": "mm", "cm": "cm", "m": "m", "um": "um"}
PROCESS_VALUES = tuple(sorted(set(PROCESS_ALIASES.values())))

CONFIDENCE_VERIFIED = 0.90
CONFIDENCE_INTERPRETED = 0.50


# ---------------------------------------------------------------------------
# JSON schema presented to the model (strict-mode compatible)
# ---------------------------------------------------------------------------

_QUOTE = {
    "type": ["string", "null"],
    "description": "Exact, verbatim, contiguous copy of the words in the request that state this value. Null when the request does not state it.",
}


def _obj(properties: dict[str, Any], description: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }
    if description:
        schema["description"] = description
    return schema


def _nullable_enum(values: tuple[str, ...], description: str) -> dict[str, Any]:
    return {"type": ["string", "null"], "enum": [*values, None], "description": description}


def _length(description: str) -> dict[str, Any]:
    return _obj(
        {
            "value": {"type": ["number", "null"], "description": "The number exactly as written in the request. Do not convert units."},
            "unit": _nullable_enum(LENGTH_UNIT_CODES, "The unit exactly as written: mm, cm, m, or um (for µm, um, microns, micrometres)."),
            "quote": _QUOTE,
        },
        description,
    )


def _choice(values: tuple[str, ...], description: str) -> dict[str, Any]:
    return _obj({"value": _nullable_enum(values, "Allowed value, or null if not stated."), "quote": _QUOTE}, description)


def grounded_extraction_schema() -> dict[str, Any]:
    families = tuple(f.value for f in StructureFamily)
    return _obj(
        {
            "domain_shape": _choice(tuple(s.value for s in DomainShape), "Overall part shape, only if the request names it."),
            "box_dimensions": _obj(
                {
                    "values": {"type": "array", "items": {"type": "number"}, "description": "The three box edge lengths exactly as written, or an empty list."},
                    "unit": _nullable_enum(LENGTH_UNIT_CODES, "Unit exactly as written."),
                    "quote": _QUOTE,
                },
                "Box (cuboid) size given as three lengths, e.g. '10 x 10 x 5 mm'.",
            ),
            "cylinder_diameter": _length("Diameter of a cylindrical part."),
            "cylinder_height": _length("Height of a cylindrical part."),
            "structure_family": _choice(families, "Porous structure family. Only choose a value the request names or unambiguously describes."),
            "pore_size": _length("Pore size or pore diameter as stated."),
            "unit_cell_size": _length("Unit-cell size / cell size / period."),
            "porosity": _obj(
                {
                    "kind": _nullable_enum(("single", "range"), "single value or a min-max range."),
                    "value": {"type": ["number", "null"], "description": "Single porosity number exactly as written."},
                    "min": {"type": ["number", "null"], "description": "Lower bound of a range, exactly as written."},
                    "max": {"type": ["number", "null"], "description": "Upper bound of a range, exactly as written."},
                    "unit": _nullable_enum(("percent", "fraction"), "percent if written with % or 'percent', fraction if written like 0.7."),
                    "quote": _QUOTE,
                },
                "Target porosity (void fraction).",
            ),
            "minimum_wall_thickness": _length("Minimum wall / strut thickness."),
            "minimum_throat_size": _length("Minimum throat / pore-opening size."),
            "require_open_pores": _obj(
                {"value": {"type": ["boolean", "null"], "description": "true if the request asks for open or interconnected pores."}, "quote": _QUOTE},
                "Pore interconnectivity requirement.",
            ),
            "preview_resolution": _length("Preview voxel resolution."),
            "final_resolution": _length("Final / manufacturing voxel resolution."),
            "export_formats": _obj(
                {
                    "values": {"type": "array", "items": {"type": "string", "enum": ["stl", "step"]}, "description": "Requested file formats, or an empty list."},
                    "quote": _QUOTE,
                },
                "Requested output file formats.",
            ),
            "manufacturing_process": _choice(PROCESS_VALUES, "Printing process, only if named."),
            "unsupported_requests": {
                "type": "array",
                "description": "Requirements in the request that no field above can hold (other formats, mechanical or biological targets, other geometry types, ...).",
                "items": _obj(
                    {
                        "feature": {"type": "string", "description": "Short name of the requirement."},
                        "quote": {"type": "string", "description": "Verbatim words from the request."},
                    }
                ),
            },
            "ambiguities": {
                "type": "array",
                "description": "Phrases that could reasonably mean different things.",
                "items": _obj(
                    {
                        "quote": {"type": "string", "description": "Verbatim ambiguous words from the request."},
                        "explanation": {"type": "string", "description": "Why it is ambiguous."},
                        "candidates": {"type": "array", "items": {"type": "string"}, "description": "Possible interpretations."},
                    }
                ),
            },
        }
    )


# ---------------------------------------------------------------------------
# Tolerant validation model for the returned JSON
# ---------------------------------------------------------------------------


class _Lenient(BaseModel):
    # Keys the schema does not define are ignored rather than trusted; missing
    # keys default to "not stated". Nothing here is used before verification.
    model_config = ConfigDict(extra="ignore")


class LengthValue(_Lenient):
    value: float | None = None
    unit: str | None = None
    quote: str | None = None


class BoxDimensions(_Lenient):
    values: list[float] = Field(default_factory=list)
    unit: str | None = None
    quote: str | None = None


class Choice(_Lenient):
    value: str | None = None
    quote: str | None = None


class PorosityValue(_Lenient):
    kind: Literal["single", "range"] | None = None
    value: float | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    quote: str | None = None


class FlagValue(_Lenient):
    value: bool | None = None
    quote: str | None = None


class FormatsValue(_Lenient):
    values: list[str] = Field(default_factory=list)
    quote: str | None = None


class QuotedFeature(_Lenient):
    feature: str = ""
    quote: str = ""


class LLMAmbiguity(_Lenient):
    quote: str = ""
    explanation: str = ""
    candidates: list[str] = Field(default_factory=list)


class GroundedExtraction(_Lenient):
    domain_shape: Choice = Field(default_factory=Choice)
    box_dimensions: BoxDimensions = Field(default_factory=BoxDimensions)
    cylinder_diameter: LengthValue = Field(default_factory=LengthValue)
    cylinder_height: LengthValue = Field(default_factory=LengthValue)
    structure_family: Choice = Field(default_factory=Choice)
    pore_size: LengthValue = Field(default_factory=LengthValue)
    unit_cell_size: LengthValue = Field(default_factory=LengthValue)
    porosity: PorosityValue = Field(default_factory=PorosityValue)
    minimum_wall_thickness: LengthValue = Field(default_factory=LengthValue)
    minimum_throat_size: LengthValue = Field(default_factory=LengthValue)
    require_open_pores: FlagValue = Field(default_factory=FlagValue)
    preview_resolution: LengthValue = Field(default_factory=LengthValue)
    final_resolution: LengthValue = Field(default_factory=LengthValue)
    export_formats: FormatsValue = Field(default_factory=FormatsValue)
    manufacturing_process: Choice = Field(default_factory=Choice)
    unsupported_requests: list[QuotedFeature] = Field(default_factory=list)
    ambiguities: list[LLMAmbiguity] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@dataclass
class RejectedValue:
    field_path: str
    proposed_value: Any
    quote: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"field_path": self.field_path, "proposed_value": self.proposed_value, "quote": self.quote, "reason": self.reason}


@dataclass
class GroundingReport:
    fields: list[ExtractedField] = field(default_factory=list)
    rejected: list[RejectedValue] = field(default_factory=list)
    unsupported: list[UnsupportedRequest] = field(default_factory=list)
    ambiguities: list[AmbiguityItem] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)
    dropped_items: int = 0

    @property
    def proposed_value_count(self) -> int:
        return len(self.fields) + len(self.rejected)

    @property
    def ungrounded_rate(self) -> float:
        total = self.proposed_value_count
        return len(self.rejected) / total if total else 0.0

    def to_parsed_result(self, *, provider_mode: str = "openrouter") -> ParsedRequestResult:
        missing = [
            MissingRequirement(
                field_path=r.field_path,
                explanation=f"The language model proposed {r.proposed_value!r} but it could not be verified in your request ({r.reason}). Please state it explicitly.",
                severity="warning",
            )
            for r in self.rejected
        ]
        return ParsedRequestResult(
            provider_mode=provider_mode,
            parser_version=GROUNDED_PARSER_VERSION,
            extracted_fields=self.fields,
            ambiguities=self.ambiguities,
            missing_requirements=missing,
            unsupported_requests=self.unsupported,
            assumptions=self.assumptions,
            provider_metadata={
                "grounding": {
                    "verified_field_count": len(self.fields),
                    "rejected_value_count": len(self.rejected),
                    "ungrounded_rate": self.ungrounded_rate,
                    "dropped_item_count": self.dropped_items,
                    "rejected_values": [r.as_dict() for r in self.rejected],
                }
            },
        )


def normalize_for_matching(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = normalize_text(text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_quote(quote: str) -> str:
    return normalize_for_matching(quote).strip(" .;:!?\"'()[]")


def quote_in_request(quote: str | None, normalized_request: str) -> bool:
    if not quote:
        return False
    cleaned = _clean_quote(quote)
    return bool(cleaned) and cleaned in normalized_request


def numbers_in(text: str) -> list[float]:
    return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", normalize_for_matching(text))]


def _number_stated(value: float, quote: str) -> bool:
    return any(abs(value - n) <= 1e-9 * max(1.0, abs(n)) for n in numbers_in(quote))


def unit_stated(code: str, quote: str) -> bool:
    pattern = _UNIT_EVIDENCE.get(code)
    if pattern is None:
        return False
    return re.search(rf"(?<![a-zµμ])(?:{pattern})(?![a-zµμ])", normalize_for_matching(quote)) is not None


def _alias_values(quote: str, aliases: dict[str, Any]) -> set[str]:
    normalized = normalize_for_matching(quote)
    found = set()
    for alias, value in aliases.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized):
            found.add(value.value if hasattr(value, "value") else str(value))
    return found


class _Verifier:
    def __init__(self, request: str) -> None:
        self.request = request
        self.normalized_request = normalize_for_matching(request)
        self.report = GroundingReport()

    # -- helpers ------------------------------------------------------------
    def reject(self, path: str, value: Any, quote: str | None, reason: str) -> None:
        self.report.rejected.append(RejectedValue(path, value, quote, reason))

    def accept(self, path: str, value: Any, quote: str, *, unit: str | None = None, interpreted: bool = False, requires_confirmation: bool = False) -> None:
        self.report.fields.append(
            ExtractedField(
                field_path=path,
                value=value,
                unit=unit,
                confidence=CONFIDENCE_INTERPRETED if interpreted else CONFIDENCE_VERIFIED,
                source_text=_clean_quote(quote),
                source=FieldSource.LLM_RECOMMENDATION,
                requires_confirmation=requires_confirmation or interpreted,
            )
        )

    def grounded_quote(self, path: str, value: Any, quote: str | None) -> bool:
        if not quote:
            self.reject(path, value, quote, "no supporting quote was given")
            return False
        if not quote_in_request(quote, self.normalized_request):
            self.reject(path, value, quote, "the quoted words do not appear in the request")
            return False
        return True

    def length_mm(self, path: str, item: LengthValue) -> float | None:
        if item.value is None:
            return None
        if not self.grounded_quote(path, item.value, item.quote):
            return None
        assert item.quote is not None
        if not _number_stated(item.value, item.quote):
            self.reject(path, item.value, item.quote, "the number is not written in the quoted words")
            return None
        if item.unit not in _UNIT_CODE_TO_PARSER_UNIT:
            self.reject(path, item.value, item.quote, "no length unit was stated")
            return None
        if not unit_stated(item.unit, item.quote):
            self.reject(path, item.value, item.quote, f"the unit '{item.unit}' is not written in the quoted words")
            return None
        if item.value <= 0:
            self.reject(path, item.value, item.quote, "lengths must be positive")
            return None
        return length_to_mm(item.value, _UNIT_CODE_TO_PARSER_UNIT[item.unit])

    def choice(self, path: str, item: Choice, aliases: dict[str, Any], allowed: set[str]) -> None:
        if item.value is None:
            return
        value = item.value.strip().lower()
        if value not in allowed:
            self.reject(path, item.value, item.quote, "the value is not one of the allowed options")
            return
        if not self.grounded_quote(path, value, item.quote):
            return
        assert item.quote is not None
        named = _alias_values(item.quote, aliases)
        if value in named:
            # Several different names in one quote ("gyroid or diamond") are
            # a choice the user must make, not a verified value.
            self.accept(path, value, item.quote, requires_confirmation=len(named) > 1)
        elif named:
            self.reject(path, value, item.quote, f"the quoted words name {sorted(named)}, not {value!r}")
        else:
            self.accept(path, value, item.quote, interpreted=True)

    # -- sections -------------------------------------------------------------
    def verify(self, extraction: GroundedExtraction) -> GroundingReport:
        self._domain(extraction)
        self.choice("structure.family", extraction.structure_family, STRUCTURE_ALIASES, {f.value for f in StructureFamily})
        for path, item in (
            ("structure.pore_diameter_mm", extraction.pore_size),
            ("structure.unit_cell_size_mm", extraction.unit_cell_size),
            ("constraints.minimum_wall_thickness_mm", extraction.minimum_wall_thickness),
            ("constraints.minimum_throat_size_mm", extraction.minimum_throat_size),
            ("generation.preview_resolution_mm", extraction.preview_resolution),
            ("generation.final_resolution_mm", extraction.final_resolution),
        ):
            mm = self.length_mm(path, item)
            if mm is not None:
                # "Pore size" is ambiguous between the generating sphere
                # diameter and the measured pore/throat size; always confirm.
                self.accept(path, mm, item.quote or "", unit="mm", requires_confirmation=path == "structure.pore_diameter_mm")
        self._porosity(extraction.porosity)
        self._open_pores(extraction.require_open_pores)
        self._formats(extraction.export_formats)
        self.choice("manufacturing.process", extraction.manufacturing_process, PROCESS_ALIASES, set(PROCESS_VALUES))
        self._unsupported(extraction.unsupported_requests)
        self._ambiguities(extraction.ambiguities)
        return self.report

    def _domain(self, extraction: GroundedExtraction) -> None:
        box = extraction.box_dimensions
        box_dims: list[float] | None = None
        if box.values:
            path = "domain.dimensions_mm"
            if len(box.values) != 3:
                self.reject(path, box.values, box.quote, "a box needs exactly three lengths")
            elif self.grounded_quote(path, box.values, box.quote):
                assert box.quote is not None
                if not all(_number_stated(v, box.quote) for v in box.values):
                    self.reject(path, box.values, box.quote, "not every number is written in the quoted words")
                elif box.unit not in _UNIT_CODE_TO_PARSER_UNIT or not unit_stated(box.unit, box.quote):
                    self.reject(path, box.values, box.quote, "no length unit was written with the dimensions")
                elif any(v <= 0 for v in box.values):
                    self.reject(path, box.values, box.quote, "lengths must be positive")
                else:
                    box_dims = [length_to_mm(v, _UNIT_CODE_TO_PARSER_UNIT[box.unit]) for v in box.values]
        diameter = self.length_mm("domain.dimensions_mm", extraction.cylinder_diameter)
        height = self.length_mm("domain.dimensions_mm", extraction.cylinder_height)
        cylinder_dims = [diameter, height] if diameter is not None and height is not None else None
        if (diameter is None) != (height is None) and (extraction.cylinder_diameter.value is not None or extraction.cylinder_height.value is not None):
            # Half a cylinder is not a domain; the verified half is reported
            # so the user is asked for the other one.
            if diameter is not None or height is not None:
                self.reject("domain.dimensions_mm", [diameter, height], None, "a cylinder needs both diameter and height")

        shape_before = len(self.report.fields)
        self.choice("domain.shape", extraction.domain_shape, DOMAIN_ALIASES, {s.value for s in DomainShape})
        stated_shape = next((f.value for f in self.report.fields[shape_before:] if f.field_path == "domain.shape"), None)

        if box_dims is not None and cylinder_dims is not None:
            self.reject("domain.dimensions_mm", {"box": box_dims, "cylinder": cylinder_dims}, box.quote, "both box and cylinder sizes were proposed")
            return
        if box_dims is not None:
            if stated_shape not in (None, DomainShape.BOX.value):
                self.reject("domain.dimensions_mm", box_dims, box.quote, f"three box lengths conflict with the stated shape {stated_shape!r}")
                return
            self.accept("domain.dimensions_mm", box_dims, box.quote or "", unit="mm")
            if stated_shape is None:
                self.accept("domain.shape", DomainShape.BOX.value, box.quote or "")
                self.report.assumptions.append(
                    Assumption(field_path="domain.shape", value=DomainShape.BOX.value, rationale="Three orthogonal dimensions imply a box/cuboid domain.", requires_confirmation=False)
                )
        elif cylinder_dims is not None:
            if stated_shape not in (None, DomainShape.CYLINDER.value):
                self.reject("domain.dimensions_mm", cylinder_dims, extraction.cylinder_diameter.quote, f"cylinder sizes conflict with the stated shape {stated_shape!r}")
                return
            quote = extraction.cylinder_diameter.quote or ""
            self.accept("domain.dimensions_mm", cylinder_dims, quote, unit="mm")
            if stated_shape is None:
                self.accept("domain.shape", DomainShape.CYLINDER.value, quote)

    def _porosity(self, item: PorosityValue) -> None:
        if item.kind is None and item.value is None and item.min is None and item.max is None:
            return
        base = "targets.porosity_target"
        kind = item.kind or ("range" if item.min is not None or item.max is not None else "single")
        numbers = [item.value] if kind == "single" else [item.min, item.max]
        if any(n is None for n in numbers):
            self.reject(f"{base}.target", numbers, item.quote, "incomplete porosity value")
            return
        if not self.grounded_quote(f"{base}.target", numbers, item.quote):
            return
        assert item.quote is not None
        if not all(_number_stated(float(n), item.quote) for n in numbers):  # type: ignore[arg-type]
            self.reject(f"{base}.target", numbers, item.quote, "the number is not written in the quoted words")
            return
        quote_norm = normalize_for_matching(item.quote)
        has_percent = "%" in quote_norm or "percent" in quote_norm
        unit = item.unit
        if unit == "percent" and not has_percent:
            self.reject(f"{base}.target", numbers, item.quote, "percent was claimed but no % is written")
            return
        if unit is None:
            unit = "percent" if has_percent else None
        if unit is None:
            if all(0.0 <= float(n) <= 1.0 for n in numbers):  # type: ignore[arg-type]
                unit = "fraction"
            else:
                self.reject(f"{base}.target", numbers, item.quote, "porosity unit (percent or fraction) is not stated")
                return
        fractions = [float(n) / 100.0 if unit == "percent" else float(n) for n in numbers]  # type: ignore[arg-type]
        if not all(0.0 < f < 1.0 for f in fractions):
            self.reject(f"{base}.target", numbers, item.quote, "porosity must lie strictly between 0 and 100 %")
            return
        # A number without the word porosity/porous/void nearby may belong to
        # something else (e.g. "70% of the height"); keep it but ask.
        about_porosity = any(word in quote_norm for word in ("poros", "porous", "void", "open volume", "empty"))
        if kind == "single":
            self.accept(f"{base}.target", fractions[0], item.quote, requires_confirmation=not about_porosity)
        else:
            lo, hi = sorted(fractions)
            self.accept(f"{base}.min_value", lo, item.quote, requires_confirmation=not about_porosity)
            self.accept(f"{base}.max_value", hi, item.quote, requires_confirmation=not about_porosity)
            midpoint = (lo + hi) / 2.0
            self.accept(f"{base}.target", midpoint, item.quote, requires_confirmation=True)
            self.report.assumptions.append(
                Assumption(field_path=f"{base}.target", value=midpoint, rationale="A porosity range was supplied; midpoint is proposed only for review.")
            )

    def _open_pores(self, item: FlagValue) -> None:
        if item.value is None:
            return
        path = "constraints.require_open_pores"
        if not self.grounded_quote(path, item.value, item.quote):
            return
        assert item.quote is not None
        normalized = normalize_for_matching(item.quote)
        evidence = any(word in normalized for word in ("interconnect", "open pore", "open-pore", "open porosity", "percolat", "connected"))
        if item.value and evidence:
            self.accept(path, True, item.quote)
        else:
            self.accept(path, bool(item.value), item.quote, interpreted=True)

    def _formats(self, item: FormatsValue) -> None:
        if not item.values:
            return
        path = "export.formats"
        if not self.grounded_quote(path, item.values, item.quote):
            return
        assert item.quote is not None
        named = _alias_values(item.quote, EXPORT_ALIASES)
        verified = sorted({v.lower() for v in item.values if v.lower() in named})
        missing = sorted({v.lower() for v in item.values} - set(verified))
        if missing:
            self.reject(path, missing, item.quote, "the format is not named in the quoted words")
        if ExportFormat.STEP.value in verified:
            self.report.unsupported.append(
                UnsupportedRequest(feature="STEP export", source_text=_clean_quote(item.quote), explanation="STEP export is not available yet; STL is produced instead.")
            )
        accepted = [v for v in verified if v != ExportFormat.STEP.value] or ([ExportFormat.STL.value] if verified else [])
        if accepted:
            self.accept(path, accepted, item.quote)

    def _unsupported(self, items: list[QuotedFeature]) -> None:
        existing = {u.feature for u in self.report.unsupported}
        for item in items:
            if not item.feature.strip() or not quote_in_request(item.quote, self.normalized_request):
                self.report.dropped_items += 1
                continue
            if item.feature in existing:
                continue
            existing.add(item.feature)
            self.report.unsupported.append(
                UnsupportedRequest(feature=item.feature.strip()[:120], source_text=_clean_quote(item.quote), explanation="Identified by the language model; not supported by the current generator.")
            )

    def _ambiguities(self, items: list[LLMAmbiguity]) -> None:
        for index, item in enumerate(items, start=1):
            if not quote_in_request(item.quote, self.normalized_request) or not item.explanation.strip():
                self.report.dropped_items += 1
                continue
            candidates = [c.strip()[:120] for c in item.candidates if c.strip()][:6]
            self.report.ambiguities.append(
                AmbiguityItem(
                    identifier=f"llm_ambiguity_{index}",
                    source_phrase=_clean_quote(item.quote),
                    explanation=item.explanation.strip()[:400],
                    candidate_interpretations=candidates,
                    recommended_choice=candidates[0] if candidates else "",
                    recommendation_rationale="Raised by the language model; review before approval.",
                    confidence=CONFIDENCE_INTERPRETED,
                    mandatory=False,
                )
            )


def verify_grounded_extraction(request: str, extraction: GroundedExtraction) -> GroundingReport:
    return _Verifier(request).verify(extraction)
