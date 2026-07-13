# Credential Persistence

Raw API keys are never stored in QSettings and are never repopulated into the password field after closing the dialog.

Supported credential modes:

- Environment variable: `OPENAI_API_KEY` or `GEMINI_API_KEY`
- Operating-system credential store through `keyring`
- Session only, stored in process memory until exit

The GUI shows credential status separately from the password field:

```text
Stored key: Available
Key source: Windows Credential Manager
Key identifier: openai, fingerprint: ...1234
```

or:

```text
Stored key: Not found
Key source: Environment variable
Environment variable not found: OPENAI_API_KEY
```

Keyring service:

```text
PGG Agent Providers
```

Usernames:

```text
openai
gemini
```

Keyring save performs immediate readback verification. If the backend is unavailable, the GUI reports the credential failure and does not claim that the key was saved.
