# Live Interpretation Validation

Phase 3B.1.3 keeps live-provider validation honest.

Connection Test verifies:

- credential availability
- provider SDK call path
- selected model access
- lightweight structured JSON output

Connection Test does not prove full natural-language interpretation.

Full interpretation validation requires:

- Agentic Design mode
- external access enabled
- selected provider and model
- available credential
- Parse Request or Interpret with External Model on an ambiguous request
- validated `ParsedRequestResult`
- human-review dialog reached
- no automatic geometry generation

Implementation-run status:

```text
LIVE_PROVIDER_TEST_NOT_RUN
```

Reason: no local API key was provided to Codex. Do not claim live success unless
request ID or equivalent provider metadata, latency, structured validation, and
redacted audit output are available.
