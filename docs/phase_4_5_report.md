# Phase 4.5: AGE-Bench

## Purpose

AGE-Bench measures what the paper claims: that a request in plain language
becomes a printable part whose numbers are **measured, not asserted**, and
that the system does not invent values. It compares AGE with its own
ablations and with language-model-only baselines on the same prompts and the
same measurements.

## Prompt set (`bench/data/age_bench_v1.jsonl`, 470 prompts)

The prompts come from seeded templates (`bench/prompts.py`, seed 2026), so the
set is reproducible and every stated value is known exactly.

| tier | n | content | ground truth |
|---|---|---|---|
| 1 explicit | 150 | family, part, porosity (single or range), cell or pore size, formats | all stated values |
| 2 partial | 80 | one or more of family / porosity / length left open | stated values; the open ones are *forbidden* as user values |
| 3 application | 60 | lay or clinical wording ("bone graft for a rabbit femur defect", "chronic wound") | part size, process, application; porosity/pore must not be attributed to the user |
| 4 constrained | 60 | minimum walls or openings, printer, relative stiffness, permeability | stated values |
| 5 infeasible | 48 | FDM with 0.1-0.2 mm pores, cell larger than the part, part larger than the volumetric vial, 1 mm walls with 0.3 mm pores at 85 %, 97-99 % porosity, 0.05 mm pores on resin | stated values; **must be reported infeasible** |
| 6 out of scope | 32 | scan-to-part, topology optimisation, multi-material, degradation, conduction, drug release | **must be flagged** |
| 7 paraphrase | 40 | held-out everyday wording ("a puck 12 mm across", "only 30 % solid material", "repeating every 2 mm") | stated values |

Tiers 1-6 use wording that the deterministic parser was developed with. Tier 7
was written afterwards and **the parser was not tuned on it**. It measures how
rule-based planning degrades on unfamiliar wording, which is where grounded LLM
extraction should help.

## Systems

| system | planner | designer / feasibility | verifier + repair |
|---|---|---|---|
| `age` | deterministic parser + knowledge base | property tables | yes (<= 3 iterations) |
| `age_llm:<model>` | grounded OpenRouter extraction + knowledge base | property tables | yes |
| `age_no_knowledge` | deterministic, no literature presets | property tables | yes |
| `age_no_feasibility` | deterministic + knowledge | none (fixed defaults) | no |
| `age_no_verifier` | deterministic + knowledge | property tables | one generation, no repair |
| `llm_direct:<model>` | the LLM returns all parameters, a list of which were stated, and a feasibility verdict | none | no (AGE's kernel builds and measures the result) |
| `llm_code:<model>` | the LLM writes `field(x, y, z)` (zero-shot code) | none | no (AGE measures the voxels) |

`llm_code` runs the model's code only with `--allow-llm-code`, in a separate
isolated Python process with a timeout, after a static whitelist check:

- the only import allowed is numpy, and only numpy's math functions (no I/O,
  no `ctypeslib`);
- no dunder names or attributes, and no `open` / `eval` / `exec`.

## Metrics (`bench/metrics.py`)

- **Extraction**:
  - field accuracy: stated values recovered;
  - exact match: a prompt with nothing wrong, missing or invented;
  - **invented-value rate** (hallucination): prompts where a value is
    attributed to the user that the request does not contain;
  - application accuracy (tier 3);
  - out-of-scope flagged (tier 6).
- **Feasibility** (propose mode, labelled prompts):
  - accuracy;
  - infeasible requests detected;
  - feasible requests wrongly refused.
- **Result** (full mode):
  - constraint satisfaction: delivered with no failed check;
  - porosity absolute error;
  - median-pore relative error;
  - printability pass rate: every `print_*` check passes;
  - iterations;
  - time;
  - user effort: two checkpoints plus the number of values to confirm.

## Running

```powershell
porous-designer bench build
porous-designer bench run --system age --mode propose                      # all 470, seconds
porous-designer bench run --system age --mode full --tiers 1,2,3,4,5 --per-tier 4
porous-designer bench run --system age_no_feasibility --mode full --tiers 1,2,3,4,5 --per-tier 4
porous-designer bench run --system "age_llm:qwen/qwen3.8-27b:free" --mode extract --per-tier 5
porous-designer bench run --system "llm_direct:qwen/qwen3.8-27b:free" --mode propose --per-tier 5
porous-designer bench run --system "llm_code:qwen/qwen3.8-27b:free" --mode full --per-tier 3 --allow-llm-code
porous-designer bench report --by-tier
```

Runs resume by default. Free OpenRouter models allow about 50 requests a day,
so LLM systems are run in slices (`--tiers`, `--per-tier`, `--limit`). Full
mode caps each generation at `--voxel-budget` grid points (8 M by default in
full mode, against the agent's usual 60 M) so a benchmark slice finishes in
minutes. This coarsens the resolution the
designer would choose and is the same for every system.

## Results

All numbers below are from runs on 2026-09-25 (RTX 5070 Ti), reproduced
with the commands above. Row files are in `runs/bench/`.

### Planning and feasibility on all 470 prompts (`age`, propose mode)

| tier | n | field accuracy | exact match | invented values | other |
|---|---|---|---|---|---|
| 1 explicit | 150 | 100 % | 100 % | 0 % | feasibility 99 % (1 FCC case needs a finer grid than the 60 M-point budget) |
| 2 partial | 80 | 100 % | 100 % | 0 % | feasibility 100 % |
| 3 application | 60 | 100 % | 100 % | 0 % | application recognised 100 % |
| 4 constrained | 60 | 100 % | 100 % | 0 % | |
| 5 infeasible | 48 | 100 % | 100 % | 0 % | **infeasible detected 100 %** |
| 6 out of scope | 32 | 100 % | 100 % | 0 % | **flagged 100 %** |
| 7 paraphrase (held out) | 40 | **31 %** | 0 % | 0 % | |
| all | 470 | 93 % | 91 % | 0 % | feasibility 99.5 %, false refusals 0.6 % |

- **No values were invented.** No prompt had a value attributed to the user that
  it does not contain. This is by construction: every stated value must quote
  the request, and everything else is labelled literature, designer or default.
- **Tiers 1-6 are at 100 % because of the templates** (see Limitations).
- **Tier 7 is the honest measure of the rule-based planner**: it recovers
  31 % of the stated values from unfamiliar wording ("a puck 12 mm across",
  "only 30 % solid material"). It does not guess the rest; the Designer asks
  for confirmation of the defaults (effort 5.0 against 2.2-3.4 elsewhere).
- **Planning is fast**: about 10 ms per prompt, generation not included.

### Complete runs (`full` mode, first 4 prompts of tiers 1-5, 8 M-point cap per part)

| system | feasibility | impossible delivered | constraints met | porosity error | pore error | printable | iterations | median time |
|---|---|---|---|---|---|---|---|---|
| `age` | 90 % | **0 %** | **100 %** (12/12) | 0.003 | 1.6 % | 100 % | 1.0 | 8.6 s |
| `age_no_verifier` | 90 % | 0 % | 100 % | 0.003 | 1.6 % | 100 % | 1.0 | 8.6 s |
| `age_no_feasibility` | 60 % | **75 %** | 70 % | 0.052 | 507 % | 0 % | 1.0 | 47.8 s |

- **Porosity error** is the absolute difference between measured and target
  porosity. **Pore error** is the relative error of the measured median pore
  against its target.
- **Printable** is the share of runs with a named printer in which every
  printability check passed. Advisory checks (recommended wall, file size) are
  not counted.
- **Without the feasibility check**, three quarters of the impossible requests
  were delivered as a mesh anyway, for example a 7 mm cell in a 5 mm cube.
  Such a mesh passes geometric validation but does not answer the request.
  Among the other requests, 30 % failed their own checks (walls below the
  requested minimum, closed pores, porosity missed on the grid). Median pore
  sizes were off by a factor of five, because a fixed 2 mm cell ignores the
  pore target.
- **The Verifier-Repairer loop was not needed on this slice.** The
  table-based Designer met every check at the first attempt, so AGE and
  `age_no_verifier` are identical here. The loop is exercised in the unit
  tests and by requests where the periodic tables are less exact (small parts
  with few cells, skins, grading, mesh domains). A benchmark slice aimed at
  those is future work.
- **Prediction against measurement** (the 12 generated AGE parts): the
  tables predicted wall d10 to within a median of 2.3 % (maximum 18 %) and
  the median pore to within 2.3 % (maximum 4 %). Throat predictions are
  looser. For the random Voronoi foam the part's percolation diameter was
  0.30 mm against 1.58 mm predicted: a small random part is not its periodic
  cell. The Verifier reports this.
- **False refusals (17 % of the labelled feasible prompts in this slice):**
  both are sphere packings that the 8 M-point benchmark cap cannot resolve.
  At the default 60 M budget only one of them remains (propose mode above).

### LLM systems (pilot)

- **Bug found:** the first grounded-extraction pilot showed that every
  OpenRouter call was failing and silently falling back to the deterministic
  parser. The cause was a gzip double-decoding bug, fixed in commit 54086cd.
  Rows now record `parser.provider_failed`, and fallbacks are reported as
  `provider_failed`, not scored as LLM results.
- **`age_llm:qwen/qwen3.8-27b:free`, 12 prompts from tiers 5-7:**
  - 11 answered (1 provider timeout);
  - field accuracy 98 %, invented values 0 %, out-of-scope flagged 100 %;
  - on the held-out wording it recovered values the rules miss ("a puck
    12 mm across" as a cylinder [12, 4] mm, "repeating every 2 mm" as the
    cell size);
  - it rejected "only 30 % solid" because the stated value (0.7) is not
    written in the request. This is the grounding rule working as intended.
- **`llm_direct`:** both free models were rate-limited or overloaded upstream
  during the session, so only 2 of the 12 prompts were answered, both by
  Nemotron. One judged "gyroid, 85 % porosity, 0.1 mm pores on an FDM
  printer" to be *feasible*; it is not (walls of about 0.02 mm against a
  0.45 mm nozzle line).
- **Still to run:** the full model comparison (`age_llm`, `llm_direct` and
  `llm_code` on several free models) is left for the user. It needs several
  days of the free-tier quota (about 50 requests a day). Runs resume and
  retry failed rows automatically.

## Physical validation (by the user)

The measurements are on the digital geometry. The planned physical study is:

- print the coupon (`make-coupon`) and a benchmark subset on the FDM, SLA and
  volumetric printers;
- measure the prints (calipers or microscope, µCT if available);
- calibrate the profiles (`calibrate`);
- compare printed against designed values.

The measurement sheets are the coupon CSVs.

## Limitations

- The ground truth comes from the templates, so tiers 1-6 measure consistency
  with the controlled vocabulary more than language understanding. Tier 7 and
  the LLM systems address that; paraphrases written by other people would
  make the set stronger.
- Feasibility labels exist only where physics decides (tier 5 impossible,
  tiers 1-2 comfortably possible).
- LLM results depend on the free models available on the day; the model id is
  recorded in each row.
