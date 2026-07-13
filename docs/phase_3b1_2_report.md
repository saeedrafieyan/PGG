# Phase 3B.1.2 Report

Scope: Provider Activation, Credential Persistence, and Live Verification.

Implemented:

- Persistent nonsecret provider settings through QSettings.
- Explicit credential modes: environment, keyring, session-only.
- Stable keyring service name: `PGG Agent Providers`.
- Keyring save readback verification.
- Save, Apply, Cancel, and Test Connection semantics.
- Active provider rebuild after Save/Apply without restart.
- External-call modes: deterministic only, when recommended, always external.
- Agentic Request provider status panel.
- `Interpret with External Model` action.
- Redacted Agent Provider diagnostics tab and copy action.
- Provider failure metadata and visible deterministic fallback.
- Real SDK client creation for OpenAI and Gemini when credentials and packages are available.

Root causes reproduced:

- Blank API-key field was expected security behavior but looked like a save failure because no stored-key status was displayed.
- Provider settings had no complete persistent activation path.
- Provider rebuild after Save/Apply was not visible.
- Deterministic call policy skipped external calls without enough GUI transparency.

Verification:

- Provider unit tests: `19 passed`
- Agentic integration tests: `8 passed`
- GUI tests: `47 passed`
- Compile: `python -m compileall src\porous_designer`

Credential backend used:

```text
keyring module unavailable in verification runtime
```

Live provider result:

```text
LIVE_PROVIDER_TEST_NOT_RUN
```

No OpenAI or Gemini key was available. No key was printed, committed, written to QSettings, logs, diagnostics, screenshots, or docs.

Remaining Phase 3B.2 blockers:

- Run an authorized live provider test on a machine with a valid local key.
- Capture redacted GUI screenshots after live success.
- Proceed to geometry strategy agents only after the provider activation path is confirmed live.
