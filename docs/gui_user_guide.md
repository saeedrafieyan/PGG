# GUI User Guide

Launch PGG with:

```powershell
python -m porous_designer.gui.app
```

or on Windows:

```powershell
launch_pgg_gui.bat
```

For runtime diagnostics:

```powershell
python -m porous_designer.gui.app --debug-gui
launch_pgg_gui.bat --debug-gui
```

Debug logs are written under `logs/`. The toolbar `Diagnostics` action opens
runtime and rendering diagnostics, including GPU/OpenGL details.

## Basic Workflow

1. Choose `Manual Design` or `Agentic Design`.
2. In Manual Design, set the output name and output folder.
3. Choose a box or cylinder domain.
4. Choose a structure family.
5. Enter the relevant geometric fields.
6. Set target porosity and tolerance.
7. Choose preview/final resolutions.
8. Click `Estimate`.
9. Click `Generate Preview`.
10. Inspect the preview mesh.
11. Click `Generate Final` when the estimate is acceptable.
12. Review validation results.
13. Export the HTML report.

Manual Design and Agentic Design are separate workflows. Manual fields are not
editable in Agentic Design.

## Agentic Request

Agentic Design is agent-assisted, not autonomous. It includes:

- natural-language request text area
- `Parse Request`
- `Clear`
- `Load Example`
- parser mode and provider status
- provider mode, credential status, last decision, and last execution
- `Configure`
- `Test`
- `Interpret with External Model`
- `Use Deterministic Only`
- extracted-field confidence summary
- unresolved ambiguity count
- `Review Proposed Specification`

Parsing does not change the Manual Design draft. Approval requires the review
dialog. After approval, the GUI shows a read-only approved specification summary
and waits for explicit Estimate, Preview, or Final actions.

## Agent Provider Settings

`Agent Provider Settings` controls optional external interpretation providers.
The default is deterministic-only with external access disabled. OpenAI and
Gemini providers are optional and require local credentials. API keys are stored
only through environment variables, the operating-system credential manager, or
session-only memory.

The API-key field is blank after reopening by design. Check the credential
status row for `Available` or `Not found`.

Use `Interpret with External Model` to force the selected provider path for a
request. This still runs deterministic extraction first, requires human review,
and never starts geometry generation.

## Rendering Presets

The preview panel includes:

- Scientific
- High Contrast
- Light Background
- Wireframe
- Surface + Edges

Use `Scientific` for normal inspection and `Light Background` for publication
screenshots. These settings affect display only.

## Preview Policy

Before a mesh is loaded, the preview status reads:

`No preview loaded`

After preview generation, the preview panel labels meshes with a compact status
row:

`PREVIEW | Not final validation | <preset> | <filename>`

When a final artifact is explicitly opened from run history, the status uses:

`FINAL ARTIFACT VIEW | Validation status: <status> | <filename>`

Preview metrics are approximate and cannot be accepted as final scientific
results.

## Rendering Diagnostics

Detailed renderer settings, OpenGL vendor/renderer/version, package versions,
and OpenGL extensions are available through `Diagnostics > Rendering`.

OpenGL extensions are collapsed by default. Use `Copy Rendering Diagnostics` or
`Save Diagnostics` when filing a rendering issue.

Provider activation details are available through `Diagnostics > Agent
Provider`. Use `Copy Provider Diagnostics` when filing provider issues; secrets
are redacted.

## Large Final Meshes

The GUI does not automatically load large final STLs. Use run history or output
folders to explicitly inspect final artifacts.

## Disabled Features

STEP, FEA, inverse design, cloud deployment, authentication, arbitrary CAD code
generation, and autonomous geometry generation are disabled in Phase 3B.1.2.
