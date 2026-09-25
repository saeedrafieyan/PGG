"""AGE-Bench (Phase 4.5): tiered design prompts with ground truth, a runner and metrics.

* ``prompts``  - builds the prompt set (``data/age_bench_v1.jsonl``) from
  seeded templates: explicit, partial, application/lay, constrained,
  infeasible and out-of-scope requests, each with the values it states,
  the values it must *not* be given, and (where decidable) feasibility.
* ``runner``   - runs a system (AGE, its ablations, or LLM-only baselines) in
  ``extract``, ``propose`` or ``full`` mode and writes one JSON row per prompt.
* ``metrics``  - aggregates rows into the tables of the paper.
"""
