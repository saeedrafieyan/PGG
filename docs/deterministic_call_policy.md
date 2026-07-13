# Deterministic Call Policy

Phase 3B.1.2 exposes the call-decision stage in the GUI:

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
complete, valid, unambiguous proposal unless the user chooses `Always use
external interpretation` or clicks `Interpret with External Model`.

The visible modes are:

- `Deterministic only`
- `External when recommended`
- `Always use external interpretation`

Provider failure sets `DETERMINISTIC_FALLBACK` metadata and remains visible in
the Agentic Request panel and Diagnostics.
