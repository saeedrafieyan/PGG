# Provider Error Handling

Provider errors are classified as:

- `PROVIDER_NOT_CONFIGURED`
- `PROVIDER_AUTHENTICATION_FAILED`
- `PROVIDER_MODEL_UNAVAILABLE`
- `PROVIDER_TIMEOUT`
- `PROVIDER_RATE_LIMITED`
- `PROVIDER_QUOTA_EXCEEDED`
- `PROVIDER_NETWORK_ERROR`
- `PROVIDER_SCHEMA_INVALID`
- `PROVIDER_REFUSAL`
- `PROVIDER_CONTENT_FILTERED`
- `PROVIDER_INTERNAL_ERROR`
- `PROVIDER_CANCELLED`
- `PROVIDER_ESCALATION_DECLINED`
- `PROVIDER_CACHE_INVALID`

Retry policy is bounded:

- transient network or timeout: one retry
- rate limit: one delayed retry when retry-after is available
- schema failure: one corrective retry
- authentication/model/quota/refusal/cancellation: no automatic retry

Failures fall back to deterministic parsing and preserve human review.
