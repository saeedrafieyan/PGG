# Live Provider Verification

Status for this implementation run:

```text
LIVE_PROVIDER_TEST_NOT_RUN
```

No OpenAI or Gemini environment credential was available, and the verification runtime did not have an importable `keyring` package. No live API call was attempted.

Manual OpenAI procedure:

```powershell
$env:OPENAI_API_KEY = "<configured locally>"
python -m porous_designer.gui.app
```

Then choose OpenAI, Environment variable credential mode, and click `Test Connection`.

Manual Gemini procedure:

```powershell
$env:GEMINI_API_KEY = "<configured locally>"
python -m porous_designer.gui.app
```

Then choose Gemini, Environment variable credential mode, and click `Test Connection`.

Use this ambiguous request for live validation:

```text
Generate a hexagonal scaffold with about 1 mm pore size, high porosity, and interconnected pores.
```

Record provider, model, request ID if returned, latency, token usage, structured validation status, and redacted metadata only.
