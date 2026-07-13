# OpenAI Provider

Phase 3B.1.1 adds an optional `OpenAIProvider`.

Default model:

```text
gpt-5.6-luna
```

Optional escalation model:

```text
gpt-5.6-terra
```

The provider uses strict `ParsedRequestResult` validation after every response.
It requests compact JSON only and does not enable tools, web search, file
access, code execution, image input, or hidden reasoning.

The OpenAI Python SDK is used only when OpenAI is selected, external access is
enabled, and a credential is available through the selected credential mode.
Deterministic mode does not require the package.

Live tests are manual and opt-in:

```powershell
set OPENAI_API_KEY=<configured locally>
pytest -m live_provider --provider openai --model gpt-5.6-luna
```

Do not print or commit the key.

In the GUI, select OpenAI, choose the credential mode, and click `Test
Connection`. The password field remains blank after saving; use the credential
status row to verify availability.
