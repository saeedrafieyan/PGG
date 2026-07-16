# Phase 3B.3 Baseline

Date: 2026-07-16

Branch: `feature/agentic-porous-gui`

Latest commits before implementation:

- `a933e03 Add engineering strategy planning Phase 3B.2`
- `0cfb87d Separate manual and agentic workflows Phase 3B.1.3`
- `350ac14 Use lightweight structured provider connection probe`
- `528229b Fix live provider connection activation`

Working tree was clean before Phase 3B.3 edits except for Git warnings about
the unreadable user-level ignore file at `C:\Users\Z32/.config/git/ignore`.

## Verification

All checks used the bundled desktop Python runtime.

```text
python -m compileall src\porous_designer
PASS

python -m pytest tests\unit -q
83 passed

python -m pytest tests\integration\test_agentic_phase_3b1.py tests\integration\test_phase_2b_generators.py tests\integration\test_strategy_phase_3b2.py -q
22 passed

python -m pytest tests\gui\test_phase_3a_gui.py -q
66 passed

python -m pytest tests\unit\test_specification.py::test_federica_legacy_spec_load -q
1 passed

python -m pytest tests\integration\test_agentic_phase_3b1.py::test_federica_request_parse_result -q
1 passed

python -m pytest tests\unit\test_provider_phase_3b1_1.py tests\unit\test_provider_phase_3b1_2.py -q
20 passed
```

Each pytest command emitted a cache warning because `.pytest_cache` could not be
updated in this checkout. The warning did not affect test results.

## Provider Status

```text
OPENAI_API_KEY_MISSING
GEMINI_API_KEY_MISSING
```

Live execution-provider wording tests are therefore expected to be reported as
`LIVE_EXECUTION_PROVIDER_TEST_NOT_RUN`.

## Baseline Screenshots

- `docs/phase_3b3_baseline_approved_specification.png`
- `docs/phase_3b3_baseline_blocked_preview_before_plan.png`
- `docs/phase_3b3_baseline_generated_strategy_plan.png`
- `docs/phase_3b3_baseline_approved_strategy_plan.png`

## Baseline Behavior

- Manual Design mode remains available without strategy-plan approval.
- Agentic Design mode parses requests and supports human-approved
  specifications.
- Strategy plans generate from approved specifications.
- Agentic Preview and Final are blocked before strategy-plan approval.
- Stale plans block execution.
- Phase 3B.2 does not yet provide a step-execution table, execution session
  model, validation gate mapping, or plan-step evidence export.
