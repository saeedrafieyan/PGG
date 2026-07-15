# Phase 3B.2 Baseline

Date: 2026-07-15

Branch: `feature/agentic-porous-gui`

Latest commits before implementation:

- `0cfb87d Separate manual and agentic workflows Phase 3B.1.3`
- `350ac14 Use lightweight structured provider connection probe`
- `528229b Fix live provider connection activation`
- `d043333 Add provider activation persistence Phase 3B.1.2`

Working tree was clean before Phase 3B.2 edits except for Git warnings about
the unreadable user-level ignore file at `C:\Users\Z32/.config/git/ignore`.

## Verification

All checks used the bundled Codex desktop Python runtime because `python` and
`pytest` were not on the shell PATH.

```text
python -m compileall src\porous_designer
PASS

python -m pytest tests\unit -q
72 passed

python -m pytest tests\integration\test_agentic_phase_3b1.py tests\integration\test_phase_2b_generators.py -q
14 passed

python -m pytest tests\gui\test_phase_3a_gui.py -q
54 passed

python -m pytest tests\unit\test_specification.py::test_federica_legacy_spec_load -q
1 passed

python -m pytest tests\integration\test_agentic_phase_3b1.py::test_federica_request_parse_result -q
1 passed

python -m pytest tests\unit\test_provider_phase_3b1_1.py tests\unit\test_provider_phase_3b1_2.py -q
20 passed
```

Each pytest command emitted a cache warning because `.pytest_cache` could not be
updated in this checkout. The warning did not affect test results.

## Baseline Behavior

- Manual Design mode was present and generation controls remained available for
  direct structured specifications.
- Agentic Design mode parsed deterministic requests and optional provider
  settings remained available.
- Human-approved agentic specifications were read-only in Agentic Design mode.
- Stale approval protection blocked Agentic Preview and Final.
- Provider settings and deterministic fallback tests passed.
- No Phase 3B.2 planning behavior existed yet.
