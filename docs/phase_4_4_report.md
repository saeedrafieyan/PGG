# Phase 4.4: simple interface (Describe -> Review -> Download)

## Goal

The Phase 3 GUI exposes every engineering parameter in one 1,289-line window
class. Phase 4.4 adds one UI-independent flow that the desktop app, a web page
and a JSON API all share, so a user can go from a sentence to a printable file
in three steps. The engineering window stays available as **Advanced mode**.

## Architecture

```
services/design_session.py   DesignSession: propose() -> approve() -> files()
                             proposal_card / result_card (plain JSON dicts)
                             write_design_report (self-contained HTML)
                             run_approved_snapshot (continue in another process)
api/server.py                Starlette app over DesignSession (+ static/index.html)
gui/simple_window.py         Qt window laying out the same cards
gui/workers/design_worker.py child-process worker (spawn-safe, like Phase 3A)
agentic/design_agent.py      propose() = Planner + Designer (no geometry)
                             execute() = Verifier + Repairer on an approved proposal
```

All logic lives in the service and agent layers. The front ends only
render the cards and forward the two checkpoints. The GUI keeps generation in a
child process: the approved proposal is passed as a picklable snapshot
(`DesignAgentResult.snapshot()` / `from_snapshot()`), so the child generates
exactly the design the user reviewed, including a proposal from an LLM
extraction.

## The three steps

1. **Describe**: a text box plus optional process and printer selectors.
   *Propose design* runs only the Planner and Designer and generates nothing.
2. **Review**: the proposal card shows:
   - one plain sentence ("A gyroid (sheet) box of 10 x 10 x 10 mm with 70 %
     porosity, pores about 0.84 mm, checked for generic_msla");
   - each value with its source (*from your request*, *from the literature*,
     *chosen by the designer*, *default*) and the reason;
   - the predicted walls, pores and openings (property tables);
   - the printer limits, the values that need confirmation, out-of-scope notes
     and the references.
   
   An infeasible request shows the numeric reason and the nearest feasible
   alternatives instead of an Approve button. *Approve and generate* is
   checkpoint 1.
3. **Download**: the result card shows the measured values against the targets,
   the printer checks (pass / warning / fail), any automatic repairs, and
   buttons for STL, 3MF and the design report (HTML). The desktop window also
   shows the 3D preview. Accepting the files is checkpoint 2.

## Web API

`porous-designer serve [--host 127.0.0.1] [--port 8765]`

| method | path | purpose |
|---|---|---|
| GET | `/` | one-page front end |
| GET | `/api/printers` | printer / process profiles |
| POST | `/api/sessions` `{text, process?, printer?}` | proposal card (nothing generated) |
| POST | `/api/sessions/{id}/approve` | start generation, returns `202` immediately |
| GET | `/api/sessions/{id}` | state, progress message, cards, file list |
| GET | `/api/sessions/{id}/files/{stl,3mf,step,report,trace}` | download |

One generation runs at a time (a single worker thread), since a Final run can
need several GB. The server binds to localhost and has no authentication. It
is a single-user local app until deployment, which is deferred. The web page
offers downloads but no in-browser 3D view: final meshes can have millions of
triangles.

## Tests

- `tests/unit/test_design_session_phase_4_4.py`:
  - a session round trip (the proposal records each value's source and
    citations, approve generates exactly once, and the report and trace
    exist);
  - an infeasible card with alternatives (approve refuses);
  - the web API end to end with Starlette's test client (proposal, approve,
    polling, report download, 409 on double approve, 400 on empty text).
- `tests/gui/test_simple_window_phase_4_4.py`: the window flow offscreen
  (Approve enabled only for a feasible proposal, downloads only after the
  result) and the infeasible card.

The tests use a synthetic property table and a fake generator; the real kernel
is exercised by `tests/integration/test_design_agent_kernel_phase_4_3.py`.

## How to try it

```powershell
porous-designer-gui                 # simple window
porous-designer-gui --advanced      # full engineering window
porous-designer serve               # then open http://127.0.0.1:8765
```
