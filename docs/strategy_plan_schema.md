# Strategy Plan Schema

Phase 3B.2 introduces strict Pydantic models in
`src/porous_designer/agentic/strategy.py`.

## Core Models

- `StrategyPlan`
- `StrategyStep`
- `ToolCallProposal`
- `ValidationGate`
- `UserCheckpoint`
- `UnsupportedRequirementNote`
- `RiskItem`
- `PlanAssumption`
- `PlanApprovalRecord`
- `PlanObservation`

## StrategyPlan Fields

- `plan_id`
- `schema_version`
- `specification_id`
- `specification_revision`
- `created_at`
- `planner_source`
- `provider`
- `model`
- `summary`
- `steps`
- `tool_proposals`
- `validation_gates`
- `user_checkpoints`
- `risks`
- `unsupported_requirements`
- `assumptions`
- `estimated_resource_notes`
- `deterministic_backend_version`
- `status`
- `provider_explanation`

Plan status is one of `draft`, `needs_review`, `approved`, `rejected`, or
`stale`.

`StrategyStep.deterministic_tool` is validated against the Phase 3B.2 allowlist.
Arbitrary tools are rejected by schema validation.
