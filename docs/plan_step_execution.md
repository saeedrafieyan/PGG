# Plan Step Execution

Phase 3B.3 adds guarded, user-triggered execution for approved strategy plans.

The execution model is still not autonomous. The system never runs the full plan
chain by itself. Every executable step requires an explicit user action.

## Executable Tools

Only these deterministic tools are executable:

- `estimate_resources`
- `generate_preview`
- `validate_preview`
- `generate_final`
- `validate_final`
- `export_html_report`
- `run_sensitivity_analysis` when explicitly confirmed

No Phase 3B.3 step may invoke STEP generation, FEA, inverse design, material
optimization, autonomous repair, arbitrary code, arbitrary shell commands, or
external CAD generation.

## Preconditions

Before a step runs, the GUI checks:

- Agentic Design mode is active.
- A specification is approved.
- The specification approval is not stale.
- A strategy plan is approved.
- The plan matches the current specification revision.
- The selected step belongs to the plan.
- Previous required executable steps are completed or skipped where allowed.
- Required run artifacts exist.
- No worker is already running.

Blocked steps record structured observations and do not start workers.
