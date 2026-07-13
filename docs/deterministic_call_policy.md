# Deterministic Call Policy

Phase 3B.1.1 adds an explicit call-decision stage:

```text
deterministic_parse
  -> assess_completeness
  -> assess_ambiguity
  -> assess_conflicts
  -> assess_unsupported_requirements
  -> decide_external_call
```

Decision codes:

- `NO_EXTERNAL_CALL_REQUIRED`
- `EXTERNAL_CALL_RECOMMENDED`
- `EXTERNAL_CALL_REQUIRED_FOR_INTERPRETATION`
- `EXTERNAL_ACCESS_DISABLED`
- `DETERMINISTIC_FALLBACK`

External models are not called when deterministic parsing already provides a
complete, valid, unambiguous proposal.
