"""Deterministic-first natural-language request parser."""

from __future__ import annotations

import re
from typing import Any

from porous_designer.agentic.confidence import (
    score_ambiguous_phrase,
    score_explicit_alias,
    score_explicit_numeric,
    score_inferred_domain,
)
from porous_designer.agentic.contracts import (
    AmbiguityItem,
    Assumption,
    ExtractedField,
    FieldSource,
    MissingRequirement,
    ParsedRequestResult,
    ParserEvidence,
    UnsupportedRequest,
    validate_field_value,
)
from porous_designer.agentic.terminology import DOMAIN_ALIASES, EXPORT_ALIASES, STRUCTURE_ALIASES, mask_pore_phrases, match_alias, normalize_text, tpms_variant_near
from porous_designer.agentic.unit_normalization import LENGTH_UNIT_PATTERN, length_to_mm, porosity_to_fraction

# A length unit that is not the prefix of a longer word ("m" in "microns").
_UNIT = rf"({LENGTH_UNIT_PATTERN})(?![a-zµμ])"
from porous_designer.domain.enums import DomainShape, ExportFormat, StructureFamily


class DeterministicRequestParser:
    parser_version = "4.1"

    def parse(self, request: str) -> ParsedRequestResult:
        if self._contains_prompt_injection(request):
            return ParsedRequestResult(
                provider_mode="deterministic",
                parser_version=self.parser_version,
                missing_requirements=[
                    MissingRequirement(
                        field_path="domain.shape",
                        explanation="Request contains unsafe instruction-like text and was rejected for agentic parsing.",
                        severity="blocking",
                    )
                ],
                provider_failed=True,
                provider_failure_reason="prompt_injection_rejected",
            )
        text = normalize_text(request)
        fields: list[ExtractedField] = []
        evidence: list[ParserEvidence] = []
        ambiguities = self.detect_ambiguities(request)
        unsupported = self.detect_unsupported(request)
        assumptions: list[Assumption] = []

        dimensions = self._extract_dimensions(text)
        if dimensions:
            dims, phrase = dimensions
            fields.append(self._field("domain.dimensions_mm", dims, "mm", 0.99, phrase))
            evidence.append(self._evidence(phrase, "dimension_triplet", dims, 0.99))
            if not self._has_domain_alias(text):
                fields.append(self._field("domain.shape", DomainShape.BOX.value, None, score_inferred_domain(), phrase, requires_confirmation=False))
                assumptions.append(
                    Assumption(
                        field_path="domain.shape",
                        value=DomainShape.BOX.value,
                        rationale="Three orthogonal dimensions imply a box/cuboid domain.",
                        requires_confirmation=False,
                    )
                )
        else:
            cylinder = self._extract_cylinder_dimensions(text)
            sphere = self._extract_sphere_diameter(mask_pore_phrases(text)) if cylinder is None else None
            if cylinder:
                dims, phrase = cylinder
                fields.append(self._field("domain.shape", DomainShape.CYLINDER.value, None, 0.95, phrase))
                fields.append(self._field("domain.dimensions_mm", dims, "mm", 0.95, phrase))
                evidence.append(self._evidence(phrase, "cylinder_dimensions", dims, 0.95))
            elif sphere:
                dims, phrase = sphere
                fields.append(self._field("domain.shape", DomainShape.SPHERE.value, None, 0.95, phrase))
                fields.append(self._field("domain.dimensions_mm", dims, "mm", 0.95, phrase))
                evidence.append(self._evidence(phrase, "sphere_diameter", dims, 0.95))

        domain_alias = match_alias(mask_pore_phrases(text), DOMAIN_ALIASES)
        if domain_alias:
            phrase, shape = domain_alias
            fields.append(self._field("domain.shape", shape.value, None, score_explicit_alias(), phrase))

        family_alias = match_alias(text, STRUCTURE_ALIASES)
        if family_alias:
            phrase, family = family_alias
            fields.append(self._field("structure.family", family.value, None, score_explicit_alias(), phrase))
            evidence.append(self._evidence(phrase, "structure_alias", family.value, 0.95))
            variant = tpms_variant_near(text, phrase) if family.is_tpms else None
            if variant:
                fields.append(self._field("structure.tpms_variant", variant[1].value, None, score_explicit_alias(), variant[0]))
        elif "hexagonal" in text:
            fields.append(
                self._field(
                    "structure.family",
                    StructureFamily.HCP_SPHERICAL_PORES.value,
                    None,
                    score_ambiguous_phrase(),
                    "hexagonal",
                    source=FieldSource.DETERMINISTIC,
                    requires_confirmation=True,
                )
            )

        pore = self._extract_length_after(text, ("generating sphere diameter", "sphere diameter", "pore diameter", "pore size", "pore sizes", "pores"), exclude_prefixes=("spherical ",))
        if pore:
            value, phrase = pore
            fields.append(self._field("structure.pore_diameter_mm", value, "mm", 0.92 if "generating" in phrase else 0.68, phrase, requires_confirmation="generating" not in phrase))
            evidence.append(self._evidence(phrase, "pore_size_length", value, 0.68))

        unit_cell = self._extract_length_after(text, ("unit-cell size", "unit cell size", "unit-cell", "unit cell", "seed spacing", "cell spacing", "cell size", "cells of", "lattice cell", "period"))
        if unit_cell:
            value, phrase = unit_cell
            fields.append(self._field("structure.unit_cell_size_mm", value, "mm", 0.93, phrase))

        wall = self._extract_length_after(
            text,
            ("minimum wall thickness", "min wall thickness", "minimum strut thickness", "minimum strut diameter", "wall thickness", "strut thickness", "strut diameter", "walls of at least", "walls at least"),
        )
        if wall:
            # "Wall thickness 0.3 mm" is read as a minimum; confirm because it may be meant as a fixed value.
            fields.append(self._field("constraints.minimum_wall_thickness_mm", wall[0], "mm", 0.85, wall[1], requires_confirmation="minimum" not in wall[1] and "least" not in wall[1]))
        throat = self._extract_length_after(
            text,
            ("minimum throat size", "minimum throat diameter", "min throat size", "throat size", "throat diameter", "throats of at least", "pore openings of at least", "pore opening", "interconnection size"),
        )
        if throat:
            fields.append(self._field("constraints.minimum_throat_size_mm", throat[0], "mm", 0.85, throat[1], requires_confirmation="minimum" not in throat[1] and "least" not in throat[1]))

        porosity = self._extract_porosity(text)
        if porosity:
            values, phrase = porosity
            if len(values) == 2:
                lo, hi = values
                midpoint = (lo + hi) / 2.0
                fields.extend(
                    [
                        self._field("targets.porosity_target.min_value", lo, None, 0.99, phrase),
                        self._field("targets.porosity_target.max_value", hi, None, 0.99, phrase),
                        self._field("targets.porosity_target.target", midpoint, None, 0.75, phrase, requires_confirmation=True),
                    ]
                )
                assumptions.append(
                    Assumption(
                        field_path="targets.porosity_target.target",
                        value=midpoint,
                        rationale="A porosity range was supplied; midpoint is proposed only for review.",
                    )
                )
            else:
                fields.append(self._field("targets.porosity_target.target", values[0], None, 0.98, phrase))
            evidence.append(self._evidence(phrase, "porosity", values, 0.98))

        if any(word in text for word in ("interconnected", "open pore", "open pores", "percolating", "percolation")):
            fields.append(self._field("constraints.require_open_pores", True, None, 0.88, "interconnected/open pores", requires_confirmation="interconnected" in text))

        preview_res = self._extract_length_after(text, ("preview resolution",))
        if preview_res:
            fields.append(self._field("generation.preview_resolution_mm", preview_res[0], "mm", 0.94, preview_res[1]))
        final_res = self._extract_length_after(text, ("final resolution", "resolution"), exclude_prefixes=("preview ",))
        if final_res:
            fields.append(self._field("generation.final_resolution_mm", final_res[0], "mm", 0.85, final_res[1]))

        formats = []
        for alias, fmt in EXPORT_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", text):
                formats.append(fmt.value)
        if formats:
            fields.append(self._field("export.formats", sorted(set(formats)), None, 0.92, "requested output formats"))

        missing = self._missing_requirements(fields)
        valid_fields = []
        for field in fields:
            try:
                validate_field_value(field.field_path, field.value)
                valid_fields.append(field)
            except Exception as exc:
                unsupported.append(
                    UnsupportedRequest(
                        feature=field.field_path,
                        source_text=field.source_text,
                        explanation=f"Parsed value was rejected by schema validation: {exc}",
                    )
                )
        return ParsedRequestResult(
            provider_mode="deterministic",
            parser_version=self.parser_version,
            extracted_fields=self._dedupe_fields(valid_fields),
            ambiguities=ambiguities,
            missing_requirements=missing,
            unsupported_requests=unsupported,
            assumptions=assumptions,
            evidence=evidence,
        )

    def detect_ambiguities(self, request: str) -> list[AmbiguityItem]:
        text = normalize_text(request)
        items: list[AmbiguityItem] = []
        if "hexagonal" in text and "hexagonal close" not in text and "hcp" not in text:
            items.append(
                AmbiguityItem(
                    identifier="ambiguous_hexagonal",
                    source_phrase="hexagonal",
                    explanation="Hexagonal may describe HCP sphere centers, hexagonal channels, or honeycomb solid cells.",
                    candidate_interpretations=["HCP spherical pore centers", "hexagonal channels", "honeycomb solid cells"],
                    recommended_choice="HCP spherical pore centers",
                    recommendation_rationale="The current validated backend supports HCP spherical-pore lattices, not honeycomb cells.",
                    confidence=0.62,
                    mandatory=True,
                )
            )
        if "pore size" in text:
            items.append(
                AmbiguityItem(
                    identifier="ambiguous_pore_size",
                    source_phrase="pore size",
                    explanation="Pore size is not a single validated measurement.",
                    candidate_interpretations=[
                        "generating sphere diameter",
                        "equivalent pore diameter",
                        "throat diameter",
                        "maximum inscribed pore diameter",
                    ],
                    recommended_choice="generating sphere diameter",
                    recommendation_rationale="Sphere-pore generators accept generating sphere diameter as input.",
                    confidence=0.68,
                    mandatory=True,
                )
            )
        if "cell size" in text and "unit cell" not in text and "unit-cell" not in text:
            items.append(
                AmbiguityItem(
                    identifier="ambiguous_cell_size",
                    source_phrase="cell size",
                    explanation="Cell size can mean the lattice unit-cell size, lattice spacing, or biological cell size.",
                    candidate_interpretations=["lattice unit-cell size", "lattice spacing", "biological cell size"],
                    recommended_choice="lattice unit-cell size",
                    recommendation_rationale="Unit-cell size is the supported input for TPMS, strut and Voronoi families.",
                    confidence=0.60,
                    mandatory=True,
                )
            )
        if "interconnected" in text:
            items.append(
                AmbiguityItem(
                    identifier="ambiguous_connectivity_direction",
                    source_phrase="interconnected",
                    explanation="Connectivity direction was not specified.",
                    candidate_interpretations=["any connectivity", "X percolation", "Y percolation", "Z percolation", "all-axis percolation"],
                    recommended_choice="all-axis percolation",
                    recommendation_rationale="The existing GUI checkbox represents a boundary-connected open-pore network.",
                    confidence=0.74,
                    mandatory=False,
                )
            )
        if re.search(r"\b\d+(\.\d+)?\s*-\s*\d+(\.\d+)?\s*%", text):
            items.append(
                AmbiguityItem(
                    identifier="porosity_range_policy",
                    source_phrase="porosity range",
                    explanation="A porosity range needs a target-selection policy.",
                    candidate_interpretations=["midpoint", "lower bound", "upper bound", "user-selected target"],
                    recommended_choice="midpoint",
                    recommendation_rationale="Midpoint is a neutral proposal but still requires approval.",
                    confidence=0.75,
                    mandatory=True,
                )
            )
        return items

    def detect_unsupported(self, request: str) -> list[UnsupportedRequest]:
        # Wall thickness and throat size are measured validators since Phase 4.2.
        return []

    def _field(self, field_path: str, value: Any, unit: str | None, confidence: float, source_text: str, *, source: FieldSource = FieldSource.DETERMINISTIC, requires_confirmation: bool = False) -> ExtractedField:
        return ExtractedField(
            field_path=field_path,
            value=value,
            unit=unit,
            confidence=confidence,
            source_text=source_text,
            source=source,
            requires_confirmation=requires_confirmation,
        )

    def _evidence(self, phrase: str, rule: str, value: Any, confidence: float) -> ParserEvidence:
        return ParserEvidence(source_text=phrase, rule=rule, normalized_value=value, confidence=confidence)

    def _extract_dimensions(self, text: str) -> tuple[list[float], str] | None:
        pattern = re.compile(
            rf"(\d+(?:\.\d+)?)\s*(?:x|by)\s*(\d+(?:\.\d+)?)\s*(?:x|by)\s*(\d+(?:\.\d+)?)\s*{_UNIT}"
        )
        match = pattern.search(text)
        if not match:
            # "a 12 mm cube", "cube of 12 mm", "12 mm cubic part", "cube with 12 mm sides"
            for cube in (
                re.compile(rf"(\d+(?:\.\d+)?)\s*{_UNIT}\s*(?:-\s*)?(?:sided\s+)?(?:cube|cubic (?:part|block|sample|specimen|scaffold))\b"),
                re.compile(rf"\bcube\b\s*(?:of|with)?\s*(?:side|sides|edge|edges)?\s*(?:length\s*)?(?:of\s*)?(\d+(?:\.\d+)?)\s*{_UNIT}"),
            ):
                m = cube.search(text)
                if m:
                    side = length_to_mm(float(m.group(1)), m.group(2))
                    return [side, side, side], m.group(0)
            return None
        unit = match.group(4)
        dims = [length_to_mm(float(match.group(i)), unit) for i in (1, 2, 3)]
        return dims, match.group(0)

    def _extract_cylinder_dimensions(self, text: str) -> tuple[list[float], str] | None:
        pattern = re.compile(rf"(\d+(?:\.\d+)?)\s*{_UNIT}\s*(?:in\s+)?diameter.*?(\d+(?:\.\d+)?)\s*{_UNIT}\s*(?:high|height|tall|long|thick)")
        match = pattern.search(text)
        if match:
            return [length_to_mm(float(match.group(1)), match.group(2)), length_to_mm(float(match.group(3)), match.group(4))], match.group(0)
        if not re.search(r"\b(?:cylinder|cylindrical|disc|disk|rod|plug)\b", text):
            return None
        # "diameter (of) 8 mm and (a) height (of) 4 mm", in either order
        dia = re.search(rf"diameter\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*{_UNIT}", text)
        hei = re.search(rf"(?:height|length|thickness)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*{_UNIT}", text) or re.search(rf"(\d+(?:\.\d+)?)\s*{_UNIT}\s*(?:high|tall|long|thick)\b", text)
        if dia and hei:
            lo, hi = min(dia.start(), hei.start()), max(dia.end(), hei.end())
            return [length_to_mm(float(dia.group(1)), dia.group(2)), length_to_mm(float(hei.group(1)), hei.group(2))], text[lo:hi]
        return None

    def _extract_length_after(self, text: str, labels: tuple[str, ...], *, exclude_prefixes: tuple[str, ...] = ()) -> tuple[float, str] | None:
        for label in labels:
            # A generic label such as "resolution" must not re-capture a more
            # specific one such as "preview resolution".
            guard = "".join(rf"(?<!{re.escape(prefix)})" for prefix in exclude_prefixes)
            label_re = rf"(?<![a-z]){guard}{re.escape(label)}(?![a-z])"
            # The value must belong to this label: "pores of 600 um", not "pores, walls of at least 1 mm"
            # (the text is normalised, so the gap may not run into another quantity's keyword).
            gap = r"(?:(?!walls?\b|struts?\b|cell|throat|opening|resolution|porosity|porous|thick|high|tall|long|wide|diameter|sphere|cylinder|cube|box)[^\d]){0,24}"
            pattern = re.compile(rf"{label_re}{gap}(\d+(?:\.\d+)?)\s*{_UNIT}")
            match = pattern.search(text)
            if match:
                phrase = match.group(0)
                return length_to_mm(float(match.group(1)), match.group(2)), phrase
            before = re.compile(rf"(\d+(?:\.\d+)?)\s*{_UNIT}\s+{label_re}")
            match = before.search(text)
            if match:
                phrase = match.group(0)
                return length_to_mm(float(match.group(1)), match.group(2)), phrase
        return None

    def _extract_porosity(self, text: str) -> tuple[list[float], str] | None:
        sep = r"\s*(?:-|–|to|and)\s*"
        range_match = re.search(
            rf"(\d+(?:\.\d+)?)\s*%?{sep}(\d+(?:\.\d+)?)\s*%\s*(?:porosity|porous)|porosity\D{{0,24}}?(\d+(?:\.\d+)?)\s*%?{sep}(\d+(?:\.\d+)?)\s*%",
            text,
        )
        if range_match:
            groups = [g for g in range_match.groups() if g is not None]
            return [porosity_to_fraction(float(groups[0])), porosity_to_fraction(float(groups[1]))], range_match.group(0)
        single = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:porosity|porous|pore volume|void)|porosity\D{0,16}(\d+(?:\.\d+)?)\s*%", text)
        if single:
            value = next(g for g in single.groups() if g is not None)
            return [porosity_to_fraction(float(value))], single.group(0)
        return None

    def _extract_sphere_diameter(self, text: str) -> tuple[list[float], str] | None:
        # "a 10 mm sphere", "sphere of 10 mm diameter", "spherical ... 10 mm diameter"
        for pattern in (
            re.compile(rf"(\d+(?:\.\d+)?)\s*{_UNIT}\s*(?:diameter\s+)?(?:sphere|spherical|ball|bead)\b"),
            re.compile(rf"\b(?:sphere|spherical|ball|bead)\b[^.;]*?(\d+(?:\.\d+)?)\s*{_UNIT}\s*(?:in\s+)?diameter"),
            re.compile(rf"\b(?:sphere|spherical|ball|bead)\b[^.;]*?diameter\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*{_UNIT}"),
        ):
            match = pattern.search(text)
            if match:
                return [length_to_mm(float(match.group(1)), match.group(2))], match.group(0)
        return None

    def _has_domain_alias(self, text: str) -> bool:
        return match_alias(mask_pore_phrases(text), DOMAIN_ALIASES) is not None

    def _missing_requirements(self, fields: list[ExtractedField]) -> list[MissingRequirement]:
        paths = {field.field_path for field in fields}
        missing = []
        if "domain.dimensions_mm" not in paths:
            missing.append(MissingRequirement(field_path="domain.dimensions_mm", explanation="Domain dimensions were not found.", severity="blocking"))
        if "structure.family" not in paths:
            missing.append(MissingRequirement(field_path="structure.family", explanation="Structure family was not found.", severity="blocking"))
        if "generation.final_resolution_mm" not in paths:
            missing.append(MissingRequirement(field_path="generation.final_resolution_mm", explanation="Manufacturing/final resolution was not specified.", severity="warning"))
        return missing

    def _dedupe_fields(self, fields: list[ExtractedField]) -> list[ExtractedField]:
        by_path: dict[str, ExtractedField] = {}
        for field in fields:
            current = by_path.get(field.field_path)
            if current is None or field.confidence > current.confidence:
                by_path[field.field_path] = field
        return list(by_path.values())

    def _contains_prompt_injection(self, request: str) -> bool:
        text = normalize_text(request)
        blocked = (
            "ignore previous",
            "system prompt",
            "developer message",
            "run command",
            "execute code",
            "read file",
            "api key",
            "disable validation",
            "approve automatically",
            "generate python",
            "cadquery",
        )
        return any(token in text for token in blocked)
