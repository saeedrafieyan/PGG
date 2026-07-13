# Agentic Privacy

External agent access is disabled by default. No external LLM is required to
use PGG.

Allowed external-provider payloads, if explicitly enabled in a later phase:

- natural-language request
- compact deterministic extraction
- JSON schema
- supported terminology
- scalar feasibility results

Not allowed:

- STL/STEP files
- mesh vertices
- voxel arrays
- screenshots unless separately approved
- run directories
- proprietary material datasets
- file-system paths
- environment variables
- API keys

The GUI shows a privacy notice in the `Agentic Request` section.

API keys are discovered from environment variables or OS credential storage.
They are never stored in normal Qt settings, logs, audit files, or request
payloads.
