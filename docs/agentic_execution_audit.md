# Agentic Execution Audit

Phase 3B.3 writes execution audit files alongside the existing strategy-plan
audit files.

```text
runs/<session>/agentic/plan_execution_session.json
runs/<session>/agentic/plan_step_executions.json
runs/<session>/agentic/plan_observations.json
runs/<session>/agentic/plan_validation_gates.json
runs/<session>/agentic/plan_next_actions.json
runs/<session>/agentic/plan_execution_audit.json
```

When a generated run exists, the same execution evidence is also copied into the
run directory before report export:

```text
runs/<run_id>/agentic/
```

The audit records user-triggered execution evidence only. It does not store API
keys, hidden model reasoning, full meshes, voxel arrays, or provider secrets.
