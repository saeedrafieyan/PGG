# API-Key Security

Supported keys:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`

Credential priority:

1. current process environment variable
2. operating-system credential store through `keyring`
3. unavailable

Keys are not read from repository files, YAML specifications, run directories,
logs, CLI arguments, or normal Qt settings.

The GUI key field is a password field. Stored keys use the OS credential
manager. Existing keys are never displayed; only source and redacted status are
shown.

Provider errors and audit files use secret redaction.
