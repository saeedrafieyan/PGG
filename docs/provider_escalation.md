# Provider Escalation

Low-cost models are used first:

- OpenAI: `gpt-5.6-luna`
- Gemini: `gemini-3.1-flash-lite`

OpenAI escalation model:

- `gpt-5.6-terra`

Escalation is optional and requires confirmation by default. Triggers include:

- schema validation failure after retry
- provider confidence below threshold
- deterministic/provider disagreement
- multiple unresolved ambiguities
- conflicting constraints
- explicit user request for stronger interpretation

The application does not automatically incur higher model cost.
