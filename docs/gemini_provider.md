# Gemini Provider

Phase 3B.1.1 adds an optional `GeminiProvider`.

Default model:

```text
gemini-3.1-flash-lite
```

The provider uses structured JSON output and validates the result with the same
`ParsedRequestResult` schema used by all providers.

The Google GenAI Python SDK is used only when Gemini is selected, external
access is enabled, and a credential is available through the selected credential
mode. It is not required for deterministic mode or OpenAI mode.

Live tests are manual and opt-in:

```powershell
set GEMINI_API_KEY=<configured locally>
pytest -m live_provider --provider gemini --model gemini-3.1-flash-lite
```

Do not print or commit the key.

In the GUI, select Gemini, choose the credential mode, and click `Test
Connection`. The password field remains blank after saving; use the credential
status row to verify availability.
