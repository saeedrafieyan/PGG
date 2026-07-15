# Phase 3B.1.3 Baseline

Date: 2026-07-15

Branch:

```text
feature/agentic-porous-gui
```

Latest provider commits:

```text
350ac14 Use lightweight structured provider connection probe
528229b Fix live provider connection activation
d043333 Add provider activation persistence Phase 3B.1.2
```

Working tree:

```text
clean before implementation
```

Current architecture before Phase 3B.1.3:

- MainWindow always constructs both manual panels and the Agentic Request panel in the same left-column workflow.
- Manual field widgets remain editable after agentic approval.
- Agentic approval writes approved values back into the same editable manual widgets through `_apply_specification_to_panels`.
- `ApplicationController` owns one active `StateStore.specification` and all generation actions read that same object.
- `AgenticRequestOrchestrator` owns `last_result`, `last_proposal`, and `last_approval`, but there is no top-level application mode.
- Provider settings persist through `ProviderSettings` and QSettings with explicit external-call modes.
- External-call modes before this phase: deterministic only, external when recommended, always external.

Baseline verification:

```text
pytest tests\unit -q
72 passed

pytest tests\integration\test_agentic_phase_3b1.py tests\integration\test_phase_2b_generators.py -q
14 passed

pytest tests\gui\test_phase_3a_gui.py -q
48 passed

pytest tests\integration\test_agentic_phase_3b1.py::test_federica_request_parse_result -q
1 passed

pytest tests\unit\test_provider_phase_3b1_1.py tests\unit\test_provider_phase_3b1_2.py -q
20 passed
```

Observed risk to fix:

- Manual and agentic workflows are visually and behaviorally mixed.
- Manual edits can mark an approval stale, but the form remains active in the same workflow.
- Generation controls do not yet distinguish manual authorization from agentic approval authorization.
- Run metadata does not yet record application mode, specification origin, or approval revision.

Live provider status:

```text
LIVE_PROVIDER_TEST_NOT_RUN
```

Reason: no local API key was provided to Codex for this baseline run.
