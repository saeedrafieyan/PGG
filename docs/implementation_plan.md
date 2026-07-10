# Implementation Plan — Porous Structure Designer

## Phase 0 — Audit and baseline ✅

- [x] Inventory all scripts and outputs
- [x] Run `python porousgen.py sample_spec.txt` — 238 s, spacing 0.9858 mm, porosity 76.67% STL
- [x] Record STL/STEP metrics; identify STEP negative-volume issue
- [x] Initialize git, branch `feature/agentic-porous-gui`
- [x] Write `docs/current_system_audit.md`
- [x] Write `docs/proposed_architecture.md`
- [x] Write `docs/implementation_plan.md`

**Unresolved from Phase 0:** STEP B-Rep orientation validation; `.gitignore` for `__pycache__`.

---

## Phase 1 — Package skeleton, domain models, blackboard ✅

- [x] `pyproject.toml` with entry points `porous-designer` (CLI) and `porous-designer-gui`
- [x] `.gitignore`, `environment.yml`
- [x] `src/porous_designer/domain/` — `DesignSpecification`, enums, validation models
- [x] `src/porous_designer/blackboard/` — state, events, persistence, state machine
- [x] `src/porous_designer/domain/actions.py`, `run_state.py`
- [x] Structured logging setup
- [x] Unit tests: specification validation, blackboard transitions (10 passed)
- [x] Legacy spec loader adapter (`sample_spec.txt` → `DesignSpecification`)

**Exit criteria:** `pytest tests/unit` pass ✅

---

## Phase 2 — Deterministic generators and initial validation

- [ ] Extract lattice generators from `porousgen.py` with unit tests (SC, BCC, FCC, HCP)
- [ ] Add diamond, primitive TPMS SDF functions
- [ ] Box and cylinder domain clipping
- [ ] `porosity_solver.py` — bisection (ported from `tune()`)
- [ ] STL export pipeline
- [ ] Basic `ValidationReport` — porosity, bbox, watertight, components
- [ ] Integration test: Federica HCP (tuner rediscovers spacing)
- [ ] `configs/default.yaml`, example specs per family

**Exit criteria:** Federica regression porosity 75–80%, watertight STL, deterministic hash.

---

## Phase 3 — STEP backend and robust validation

- [ ] STEP exporter (gmsh, ported `build_step`)
- [ ] `step_validator.py` — reimport, volume sign, solid count, BRepCheck if available
- [ ] Connectivity validator (pore phase labeling, percolation)
- [ ] Thickness validator (distance transform, resolution-aware reporting)
- [ ] Throat estimator for sphere lattices
- [ ] Repair agent with allowed action list
- [ ] Inner/outer bounded loops in orchestration

**Exit criteria:** STEP validation reports `partially_validated` or `valid` with documented method; repair bounded.

---

## Phase 4 — Agent interfaces

- [ ] `LLMProvider` protocol + `NullLLMProvider` + optional OpenAI-compatible adapter
- [ ] `RequestParserAgent` — regex/heuristic parser (no LLM required for Federica case)
- [ ] `AmbiguityAgent` — structured alternatives for hexagonal packing, porosity terms
- [ ] `FeasibilityAgent` — deterministic rules (pore count, memory estimate, overlap)
- [ ] `StrategyAgent` — generator/backend selection
- [ ] `ReportAgent` — template-based HTML report

**Exit criteria:** Federica NL request parses correctly; ambiguities shown; structured-only mode works.

---

## Phase 5 — PySide6 GUI

- [ ] `main_window.py` multi-panel layout
- [ ] Request, specification, ambiguity, feasibility, preview, progress, validation, history panels
- [ ] `workers.py` — background generation with cancel
- [ ] PyVistaQt 3D preview with clipping planes
- [ ] pytest-qt smoke tests

**Exit criteria:** GUI launches; preview + final generation without freeze; cancel works.

---

## Phase 6 — Reporting, history, packaging

- [ ] HTML report with all required sections
- [ ] SQLite run history
- [ ] `docs/architecture.md`, `user_guide.md`, `validation_methods.md`
- [ ] `CHANGELOG.md`, final implementation report
- [ ] Windows `start_gui.bat`
- [ ] Full test suite green

**Exit criteria:** All 22 acceptance criteria from spec section 27.

---

## Commit strategy

One commit per completed phase on `feature/agentic-porous-gui`.

## Risk register

| Risk | Mitigation |
|------|------------|
| STEP negative volume | BRepCheck + volume sign gate; disable STEP export on failure |
| Python 3.14 instability | Document 3.12 env; test both |
| Large mesh GUI perf | Display mesh decimation separate from export mesh |
| LLM schema failures | Null provider default; one retry then fallback |
