# Plan Review Workflow

Agentic Design now follows this sequence:

1. User enters a natural-language request.
2. Deterministic extraction runs, with optional external interpretation.
3. Ambiguities are resolved by the user.
4. The user approves the proposed specification.
5. The user generates a strategy plan.
6. The user reviews the plan, unsupported requirements, validation gates, risks,
   and checkpoints.
7. The user approves or rejects the plan.
8. Only an approved, non-stale plan unlocks Agentic Preview and Final.
9. Each deterministic execution step still requires an explicit user click.

Manual Design mode does not require a strategy plan.

Estimate can be run after specification approval, but Preview and Final require
plan approval in Agentic Design mode.

If the approved specification changes, the current plan becomes stale and no
longer authorizes execution.
