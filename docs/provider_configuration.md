# Provider Configuration

Default mode:

```text
Deterministic only
```

External agent access is disabled by default.

The GUI `Agent Provider Settings` dialog controls:

- external agent access
- provider: Deterministic only, OpenAI, Gemini
- external-call mode: deterministic only, external when recommended, always external
- model ID
- model category
- timeout
- maximum retry count
- reasoning level where supported
- confidence threshold
- escalation model
- confirmation before escalation
- API-key source
- connection test
- key deletion
- payload review text
- cache clearing

Model IDs are configuration values, not business-logic constants spread through
the parser.

Save and Apply persist nonsecret settings and rebuild the active provider
without restarting the GUI. Cancel discards unsaved changes and clears any
unsaved key text.

The API-key field is intentionally blank after reopening. Stored credential
availability is shown separately in the credential status row.
