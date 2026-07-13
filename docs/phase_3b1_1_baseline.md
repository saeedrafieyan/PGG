# Phase 3B.1.1 Baseline

Baseline branch:

```text
feature/agentic-porous-gui
```

Baseline commits:

```text
a11145c Clean preview layout and diagnostics Phase 3A.3
f4b3ba1 Add human-supervised request interpretation Phase 3B.1
```

## Working Tree

The working tree was clean before Phase 3B.1.1 edits. Git continued to print a
local warning about `C:\Users\Z32/.config/git/ignore` permissions; no project
changes were present.

## Existing Interfaces

Current providers:

- `NoLLMProvider`
- `MockAgentProvider`
- disabled `ExternalAgentProviderAdapter`

Current contract:

- `ParsedRequestResult`
- `ExtractedField`
- `AmbiguityItem`
- `MissingRequirement`
- `UnsupportedRequest`
- `Assumption`
- `ApprovalRecord`

Schemas use Pydantic `extra="forbid"` and reject unknown fields.

## Existing Privacy Boundary

Phase 3B.1 external access is disabled by default. The GUI privacy notice says
that deterministic parsing is the default and external agent access must be
explicitly configured. No API keys are stored by the 3B.1 implementation.

## GUI Workflow

The `Agentic Request` panel accepts natural-language text, parses
deterministically, displays extracted fields and ambiguities, and opens a
review dialog. Parsed fields do not become active until explicit human
approval. Approval populates existing GUI fields and runs deterministic
validation/estimation. Preview/final generation remains a separate user action.

## Deterministic Federica Parse

Request:

```text
Generate an 8 x 14 x 8 mm scaffold with hexagonal packing, 1 mm pore size,
75-80% porosity, interconnected pores, and STL and STP files.
```

Extracted fields:

- `domain.dimensions_mm = [8.0, 14.0, 8.0]`
- `domain.shape = box`
- `structure.family = hcp_spherical_pores`, confirmation required
- `structure.pore_diameter_mm = 1.0`, confirmation required
- `targets.porosity_target.min_value = 0.75`
- `targets.porosity_target.max_value = 0.8`
- `targets.porosity_target.target = 0.775`, confirmation required
- `constraints.require_open_pores = true`, confirmation required
- `export.formats = [stl]`

Ambiguities:

- `ambiguous_hexagonal`
- `ambiguous_pore_size`
- `ambiguous_connectivity_direction`
- `porosity_range_policy`
- `unsupported_step_request`

Unsupported:

- `STEP export`

Missing:

- `generation.final_resolution_mm` warning

## Baseline Tests

- Unit tests: `52 passed`
- Agentic integration tests: `8 passed`
- GUI tests: `39 passed`
- Generator integration tests: `6 passed`

## SDK Availability In Baseline Runtime

- OpenAI Python SDK: not available
- Google GenAI Python SDK: not available
- keyring: not confirmed in the baseline probe because `google` namespace was
  absent during the combined import check

Phase 3B.1.1 must keep provider SDK imports optional so deterministic mode
continues to launch without these packages.
