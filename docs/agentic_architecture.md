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

## Packages

- `agentic.contracts`: strict Pydantic schemas for parsed fields,
  ambiguities, unsupported requests, assumptions, and approval records.
- `agentic.deterministic_parser`: regex, units, terminology, confidence, and
  ambiguity rules.
- `agentic.provider`: provider-neutral interface, deterministic provider,
  mock provider, and disabled external adapter.
- `agentic.orchestrator`: parse/propose/approve lifecycle and audit writing.
- `agentic.review`: proposal construction and approved-field application.
- `agentic.audit`: reproducible agentic audit files.

## GUI Boundary

The `Agentic Request` panel displays parsed fields and ambiguities. The
`SpecificationReviewDialog` is the only GUI path that can approve parsed
fields. Approved fields populate existing GUI widgets and then reuse existing
`DesignSpecification` validation.
