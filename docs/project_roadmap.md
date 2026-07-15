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
- Phase 3B.2: Engineering Strategy Agent and Plan Approval.

## Current

- Phase 3B.2 completion and review.

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
- deterministic strategy planning
- human plan approval
- plan observations

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

Phase 3B.3 should add the next bounded agentic capability without relaxing the
human approval boundary. Recommended scope: richer per-step execution status,
report export integration from the plan panel, and guarded sensitivity-analysis
proposal handling. Autonomous repair, STEP generation, FEA, inverse design, and
material optimization should remain out of scope unless explicitly promoted to a
future phase.
