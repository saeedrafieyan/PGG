# Strategy Agent

Phase 3B.2 adds the first bounded engineering strategy agent.

The strategy agent creates a reviewable plan from a human-approved
`DesignSpecification`. It does not generate geometry, repair models, run FEA,
create STEP files, optimize materials, or execute a chain of tools.

## Inputs

- Approved `DesignSpecification`
- Exact specification revision
- Optional parsed request metadata for unsupported requirements and assumptions

## Output

- `StrategyPlan`
- `PlanApprovalRecord`
- `PlanObservation` records after user-triggered tool runs
- JSON audit files under `runs/<session>/agentic/`

## Deterministic Planner

The deterministic planner is the authority. It proposes only these tools:

- `estimate_resources`
- `generate_preview`
- `validate_preview`
- `generate_final`
- `validate_final`
- `export_html_report`
- `run_sensitivity_analysis` when explicitly approved later

For sphere-pore structures, it plans estimate, preview, preview validation,
user checkpoint, final STL generation, final validation, report export, and a
follow-up archive/duplicate decision.

For TPMS structures, it adds caution notes that pore diameter and throat metrics
are not measured in this phase.

For cylinder domains, it adds voxel-resolution and dimensional-accuracy notes.

STEP/STP requests, wall-thickness measurements, throat-size measurements, FEA,
repair, inverse design, and material optimization remain unsupported.

## Optional Provider Wording

An external or mock provider may only improve wording. Provider output cannot
add tools, remove validation gates, approve a plan, execute a plan, modify the
approved specification, or turn unsupported requirements into supported ones.

If provider wording proposes forbidden tools or executable steps, it is rejected
and the deterministic plan remains unchanged.
