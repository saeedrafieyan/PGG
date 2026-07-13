# API-Key Security

Supported keys:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`

Credential modes are explicit:

- environment variable
- operating-system credential store through `keyring`
- session only

Keys are not read from repository files, YAML specifications, run directories,
logs, CLI arguments, or normal Qt settings.

The GUI key field is a password field. Stored keys use the OS credential
manager. Existing keys are never displayed; only source and redacted status are
shown.

Provider errors and audit files use secret redaction.

Keyring entries use service `PGG Agent Providers` and username `openai` or
`gemini`. A keyring save is accepted only after immediate readback succeeds.
Session-only keys are kept in process memory and disappear when the application
exits.
