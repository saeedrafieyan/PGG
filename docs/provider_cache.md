# Provider Cache

Phase 3B.1.1 includes an optional cache for validated provider results.

Cache key includes:

- normalized request hash
- parser version
- provider
- model
- schema version
- terminology-registry version

The cache never stores API keys, authorization headers, hidden reasoning,
geometry, filesystem paths, or unvalidated provider output.

Cached results still require human review and approval.
