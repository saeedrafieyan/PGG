# Human Approval Boundary

The agentic parser is advisory. It cannot approve specifications or start
geometry generation.

Approval requires:

1. parsed request evidence
2. ambiguity review where needed
3. field-by-field review
4. explicit `Approve Resolved Specification`

Approved fields create a new agentic approved specification revision. In
Agentic Design mode the normal manual editing forms are hidden and a read-only
summary is shown.

After approval, Estimate, Preview, and Final remain separate user actions.

If the user manually edits a scientific field after approval, the approval state
becomes stale and the previous approval audit record is preserved. Stale
approval blocks agentic Preview and Final generation.
## Strategy Plan Approval

Phase 3B.2 adds a second approval boundary after specification approval.

The first approval applies a parsed natural-language request to a
`DesignSpecification`. The second approval accepts a deterministic engineering
strategy plan for that exact specification revision.

Plan approval does not authorize autonomous execution. It only enables the user
to trigger deterministic Preview and Final actions manually in Agentic Design
mode. If the specification changes, both the prior specification approval and
the plan authorization are considered stale for execution.
