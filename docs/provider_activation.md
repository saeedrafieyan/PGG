# Provider Activation

Phase 3B.1.2 makes provider activation explicit.

Save and Apply now:

- read the current dialog controls
- store nonsecret settings in QSettings
- store a new key only in the selected credential mode
- verify keyring/session availability when applicable
- bump the provider configuration version
- rebuild the active provider object without restarting the app
- refresh the Agentic Request status panel

Provider rebuild events:

- `provider_rebuild_started`
- `provider_rebuild_completed`
- `provider_rebuild_failed`

The active provider can be deterministic, OpenAI, or Gemini. External access must still be enabled before OpenAI or Gemini may be called.

Cancel clears unsaved key text and does not update the active provider.
