# Phase 3B.1.2 Reproduction

Date: 2026-07-13

Observed defect before this phase:

- The API-key password field was blank after reopening, which is correct security behavior.
- The dialog did not separately show whether a stored key existed.
- Nonsecret provider settings were not loaded through a persistent settings path.
- The active provider object was not visibly rebuilt after Save or Apply.
- Automatic deterministic policy could skip an external model without a clear decision label.
- Provider failure could fall back to deterministic parsing without enough visible context.

Implementation environment:

- Branch: `feature/agentic-porous-gui`
- Runtime: bundled Python 3.12
- Keyring backend probe: `keyring` module unavailable in this runtime
- `OPENAI_API_KEY`: not available
- `GEMINI_API_KEY`: not available

Reproduction status after fix:

- QSettings stores nonsecret values under `agent_provider/*`.
- QSettings does not store raw API keys.
- Credential lookup reports explicit mode: environment, keyring, or session.
- Keyring mode reports `CREDENTIAL_BACKEND_UNAVAILABLE` when the backend cannot be imported.
- Session-only credentials remain in process memory only.
- Provider rebuild emits `provider_rebuild_started` and `provider_rebuild_completed` or `provider_rebuild_failed`.
- The Agentic Request panel shows mode, provider, model, external access, credential status, connection status, last decision, and last execution.
- Diagnostics includes an Agent Provider tab and copy action.

Live provider execution:

```text
LIVE_PROVIDER_TEST_NOT_RUN
```

Reason: no valid OpenAI or Gemini key was available in the verification environment, and the keyring package was not importable. No API key was printed, stored in docs, or written to logs.

Manual GUI verification procedure on a machine with credentials:

1. Launch `python -m porous_designer.gui.app`.
2. Open `Agent Provider Settings`.
3. Enable external access.
4. Select OpenAI or Gemini.
5. Choose credential mode.
6. Enter a key if using credential store or session-only mode.
7. Click `Test Connection`.
8. Click `Save`.
9. Reopen the dialog and confirm the password field is blank but status says available.
10. Restart the app and confirm nonsecret settings persist.
11. Enter: `Generate a hexagonal scaffold with about 1 mm pore size, high porosity, and interconnected pores.`
12. Confirm the call decision and approve payload review if an external call is attempted.
13. Confirm the review dialog appears and geometry generation does not start automatically.
