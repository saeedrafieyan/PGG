# Human Approval Boundary

The agentic parser is advisory. It cannot approve specifications or start
geometry generation.

Approval requires:

1. parsed request evidence
2. ambiguity review where needed
3. field-by-field review
4. explicit `Approve Resolved Specification`

Approved fields are applied to existing GUI widgets. The current
`SpecificationModel` then validates the resulting `DesignSpecification`.

After approval, deterministic feasibility estimation runs. Preview and final
generation remain separate user actions.

If the user manually edits a scientific field after approval, the approval state
becomes stale and the previous approval audit record is preserved.
