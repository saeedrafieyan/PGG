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
- Phase 3B.3: guarded plan-step execution and observation integration.

## Current

- Phase 3B.3 completion and review.

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
- guarded user-triggered step execution
- validation gate mapping
- execution audit files
- report and run-history execution evidence

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

Phase 3B.4 should add the next bounded agentic capability without relaxing the
human approval boundary. Recommended scope: richer report review, improved
validation-gate visualization, and a carefully scoped sensitivity-analysis
execution path. Autonomous repair, STEP generation, FEA, inverse design, and
material optimization should remain out of scope unless explicitly promoted to a
future phase.
