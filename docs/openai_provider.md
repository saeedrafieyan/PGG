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

The OpenAI Python SDK is an optional `llm` extra. Deterministic mode does not
require the package.

Live tests are manual and opt-in:

```powershell
set OPENAI_API_KEY=<configured locally>
pytest -m live_provider --provider openai --model gpt-5.6-luna
```

Do not print or commit the key.
