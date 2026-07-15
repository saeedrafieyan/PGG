# Phase 3B.1.3 Report

Scope: Separate Manual and Agentic Workflows with Live Provider Validation.

Implemented:

- Top-level `ApplicationMode`: Manual Design and Agentic Design.
- Persistent last selected mode through QSettings.
- Manual mode hides the agentic request/provider workflow from the main design area.
- Agentic mode hides editable manual domain, structure, target, and manufacturing forms.
- Agentic approval creates an approved specification revision and read-only summary.
- Switching from Agentic to Manual creates an editable derived copy and invalidates agentic execution authorization.
- Switching from Manual to Agentic starts a new review-required interpretation workflow.
- Preview and final generation in Agentic Design require a non-stale approved specification.
- Manual generation does not require agentic approval.
- GUI workers receive and persist `workflow_metadata.json` for mode/provenance.
- Provider connection status remains distinct from full interpretation status.

Verification:

```text
compileall src\porous_designer
pytest tests\unit -q
72 passed

pytest tests\integration\test_agentic_phase_3b1.py tests\integration\test_phase_2b_generators.py -q
14 passed

pytest tests\gui\test_phase_3a_gui.py -q
54 passed
```

Live provider status:

```text
LIVE_PROVIDER_TEST_NOT_RUN
```

No local API key was provided to Codex. No secret was written to docs, logs, or
tests.

Provider environment probe:

```text
OPENAI_API_KEY available: false
GEMINI_API_KEY available: false
openai SDK available: false
google-genai SDK available: false
keyring SDK available: false
```

Screenshots:

Automated screenshots were not captured in this headless verification run.

Remaining limitations:

- The Agentic Design summary is textual in this phase.
- Full live-provider interpretation still requires a local key and installed
  `llm` extra.
- Strategy planning and bounded repair remain Phase 3B.2 work.
