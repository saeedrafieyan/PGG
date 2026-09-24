# Phase 4.0 — Stabilisation and evidence-grounded OpenRouter extraction

Phase 4.0 is the first step of the AGE backbone plan. It makes the
natural-language path actually work, removes silent assumptions, and fixes
reliability bugs found in the audit. Geometry generation is unchanged.

## Why

The Phase 3B provider path had never completed a live call: every recorded
OpenAI request failed with `invalid_json_schema`, because the internal
`ParsedRequestResult` Pydantic schema is not valid for strict structured
output. The timeout wrapper also blocked the GUI thread, and several parser
defects changed user values without telling them.

## What changed

### One provider: OpenRouter

* `agentic/openrouter.py` — a small `httpx` client (`/chat/completions`,
  `/models`, `/key`), HTTP-status error classification, and a cached model
  catalog.
* `OpenRouterProvider` in `agentic/provider.py` replaces `OpenAIProvider`,
  `GeminiProvider`, and the unused `ExternalAgentProviderAdapter`.
* Default model chain: `qwen/qwen3.8-27b:free`, then `nex-agi/nex-n2.5-pro:free`,
  then `nvidia/nemotron-3-super-120b-a12b:free` (all free, all with strict
  structured output in Sept 2026). Nemotron's free endpoints require allowing
  prompt training, so with the default `data_collection: deny` it returns 404
  and is skipped. The live catalog is checked at run time; unlisted models are
  skipped.
* Old QSettings (schema version < 3) fall back to deterministic-only mode.

### Anti-hallucination design

The language model never writes specification values. `agentic/grounding.py`
defines a flat, strict-mode JSON schema in which every value carries:

* `quote` — a verbatim, contiguous copy of the request words that state it,
* the number exactly as written (no conversion, no rounding),
* the unit exactly as written (`mm`, `cm`, `m`, `um`; `percent`/`fraction`).

Deterministic verification then accepts a value only if the quote occurs in
the request, every claimed number occurs in the quote, and the claimed unit is
written in the quote. Unit conversion happens in code. Categories (structure
family, shape, process, format) must be named in the quote; a vague description
("sponge-like") is kept only as a confirmation-required interpretation.
Anything that fails is turned into a question for the user, and is counted
(`grounding.rejected_value_count`, `ungrounded_rate`) in the provider
metadata.

The extraction is independent of the deterministic parser: the model does not
see the regex results. `merge_with_deterministic` keeps deterministic fields
primary, fills gaps with verified model fields, and marks conflicting fields
for confirmation with a blocking disagreement record.

Request parameters (see `ProviderSettings`):

| Parameter | Value | Reason |
|---|---|---|
| `temperature` | 0 | faithful copying, not creativity |
| `seed` | 7, only where supported | reproducibility |
| `max_tokens` | 3000 | room for reasoning models without truncation |
| `reasoning` | `{effort: low, exclude: true}` where supported | cost; hidden reasoning is not returned |
| `response_format` | strict `json_schema`; `json_object` + schema in prompt for models without it | server-side enforcement where possible |
| `provider.require_parameters` | `true` | never route to an endpoint that silently ignores the schema or sampling settings |
| `provider.data_collection` | `deny` (setting to allow) | prompts are not stored or trained on |

Optional parameters are sent only if the model's catalog entry lists them,
because `require_parameters` would otherwise exclude every endpoint.

### Retries, fallbacks, time limits

* Only retryable failures are retried on the same model: timeouts, 408, short
  429s, 500/502/504, and invalid JSON (one self-repair turn with the error).
* 401/402/403 stop immediately. 404, 503, long 429s (e.g. the free daily cap)
  and 400s move to the next model in the chain.
* The whole call is bounded by `total_deadline_s` (default 180 s).
* `call_provider_with_timeout` no longer joins a hung thread on exit.
* GUI parsing that may reach the network runs in a background thread;
  deterministic parsing stays synchronous.
* The connection test uses the zero-cost `/key` endpoint and the public
  catalog, so it does not spend one of the 50 free requests per day.

### Other fixes

* The parser understands µm / um / microns ("500 um" used to be dropped, and
  review then silently injected 1.0 mm). Units need a word boundary, so the
  "m" of "microns" is no longer read as metres.
* "preview resolution 0.1 mm" is no longer also captured as the final
  resolution. Decimal commas ("1,2 mm") are read as decimals.
* Missing structure parameters are no longer filled silently: a
  `FieldSource.DEFAULT` row marked "ASSUMED" appears in the review, and
  rejecting it blocks approval with a clear message.
* Requests rejected as prompt injection are never forwarded to a provider.
* `generate_porous_stl` no longer mutates the caller's specification.
* Nested `tracemalloc` in mesh optimisation no longer corrupts peak-memory
  reporting.
* Plan observations read `overall_status` (the key that exists) instead of
  `aggregate_status`.
* `porous_designer/paths.py`: runs, caches, and `configs/default.yaml` are
  resolved from the checkout root (or `AGE_HOME`, `AGE_RUNS_DIR`,
  `AGE_CONFIG`), not the working directory. A missing config file logs a
  warning.
* Duplicate test module names that broke `pytest` collection were renamed.
* 146 MB of generated STL/STEP/log files and a `.pyc` were untracked (files
  kept on disk; history not rewritten).

## Usage

```
porous-designer credentials set          # key is read without echo into the OS credential store
porous-designer credentials status
porous-designer openrouter-models        # free models with strict structured output
porous-designer evaluate-agent-provider --provider openrouter
```

The live benchmark (`agentic/evaluation.py:live_extraction_cases`) has 12
cases, including hallucination bait (typical-value requests, missing units,
off-topic text, prompt injection). It reports `field_recall`,
`accepted_wrong`, `accepted_forbidden` (values accepted although never
stated), and `caught_by_verifier`. The free tier allows 50 requests per day
for accounts with less than 10 purchased credits.

## Limitations

* The prompt-injection filter is still a substring blocklist and rejects
  benign text that contains, e.g., "cadquery".
* Only the request-parsing step uses the LLM; planning and repair remain
  deterministic (Phase 4.3).
* Free models change often; defaults must be re-checked with
  `openrouter-models`.
