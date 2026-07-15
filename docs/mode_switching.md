# Mode Switching

PGG has two top-level modes:

- Manual Design
- Agentic Design, Interpretation Stage

Only one mode is active at a time.

Switching from Agentic Design to Manual Design creates an editable copy of the
latest approved or proposed agentic specification. The prior approval audit is
preserved, but execution authorization is invalidated for the copy.

Switching from Manual Design to Agentic Design starts a new interpretation
workflow. The current manual specification may be used as read-only context, but
it is not automatically approved as agentic intent.

Mode switches are explicit actions. If a worker is running, the GUI asks before
cancelling and switching.
