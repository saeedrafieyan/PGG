# External Call Modes

Phase 3B.1.2 exposes the deterministic-first policy as a visible user setting.

Modes:

- Deterministic only: never call an external model.
- External when recommended: call only when ambiguity, missing required fields, unsupported requirements, or low-confidence interpretation remain.
- Always use external interpretation: run deterministic extraction first, then call the selected provider.

Application-wide default:

```text
Deterministic only
```

When a user explicitly enables external access for OpenAI or Gemini, the dialog moves to `External when recommended` unless the user has chosen another mode.

The Agentic Request panel shows the selected mode and the last decision code, including `NO_EXTERNAL_CALL_REQUIRED`, `EXTERNAL_CALL_RECOMMENDED`, `EXTERNAL_ACCESS_DISABLED`, and `DETERMINISTIC_FALLBACK`.
