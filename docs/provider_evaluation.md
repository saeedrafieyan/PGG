# Provider Evaluation

The benchmark contains 40 requests covering:

- explicit SC, BCC, FCC, HCP
- ambiguous hexagonal
- ambiguous pore size
- box and cylinder dimensions
- gyroid, diamond, primitive
- porosity ranges
- unsupported STEP/STP
- impossible or missing values
- mixed units
- prompt-injection attempts

Run deterministic evaluation:

```powershell
porous-designer evaluate-agent-provider --provider deterministic
```

Live provider evaluation is opt-in only and must use local credentials.

Current deterministic benchmark:

- cases: `40`
- external-call avoidance rate: `0.725`
- schema success rate: `1.0`
- exact field accuracy on ground-truth subset: `1.0`
- ambiguity recall: `1.0`
- unsupported-feature recall: `1.0`
- estimated cost: `0.0`
