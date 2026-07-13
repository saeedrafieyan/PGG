# Agent Provider Interface

Phase 3B.1 defines a provider-neutral interface:

```python
class AgentProvider(Protocol):
    def parse_request(self, request: str, deterministic_evidence: dict, schema: dict) -> dict: ...
    def explain_ambiguities(self, request: str, parsed_result: dict, ambiguity_rules: list[dict]) -> dict: ...
    def explain_feasibility(self, deterministic_result: dict, approved_specification: dict) -> dict: ...
```

Providers:

- `NoLLMProvider`: deterministic-only mode, always available, no network.
- `MockAgentProvider`: deterministic test provider for automated tests.
- `OpenAIProvider`: optional strict structured-output adapter.
- `GeminiProvider`: optional strict structured-output adapter.
- `ExternalAgentProviderAdapter`: disabled compatibility adapter.

Provider responses must validate against `ParsedRequestResult` schema. Invalid
responses retry once with schema-error feedback and then fall back to
deterministic-only parsing.
