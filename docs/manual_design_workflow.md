# Manual Design Workflow

Manual Design is the direct engineering-parameter workflow.

Visible and editable:

- output configuration
- domain controls
- structure-family controls
- geometry parameters
- porosity target and constraints
- manufacturing fields
- generation settings
- Estimate, Generate Preview, Generate Final

Hidden:

- natural-language request parsing
- provider status in the main design area
- ambiguity and agentic review controls
- approved agentic specification summary

Manual generation does not require agentic approval. Runs started from Manual
Design record `application_mode=manual_design` and `approval_status=not_required`.

If a manual draft is derived from an agentic specification, it becomes an
editable copy. The original agentic audit and approval remain preserved, but
they no longer authorize the copied manual specification.
