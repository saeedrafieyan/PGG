# Agentic Design Workflow

Agentic Design, Interpretation Stage is the human-supervised natural-language
workflow.

Visible:

- natural-language request editor
- provider status and external-call mode
- Parse Request
- Interpret with External Model
- extracted requirements and ambiguities
- human review action
- read-only approved specification summary
- disabled Agent Planning placeholder for Phase 3B.2
- generation action buttons after approval

Hidden:

- independently editable manual domain, structure, target, and manufacturing
  forms

Preview and final generation require:

- resolved mandatory ambiguities
- explicit human approval
- valid approved specification
- non-stale approval status
- explicit user click

Approval does not automatically start preview or final generation.
## Phase 3B.2 Plan Review

After the user approves an agentic specification, Agentic Design shows an
Agentic Plan section. The user can generate a strategy plan, review deterministic
steps, validation gates, unsupported requirements, risks, and checkpoints, then
approve or reject the plan.

Approved plans do not run anything automatically. Estimate, Preview, Final, and
report export remain deterministic user-triggered actions. Preview and Final are
disabled until the current approved specification revision has an approved
strategy plan.

If the approved specification changes, the plan becomes stale and must be
regenerated or reapproved for the new revision.

## Phase 3B.3 Step Execution

After plan approval, use the step-execution table to run deterministic steps
manually. Estimate, Preview, Final, Validation, and Report actions update step
status and append structured observations. Final generation asks for explicit
confirmation before starting.

Blocked steps show the failed precondition and do not start execution.
