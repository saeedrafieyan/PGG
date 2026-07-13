# Gemini Provider

Phase 3B.1.1 adds an optional `GeminiProvider`.

Default model:

```text
gemini-3.1-flash-lite
```

The provider uses structured JSON output and validates the result with the same
`ParsedRequestResult` schema used by all providers.

The Google GenAI Python SDK is an optional `llm` extra. It is not required for
deterministic mode or OpenAI mode.

Live tests are manual and opt-in:

```powershell
set GEMINI_API_KEY=<configured locally>
pytest -m live_provider --provider gemini --model gemini-3.1-flash-lite
```

Do not print or commit the key.
