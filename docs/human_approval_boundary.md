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
