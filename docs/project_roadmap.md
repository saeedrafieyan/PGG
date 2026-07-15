# Project Roadmap

Formal goal:

```text
Agentic Porous-Material Design System
```

## Completed

- Phase 3A: local deterministic PySide6 GUI.
- Phase 3A.1: Windows worker/runtime stability.
- Phase 3A.2: scientific preview rendering quality.
- Phase 3A.3: compact preview layout and Diagnostics separation.
- Phase 3B.1: human-supervised natural-language requirement interpretation.
- Phase 3B.1.1: secure optional low-cost OpenAI/Gemini provider integration
  and deterministic/provider evaluation.
- Phase 3B.1.2: provider activation, credential persistence, and connection
  verification.
- Phase 3B.1.3: separated Manual Design and Agentic Design workflows.

## Current

- Phase 3B.1.3 completion and review.

Scope:

- deterministic-first parsing
- provider-neutral optional LLM interface
- strict schema validation
- ambiguity detection
- field-by-field review
- explicit human approval
- audit files
- mode-specific generation authorization
- specification authority and provenance records

Out of scope:

- autonomous geometry modification
- arbitrary Python or CAD code generation
- STEP generation
- FEA
- inverse design
- material optimization
- cloud deployment
- unrestricted multi-agent conversations

## Recommended Next

Phase 3B.2 should add strategy-agent planning and bounded repair without
relaxing the human approval boundary.
