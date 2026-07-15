# Specification Authority

Phase 3B.1.3 separates specification authority by workflow.

Manual mode:

```text
manual_draft_specification
```

Agentic mode:

```text
agentic_proposed_specification
agentic_approved_specification
```

Agentic approval creates a revision record with:

- specification ID
- revision
- origin
- approval status
- approval ID
- approval timestamp
- superseded revision when applicable

Manual edits cannot mutate the immutable approved agentic specification because
the manual forms are hidden in Agentic Design. If the user requests changes, the
approval becomes stale and preview/final generation are blocked until a new
review is approved.

Run metadata records the active mode, origin, revision, approval status,
provider/model, external-call mode, stale-approval status, and the user action
that authorized generation.
