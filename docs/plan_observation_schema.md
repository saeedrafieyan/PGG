# Plan Observation Schema

Phase 3B.3 extends plan observations with execution evidence.

`PlanObservation` records:

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

Observation status can be `completed`, `failed`, `skipped`, `blocked`, or
`cancelled`.

Observations may include scalar estimates, validation statuses, artifact paths,
hashes, runtime, and memory summaries. They do not include full meshes, voxel
arrays, hidden reasoning, or secrets.
