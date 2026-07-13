# Natural-Language Requests

Phase 3B.1 accepts natural-language scaffold requests in the `Agentic Request`
GUI section.

Supported deterministic extraction includes:

- box dimensions such as `8 x 14 x 8 mm`
- cylinder diameter and height
- SC, BCC, FCC, HCP, gyroid, diamond, and primitive families
- pore/generating-sphere diameter
- TPMS unit-cell size
- porosity values and ranges
- open/interconnected pore language
- STL, STEP, and STP output requests
- preview/final resolution when explicitly stated

Examples are built into the GUI:

- Federica HCP case with hexagonal ambiguity and STEP/STP request
- explicit HCP spherical-pore scaffold
- gyroid TPMS scaffold
- cylindrical diamond TPMS scaffold
- ambiguous pore-size request
- unsupported STEP-only request

The parser proposes fields with confidence and evidence. It does not directly
modify the active specification.

When external providers are enabled, deterministic parsing still runs first.
The call policy avoids unnecessary external calls for complete, unambiguous
requests.
