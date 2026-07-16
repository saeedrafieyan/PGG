# Agentic Architecture

The formal project goal is now:

```text
Agentic Porous-Material Design System
```

Phase 3B.1 introduces human-supervised natural-language interpretation while
keeping the deterministic geometry backend authoritative.

## Flow

```text
User request
  -> deterministic preprocessing
  -> optional provider-neutral LLM parsing
  -> strict schema validation
  -> ambiguity detection
  -> proposed specification
  -> field-by-field human review
  -> explicit approval
  -> existing deterministic estimate / preview / final workflow
```

The agentic layer never starts preview or final generation.

Phase 3B.1.3 separates the GUI into Manual Design and Agentic Design modes.
Agentic approval creates an approved specification revision and a read-only
summary. Manual widgets are not independently editable while Agentic Design is
active.

## Packages

- `agentic.contracts`: strict Pydantic schemas for parsed fields,
  ambiguities, unsupported requests, assumptions, and approval records.
- `agentic.deterministic_parser`: regex, units, terminology, confidence, and
  ambiguity rules.
- `agentic.provider`: provider-neutral interface, deterministic provider,
  mock provider, optional OpenAI/Gemini adapters, and disabled external adapter.
- `agentic.orchestrator`: parse/propose/approve lifecycle and audit writing.
- `agentic.review`: proposal construction and approved-field application.
- `agentic.audit`: reproducible agentic audit files.

## GUI Boundary

The `Agentic Request` panel displays parsed fields and ambiguities. The
`SpecificationReviewDialog` is the only GUI path that can approve parsed
fields. Approved fields create an agentic approved specification revision. The
GUI then shows a read-only approved-specification summary and uses explicit
generation authorization checks before Estimate, Preview, or Final actions.

Phase 3B.1.1 adds optional OpenAI and Gemini providers behind the same
provider-neutral interface. The deterministic call policy decides whether an
external call is needed before any provider request is made.
## Phase 3B.2 Strategy Planning

The architecture now includes a bounded strategy-planning layer after
specification approval. `porous_designer.agentic.strategy` creates strict
`StrategyPlan` objects from approved `DesignSpecification` revisions.

The deterministic planner is authoritative. Optional provider wording can only
add concise explanation or caution text and is rejected if it proposes
forbidden tools such as STEP generation, FEA, autonomous repair, inverse design,
material optimization, arbitrary code, or unrestricted tool use.

Plan approval is separate from specification approval. Agentic Preview and Final
require both an approved non-stale specification and an approved non-stale
strategy plan. Manual Design mode does not use this gate.

## Phase 3B.3 Guarded Execution

Approved plans now create `PlanExecutionSession` records. The Agentic Plan panel
can execute approved steps one at a time through existing deterministic GUI
controller actions and backend services. Preconditions are checked before every
step, observations are structured, and validation gates are mapped from backend
validation reports.

No autonomous plan runner exists in Phase 3B.3.
