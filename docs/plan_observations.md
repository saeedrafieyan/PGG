# Plan Observations

Phase 3B.2 records structured observations after user-triggered plan steps.

`PlanObservation` includes:

- `plan_id`
- `step_id`
- `tool_name`
- `run_id`
- `started_at`
- `completed_at`
- `status`
- `scalar_result_summary`
- `validation_status`
- `warnings`
- `errors`
- `artifact_paths`
- `next_recommended_action`

Observations are written to:

```text
runs/<session>/agentic/strategy_plan_observations.json
```

Observation records do not store secrets, hidden reasoning, meshes, voxel
arrays, or full geometry payloads.

Phase 3B.3 also writes execution observations to:

```text
runs/<session>/agentic/plan_observations.json
```

Run-specific reports can include those observations when execution audit files
are copied into `runs/<run_id>/agentic/`.
