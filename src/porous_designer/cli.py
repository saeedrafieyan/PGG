"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import trimesh

from porous_designer import __version__
from porous_designer.domain.specification import DesignSpecification, load_legacy_spec
from porous_designer.agentic.evaluation import evaluate_deterministic
from porous_designer.logging_config import configure_logging, get_logger
from porous_designer.paths import runs_dir
from porous_designer.services.generation_service import GenerationProfile, generate_porous_stl
from porous_designer.services.mesh_optimization import OptimizationProfile, optimize_and_validate_mesh
from porous_designer.services.mesh_optimization import validate_optimization_pair
from porous_designer.services.phase_2c import (
    cylinder_accuracy_study,
    determinism_study,
    preview_final_consistency,
    profile_generation,
)
from porous_designer.services.resource_estimation import estimate_resources
from porous_designer.services.sensitivity_service import run_resolution_sensitivity
from porous_designer.services.validation_service import validate_standalone_stl


def _load_spec(path: Path, as_yaml: bool) -> DesignSpecification:
    if as_yaml or path.suffix in (".yaml", ".yml"):
        return DesignSpecification.from_yaml_file(path)
    return load_legacy_spec(path)


def cmd_generate(args: argparse.Namespace) -> int:
    log = get_logger("cli.generate")
    spec_path = Path(args.spec)
    if not spec_path.exists():
        log.error("spec_not_found", path=str(spec_path))
        return 1

    try:
        spec = _load_spec(spec_path, args.yaml)
    except Exception as exc:
        log.error("spec_load_failed", error=str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    profile = GenerationProfile.PREVIEW if args.preview else GenerationProfile(args.profile)
    result = generate_porous_stl(
        spec,
        profile=profile,
        optimization_profile=OptimizationProfile(args.optimization),
    )

    print(f"Porous Structure Designer v{__version__} - generate ({profile.value})")
    print(f"  Run ID:              {result.run_id}")
    print(f"  Status:              {'PASSED' if result.success else 'FAILED'}")
    print(f"  Family:              {spec.structure.family.value}  domain: {spec.domain.shape.value}")
    print(f"  Control parameter:   {result.control_parameter_name} = {result.lattice_spacing_mm:.5f}")
    print(f"  Tuning-grid porosity:{result.tuning_grid_porosity * 100:.2f}%")
    print(f"  Final voxel porosity:{result.final_voxel_porosity * 100:.2f}%")
    print(f"  Final mesh porosity: {result.final_mesh_porosity * 100:.2f}%")
    print(f"  Triangles:           {result.triangle_count}")
    print(f"  Watertight:          {result.watertight}")
    print(f"  Solid components:    {result.solid_components}")
    print(f"  STL:                 {result.stl_path}")
    if result.threemf_path:
        print(f"  3MF:                 {result.threemf_path}")
    for fmt, status in (result.export_status or {}).items():
        if fmt != "stl":
            print(f"  Export {fmt}:{' ' * max(1, 13 - len(fmt))}{status}")
    if result.step_path:
        print(f"  STEP:                {result.step_path}")
    labels = {
        "pore_d50_mm": ("Pore size (median)", "mm"),
        "wall_d50_mm": ("Wall thickness (median)", "mm"),
        "wall_min_mm": ("Wall thickness (thin 10%)", "mm"),
        "percolation_diameter_mm": ("Largest passing sphere", "mm"),
        "closed_void_fraction": ("Closed pore fraction", ""),
        "specific_surface_per_mm": ("Specific surface", "1/mm"),
        "tortuosity": ("Tortuosity", ""),
        "permeability_m2": ("Permeability", "m^2"),
        "youngs_relative": ("Stiffness E*/Es (min)", ""),
    }
    for key, value in (result.measurements or {}).items():
        name, unit = labels.get(key, (key, ""))
        text = f"{value:.3e}" if key == "permeability_m2" else f"{value:.4g}"
        print(f"  {name + ':':26s}{text} {unit}".rstrip())
    if result.printability:
        bad = [c for c in result.printability["checks"] if c["status"] != "pass"]
        print(f"  Printability ({result.printability['profile_id']}): {'OK' if not bad else str(len(bad)) + ' issue(s)'}")
        for c in bad:
            print(f"    - {c['name']}: {c['message']}")
    if result.optimization:
        print(f"  Optimization:        {result.optimization.profile.value} ({result.optimization.reason})")
        print(f"  Recommended STL:     {result.optimization.recommended_path}")
    print(f"  Timing (s):          total={result.timing.total_s:.1f}  "
          f"tune={result.timing.tuning_s:.1f}  voxel={result.timing.voxel_generation_s:.1f}  "
          f"mc={result.timing.marching_cubes_s:.1f}  val={result.timing.validation_s:.1f}")
    print(f"  Peak memory:         {result.peak_memory_mb:.1f} MB")
    for msg in result.messages:
        print(f"  NOTE: {msg}")
    if result.tuning and not result.tuning.converged:
        print(f"  WARNING: {result.tuning.message}")

    return 0 if result.success else 1


def cmd_estimate(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    spec = _load_spec(spec_path, args.yaml)
    profile = GenerationProfile(args.profile)
    resolution = (
        spec.generation.preview_resolution_mm
        if profile == GenerationProfile.PREVIEW
        else spec.generation.reference_resolution_mm
        if profile == GenerationProfile.REFERENCE
        else spec.generation.final_resolution_mm
    )
    estimate = estimate_resources(spec, resolution)
    print(json.dumps(estimate.to_dict(), indent=2))
    return 1 if estimate.status.value == "infeasible" else 0


def cmd_sensitivity(args: argparse.Namespace) -> int:
    spec = _load_spec(Path(args.spec), args.yaml)
    resolutions = [float(x) for x in args.resolutions.split(",")]
    result = run_resolution_sensitivity(spec, resolutions=resolutions)
    print(f"Sensitivity written to {result.output_dir}")
    for key, value in result.status.items():
        print(f"  {key}: {value}")
    return 0 if result.rows else 1


def cmd_optimize_mesh(args: argparse.Namespace) -> int:
    path = Path(args.stl)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1
    mesh = trimesh.load(path, force="mesh")
    optimized = path.with_name(path.stem + f"_{args.profile}.stl")
    result, _export = optimize_and_validate_mesh(
        mesh,
        master_path=path,
        optimized_path=optimized,
        domain_volume_mm3=float(args.domain_volume) if args.domain_volume else abs(float(mesh.volume)),
        profile=OptimizationProfile(args.profile),
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.accepted or result.profile == OptimizationProfile.NONE else 1


def cmd_validate_optimization(args: argparse.Namespace) -> int:
    result = validate_optimization_pair(
        Path(args.master),
        Path(args.candidate),
        domain_volume_mm3=float(args.domain_volume),
    )
    print(json.dumps(result, indent=2))
    return 0 if result["accepted"] else 1


def cmd_determinism(args: argparse.Namespace) -> int:
    spec = _load_spec(Path(args.spec), args.yaml)
    result = determinism_study(spec, runs=args.runs)
    print(json.dumps(result, indent=2))
    return 0 if result["classification"] in {"bitwise deterministic", "numerically deterministic"} else 1


def cmd_profile(args: argparse.Namespace) -> int:
    spec = _load_spec(Path(args.spec), args.yaml)
    result = profile_generation(spec, profile=GenerationProfile(args.profile))
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


def cmd_preview_consistency(args: argparse.Namespace) -> int:
    spec = _load_spec(Path(args.spec), args.yaml)
    result = preview_final_consistency(spec)
    print(json.dumps(result, indent=2))
    return 0


def cmd_cylinder_accuracy(args: argparse.Namespace) -> int:
    result = cylinder_accuracy_study(
        diameter_mm=args.diameter,
        height_mm=args.height,
        resolutions=[float(x) for x in args.resolutions.split(",")],
        output_dir=Path(args.output),
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.stl)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1
    dims = None
    if args.dims:
        dims = [float(x) for x in args.dims.split(",")]
    report = validate_standalone_stl(str(path), expected_dims=dims)
    print(f"Validation: {report.overall_status.value}")
    for check in report.checks:
        print(
            f"  [{check.status.value:12}] {check.name}: "
            f"requested={check.requested_value} achieved={check.achieved_value} "
            f"{check.message}"
        )
    return 0 if report.passed else 1


def cmd_inspect_run(args: argparse.Namespace) -> int:
    run_path = Path(args.run_dir)
    bb_path = run_path / "blackboard.json"
    if not bb_path.exists():
        print(f"ERROR: no blackboard at {bb_path}", file=sys.stderr)
        return 1
    print(json.dumps(json.loads(bb_path.read_text(encoding="utf-8")), indent=2)[:4000])
    timing_path = run_path / "timing.json"
    if timing_path.exists():
        print("\n--- timing ---")
        print(timing_path.read_text(encoding="utf-8"))
    val_path = run_path / "validation_report.json"
    if val_path.exists():
        data = json.loads(val_path.read_text(encoding="utf-8"))
        print(f"\n--- validation: {data.get('overall_status')} ---")
        for c in data.get("checks", [])[:15]:
            print(f"  {c['name']}: {c['status']} ({c.get('achieved_value')})")
    return 0


def cmd_evaluate_agent_provider(args: argparse.Namespace) -> int:
    output = args.output or str(runs_dir() / "agentic" / f"provider_evaluation_{args.provider}.json")
    if args.provider == "deterministic":
        metrics = evaluate_deterministic(output)
        print(json.dumps({k: v for k, v in metrics.items() if k != "rows"}, indent=2))
        return 0
    from porous_designer.agentic.contracts import ProviderMode
    from porous_designer.agentic.evaluation import evaluate_live_provider, live_extraction_cases
    from porous_designer.agentic.provider import OpenRouterProvider
    from porous_designer.agentic.provider_config import CredentialMode, ExternalCallMode, ProviderSettings

    settings = ProviderSettings(
        external_access_enabled=True,
        provider_mode=ProviderMode.OPENROUTER,
        external_call_mode=ExternalCallMode.ALWAYS,
        credential_mode=CredentialMode(args.credential_mode),
        allow_provider_data_collection=args.allow_data_collection,
    )
    if args.model:
        settings.openrouter_model = args.model
    if args.no_fallback:
        settings.openrouter_fallback_models = []
    cases = live_extraction_cases()
    if args.cases:
        wanted = {c.strip() for c in args.cases.split(",") if c.strip()}
        cases = [c for c in cases if c.identifier in wanted]
    if args.limit:
        cases = cases[: args.limit]
    print(f"Running {len(cases)} live extraction cases on {settings.model_chain()} (each case uses at least one free-tier request).", file=sys.stderr)
    metrics = evaluate_live_provider(OpenRouterProvider(settings), cases, output=output)
    print(json.dumps({k: v for k, v in metrics.items() if k != "rows"}, indent=2))
    for row in metrics["rows"]:
        flags = []
        if row.get("status") != "ok":
            flags.append(f"FAILED: {row.get('error')}")
        if row.get("accepted_wrong"):
            flags.append(f"WRONG {row['accepted_wrong']}")
        if row.get("accepted_forbidden"):
            flags.append(f"HALLUCINATED {row['accepted_forbidden']}")
        if row.get("missing"):
            flags.append(f"missing {row['missing']}")
        if row.get("rejected_values"):
            flags.append(f"caught {len(row['rejected_values'])}")
        print(f"  {row['id']:28s} {'; '.join(flags) or 'ok'}")
    print(f"Full results: {output}", file=sys.stderr)
    return 0 if metrics["failed_calls"] == 0 and metrics["accepted_wrong"] == 0 and metrics["accepted_forbidden"] == 0 else 1


def cmd_credentials(args: argparse.Namespace) -> int:
    import getpass

    from porous_designer.agentic.credentials import ENVIRONMENT_VARIABLES, delete_api_key, lookup_api_key, store_api_key
    from porous_designer.agentic.provider_config import CredentialMode

    provider = args.provider
    if args.action == "set":
        # The key is read without echo and goes straight to the OS credential
        # store; it is never written to settings, logs, or run folders.
        key = getpass.getpass(f"{provider} API key (input hidden): ").strip()
        if not key:
            print("No key entered; nothing stored.", file=sys.stderr)
            return 1
        store_api_key(provider, key)
        found = lookup_api_key(provider, CredentialMode.KEYRING)
        print(f"Stored in the OS credential store ({found.backend}); fingerprint {found.redacted_display}.")
        return 0
    if args.action == "delete":
        try:
            delete_api_key(provider)
        except Exception as exc:
            print(f"Delete failed: {exc}", file=sys.stderr)
            return 1
        print("Stored key deleted.")
        return 0
    stored = lookup_api_key(provider, CredentialMode.KEYRING)
    env = lookup_api_key(provider, CredentialMode.ENVIRONMENT)
    print(f"Credential store: {'available ' + stored.redacted_display if stored.available else 'not found'} ({stored.backend or stored.message})")
    print(f"Environment {ENVIRONMENT_VARIABLES.get(provider, provider.upper() + '_API_KEY')}: {'available ' + env.redacted_display if env.available else 'not set'}")
    return 0


def cmd_openrouter_models(args: argparse.Namespace) -> int:
    from porous_designer.agentic.openrouter import ModelCatalog, OpenRouterClient
    from porous_designer.agentic.provider_config import OPENROUTER_DEFAULT_FALLBACK_MODELS, OPENROUTER_DEFAULT_MODEL

    catalog = ModelCatalog(OpenRouterClient(None, timeout_s=30.0), cache_path=runs_dir() / ".cache" / "openrouter_models.json", ttl_s=0.0)
    models = catalog.free_structured_models()
    if catalog.last_error:
        print(f"Catalog unavailable: {catalog.last_error}", file=sys.stderr)
        return 1
    defaults = {OPENROUTER_DEFAULT_MODEL, *OPENROUTER_DEFAULT_FALLBACK_MODELS}
    print(f"Free OpenRouter models with strict structured output ({len(models)}):")
    for caps in models:
        marks = ["seed" if caps.supports("seed") else "no-seed"]
        if caps.model_id in defaults:
            marks.append("AGE default chain")
        print(f"  {caps.model_id:55s} ctx={caps.context_length}  {', '.join(marks)}")
    missing = sorted(m for m in defaults if catalog.is_listed(m) is False)
    if missing:
        print(f"Default models no longer listed: {missing}", file=sys.stderr)
    return 0


def cmd_printers(args: argparse.Namespace) -> int:
    from porous_designer.printability.profiles import all_profiles, user_profile_dir

    for pid, prof in sorted(all_profiles().items()):
        tag = " [calibrated]" if prof.calibrated else ""
        print(f"{pid:34s} {prof.process:12s} wall >= {prof.min_wall_mm} mm, hole >= {prof.min_hole_mm} mm{tag}")
    print(f"User profiles: {user_profile_dir()}")
    return 0


def cmd_make_coupon(args: argparse.Namespace) -> int:
    from porous_designer.printability.coupon import make_coupon, write_coupon
    from porous_designer.printability.profiles import get_profile

    profile = get_profile(args.profile)
    files = write_coupon(make_coupon(profile), args.output, profile)
    print(f"Calibration coupon for {profile.display_name or profile.id}:")
    for key, path in files.items():
        print(f"  {key:8s} {path}")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    from porous_designer.printability.coupon import calibrate_profile
    from porous_designer.printability.profiles import get_profile, user_profile_dir

    profile = calibrate_profile(get_profile(args.profile), args.measurements, args.name)
    print(f"Calibrated profile '{profile.id}' saved to {user_profile_dir() / (profile.id + '.yaml')}")
    print(f"  min wall {profile.min_wall_mm} mm, min hole {profile.min_hole_mm} mm, min gap {profile.min_gap_mm} mm")
    print(f"  use it with manufacturing.printer_profile: {profile.id}")
    return 0


def cmd_families(args: argparse.Namespace) -> int:
    """List every structure family with the parameter that defines it."""
    from porous_designer.domain.enums import StructureFamily

    groups = (
        ("Sphere-pore lattices (pore_diameter_mm; porosity tuned by lattice spacing)", lambda f: f.is_sphere_lattice),
        ("TPMS, sheet or network (unit_cell_size_mm; tpms_variant; porosity tuned by wall thickness/offset)", lambda f: f.is_tpms),
        ("Strut lattices (unit_cell_size_mm; porosity tuned by strut diameter)", lambda f: f.is_strut_lattice),
        ("Stochastic foam (unit_cell_size_mm = mean seed spacing; voronoi_randomness)", lambda f: f.is_stochastic),
    )
    for title, member in groups:
        print(title)
        for family in StructureFamily:
            if member(family):
                print(f"  {family.value}")
    print("Domains: box [X,Y,Z], cylinder [diameter,height], sphere [diameter], mesh (closed STL/OBJ/PLY/3MF via domain.mesh_path)")
    print("Exports: stl, 3mf, step (faceted solid)")
    return 0


def cmd_make_phantom(args: argparse.Namespace) -> int:
    from porous_designer.geometry.phantoms import wound_cavity_phantom

    mesh = wound_cavity_phantom(args.length, args.width, args.depth, irregularity=args.irregularity, seed=args.seed)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(out)
    ext = mesh.extents
    print(f"Wound-cavity phantom written to {out}")
    print(f"  extents {ext[0]:.2f} x {ext[1]:.2f} x {ext[2]:.2f} mm, volume {mesh.volume:.1f} mm3, watertight {mesh.is_watertight}, {len(mesh.faces)} triangles")
    return 0


def cmd_build_property_tables(args: argparse.Namespace) -> int:
    from porous_designer.knowledge.property_tables import DATA_FILE, build_tables

    path = Path(args.output) if args.output else DATA_FILE
    build_tables(path, with_physics=not args.no_physics, log=lambda m: print(m, flush=True))
    print(f"Property tables written to {path}")
    return 0


def _print_intent(intent, spec, info) -> None:
    print("Design intent (source of every value):")
    for key, v in intent.values.items():
        if key.startswith("note_"):
            continue
        flag = "  [please confirm]" if v.requires_confirmation else ""
        print(f"  {key:22s} {str(v.value):24s} {v.source:15s} {v.detail}{flag}")
        for c in v.citations:
            print(f"  {'':22s} {'':24s} ref: {c}")
    for key, v in intent.values.items():
        if key.startswith("note_"):
            print(f"  note: {v.value}")
    for item in intent.unsupported:
        print(f"  not supported: {item}")
    for item in intent.ambiguities:
        print(f"  ambiguous: {item}")
    point = info.get("design_point") or {}
    if point:
        print(f"Predicted (property tables): walls {point['wall_mm']:.3f} mm, median pore {point['pore_mm']:.3f} mm, openings {point['throat_mm']:.3f} mm")
    print(f"Printer check against: {info.get('printer') or 'no printer selected'}")


def cmd_design(args: argparse.Namespace) -> int:
    from porous_designer.agentic.design_agent import DesignAgent

    provider = settings = None
    if args.provider == "openrouter":
        from porous_designer.agentic.contracts import ProviderMode
        from porous_designer.agentic.provider_config import ExternalCallMode, load_provider_settings
        from porous_designer.agentic.provider_factory import provider_from_settings

        settings = load_provider_settings()
        settings.external_access_enabled = True
        settings.provider_mode = ProviderMode.OPENROUTER
        settings.external_call_mode = ExternalCallMode.ALWAYS
        provider = provider_from_settings(settings)

    def approve_intent(intent, spec, info) -> bool:
        _print_intent(intent, spec, info)
        if args.yes:
            return True
        return input("Generate this design? [y/N] ").strip().lower() in ("y", "yes")

    def approve_final(result) -> bool:
        print(result.explanation or "")
        if args.yes:
            return True
        return input("Accept the result? [Y/n] ").strip().lower() in ("", "y", "yes")

    agent = DesignAgent(
        provider=provider,
        settings=settings,
        output_dir=args.output,
        max_iterations=args.max_iterations,
        approve_intent=approve_intent,
        approve_final=approve_final,
        printer_profile=args.printer,
        process=args.process,
    )
    result = agent.run(args.request)
    print(f"Status: {result.status}")
    if result.status == "infeasible":
        print(result.explanation)
    elif result.explanation and result.status not in ("delivered",):
        print(result.explanation)
    for it in result.iterations:
        v = it["verification"]
        repairs = "; ".join(f"{r['rule']} {r['from']} -> {r['to']}" for r in it.get("repairs", []))
        print(f"  iteration {it['iteration']}: failed {v['failed'] or 'none'}, warnings {v['warnings'] or 'none'}" + (f"; repair: {repairs}" if repairs else ""))
    if result.generation is not None and result.generation.stl_path:
        print(f"Geometry: {result.generation.stl_path}")
        for path in (result.generation.threemf_path, result.generation.step_path):
            if path:
                print(f"  {path}")
    print(f"Agent trace: {result.trace_path}")
    return 0 if result.status in ("delivered", "delivered_with_warnings") else 1


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        from porous_designer.api.server import serve
    except ImportError:
        print("The web front end needs starlette and uvicorn: pip install porous-designer[web]", file=sys.stderr)
        return 1
    print(f"AGE Designer on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    serve(args.host, args.port, output_dir=Path(args.output) if args.output else None)
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    from porous_designer.bench import metrics
    from porous_designer.bench.prompts import DATA_FILE, load_prompts, write_prompts

    if args.action == "build":
        path = write_prompts(seed=args.seed)
        cases = load_prompts(path)
        print(f"{len(cases)} prompts written to {path}")
        return 0
    if args.action == "run":
        from porous_designer.bench.runner import run_bench

        safe = args.system.replace(":", "_").replace("/", "_")
        out = Path(args.output) if args.output else runs_dir() / "bench" / f"{safe}_{args.mode}.jsonl"
        tiers = [int(t) for t in args.tiers.split(",")] if args.tiers else None
        if args.system.startswith(("age_llm", "llm_")):
            n = len([c for c in load_prompts() if not tiers or c.tier in tiers])
            n = min(n, args.limit or n) if not args.per_tier else min(n, args.per_tier * len(tiers or range(7)))
            print(f"This run makes up to {n} OpenRouter request(s); free models allow about 50 per day.", file=sys.stderr)
        run_bench(
            args.system,
            mode=args.mode,
            output=out,
            tiers=tiers,
            limit=args.limit,
            per_tier=args.per_tier,
            resume=not args.fresh,
            voxel_budget=args.voxel_budget,
            allow_llm_code=args.allow_llm_code,
        )
        print(json.dumps(metrics.summarise_file(out)["overall"], indent=2))
        print(f"Rows: {out}")
        return 0
    # report
    files = [Path(f) for f in args.files] or sorted((runs_dir() / "bench").glob("*.jsonl"))
    summaries = {}
    for f in files:
        rows = metrics.load_rows(f)
        if rows:
            summaries[f"{rows[0]['system']} ({rows[0]['mode']})"] = metrics.summarise(rows)
    table = metrics.markdown_table(summaries)
    print(table)
    if args.by_tier:
        for f in files:
            s = metrics.summarise_file(f)
            print(f"\n{f.name}")
            print(metrics.markdown_table({f"tier {t}": v for t, v in s["by_tier"].items()}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="porous-designer",
        description="AGE (Agentic Geometry Engineering) - porous scaffold generation",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--json-log", action="store_true")
    sub = parser.add_subparsers(dest="command")

    p_gen = sub.add_parser("generate", help="Generate STL from specification")
    p_gen.add_argument("spec", help="Specification file path")
    p_gen.add_argument("--yaml", action="store_true")
    p_gen.add_argument("--preview", action="store_true", help="Fast low-resolution preview profile")
    p_gen.add_argument(
        "--profile",
        choices=[p.value for p in GenerationProfile],
        default=GenerationProfile.FINAL.value,
    )
    p_gen.add_argument(
        "--optimization",
        choices=[p.value for p in OptimizationProfile],
        default=OptimizationProfile.NONE.value,
    )
    p_gen.set_defaults(func=cmd_generate)

    p_val = sub.add_parser("validate", help="Validate an STL file")
    p_val.add_argument("stl", help="STL file path")
    p_val.add_argument("--dims", help="Expected X,Y,Z dimensions mm (comma-separated)")
    p_val.set_defaults(func=cmd_validate)

    p_ins = sub.add_parser("inspect-run", help="Inspect a run directory")
    p_ins.add_argument("run_dir", help="Path to runs/<run_id>")
    p_ins.set_defaults(func=cmd_inspect_run)

    p_est = sub.add_parser("estimate", help="Estimate memory/runtime before generation")
    p_est.add_argument("spec")
    p_est.add_argument("--yaml", action="store_true")
    p_est.add_argument("--profile", choices=[p.value for p in GenerationProfile], default="final")
    p_est.set_defaults(func=cmd_estimate)

    p_sens = sub.add_parser("sensitivity", help="Run resolution-sensitivity analysis")
    p_sens.add_argument("spec")
    p_sens.add_argument("--yaml", action="store_true")
    p_sens.add_argument("--resolutions", default="0.10,0.06,0.04")
    p_sens.set_defaults(func=cmd_sensitivity)

    p_opt = sub.add_parser("optimize-mesh", help="Optimize and validate an STL candidate")
    p_opt.add_argument("stl")
    p_opt.add_argument("--profile", choices=[p.value for p in OptimizationProfile], default="conservative")
    p_opt.add_argument("--domain-volume", type=float, default=None)
    p_opt.set_defaults(func=cmd_optimize_mesh)

    p_val_opt = sub.add_parser("validate-optimization", help="Validate master/candidate mesh optimization")
    p_val_opt.add_argument("master")
    p_val_opt.add_argument("candidate")
    p_val_opt.add_argument("--domain-volume", type=float, required=True)
    p_val_opt.set_defaults(func=cmd_validate_optimization)

    p_det = sub.add_parser("determinism", help="Run repeated deterministic generation")
    p_det.add_argument("spec")
    p_det.add_argument("--yaml", action="store_true")
    p_det.add_argument("--runs", type=int, default=2)
    p_det.set_defaults(func=cmd_determinism)

    p_prof = sub.add_parser("profile", help="Profile one generation run")
    p_prof.add_argument("spec")
    p_prof.add_argument("--yaml", action="store_true")
    p_prof.add_argument("--profile", choices=[p.value for p in GenerationProfile], default="final")
    p_prof.set_defaults(func=cmd_profile)

    p_prev = sub.add_parser("preview-consistency", help="Compare preview and final metrics")
    p_prev.add_argument("spec")
    p_prev.add_argument("--yaml", action="store_true")
    p_prev.set_defaults(func=cmd_preview_consistency)

    p_cyl = sub.add_parser("cylinder-accuracy", help="Analyze cylinder voxel-volume convergence")
    p_cyl.add_argument("--diameter", type=float, required=True)
    p_cyl.add_argument("--height", type=float, required=True)
    p_cyl.add_argument("--resolutions", default="0.20,0.10,0.05")
    p_cyl.add_argument("--output", default=str(runs_dir() / "cylinder_accuracy"))
    p_cyl.set_defaults(func=cmd_cylinder_accuracy)

    p_eval = sub.add_parser("evaluate-agent-provider", help="Evaluate request parsing (deterministic, or live grounded extraction via OpenRouter)")
    p_eval.add_argument("--provider", choices=["deterministic", "openrouter"], default="deterministic")
    p_eval.add_argument("--model", default="", help="OpenRouter model id (default: configured default)")
    p_eval.add_argument("--no-fallback", action="store_true", help="Evaluate only --model, without fallback models")
    p_eval.add_argument("--cases", default="", help="Comma-separated case ids to run")
    p_eval.add_argument("--limit", type=int, default=0, help="Run at most N cases (free tier: 50 requests/day)")
    p_eval.add_argument("--credential-mode", choices=["keyring", "environment"], default="keyring")
    p_eval.add_argument("--allow-data-collection", action="store_true", help="Allow endpoints that may log prompts")
    p_eval.add_argument("--output", default="")
    p_eval.set_defaults(func=cmd_evaluate_agent_provider)

    p_cred = sub.add_parser("credentials", help="Store, inspect, or delete a provider API key in the OS credential store")
    p_cred.add_argument("action", choices=["set", "status", "delete"])
    p_cred.add_argument("--provider", default="openrouter", choices=["openrouter"])
    p_cred.set_defaults(func=cmd_credentials)

    p_models = sub.add_parser("openrouter-models", help="List free OpenRouter models that support strict structured output")
    p_models.set_defaults(func=cmd_openrouter_models)

    p_pr = sub.add_parser("printers", help="List printer/process profiles used by the printability checks")
    p_pr.set_defaults(func=cmd_printers)

    p_cp = sub.add_parser("make-coupon", help="Write a calibration coupon (STL + measurement sheet) for a printer profile")
    p_cp.add_argument("output", help="Output folder")
    p_cp.add_argument("--profile", default="generic_msla", help="Profile id (see 'printers')")
    p_cp.set_defaults(func=cmd_make_coupon)

    p_cal = sub.add_parser("calibrate", help="Create a printer profile from a filled-in coupon measurement sheet")
    p_cal.add_argument("--profile", required=True, help="Profile the coupon was made for")
    p_cal.add_argument("--measurements", required=True, help="Filled-in *_measurements.csv")
    p_cal.add_argument("--name", required=True, help="Id of the new profile (e.g. my_elegoo_mars)")
    p_cal.set_defaults(func=cmd_calibrate)

    p_fam = sub.add_parser("families", help="List structure families, domains, and export formats")
    p_fam.set_defaults(func=cmd_families)

    p_ph = sub.add_parser("make-phantom", help="Write a synthetic closed wound-cavity mesh for mesh-domain tests")
    p_ph.add_argument("output", help="Output mesh path (.stl, .ply, .obj)")
    p_ph.add_argument("--length", type=float, default=30.0, help="Wound length (mm)")
    p_ph.add_argument("--width", type=float, default=18.0, help="Wound width (mm)")
    p_ph.add_argument("--depth", type=float, default=6.0, help="Maximum depth (mm)")
    p_ph.add_argument("--irregularity", type=float, default=0.15)
    p_ph.add_argument("--seed", type=int, default=0)
    p_ph.set_defaults(func=cmd_make_phantom)

    p_des = sub.add_parser("design", help="Agent v2: plain-language request -> verified, printable design")
    p_des.add_argument("request", help="Design request in plain language")
    p_des.add_argument("--process", default=None, help="Manufacturing process (fdm, sla, dlp, volumetric_tomographic, ...)")
    p_des.add_argument("--printer", default=None, help="Printer profile id (see 'printers')")
    p_des.add_argument("--provider", default="deterministic", choices=["deterministic", "openrouter"])
    p_des.add_argument("--max-iterations", type=int, default=3)
    p_des.add_argument("--output", default=None, help="Output folder")
    p_des.add_argument("--yes", action="store_true", help="Approve both checkpoints automatically")
    p_des.set_defaults(func=cmd_design)

    p_tab = sub.add_parser("build-property-tables", help="Measure structure-property tables of every family (GPU recommended)")
    p_tab.add_argument("--output", default=None)
    p_tab.add_argument("--no-physics", action="store_true", help="Skip permeability and stiffness")
    p_tab.set_defaults(func=cmd_build_property_tables)

    p_srv = sub.add_parser("serve", help="Local web front end (Describe -> Review -> Download) and JSON API")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=8765)
    p_srv.add_argument("--output", default=None)
    p_srv.set_defaults(func=cmd_serve)

    p_b = sub.add_parser("bench", help="AGE-Bench: build the prompt set, run a system, compare results")
    p_b.add_argument("action", choices=["build", "run", "report"])
    p_b.add_argument("--system", default="age", help="age | age_llm:<model> | age_no_knowledge | age_no_feasibility | age_no_verifier | llm_direct:<model> | llm_code:<model>")
    p_b.add_argument("--mode", default="extract", choices=["extract", "propose", "full"])
    p_b.add_argument("--tiers", default=None, help="comma-separated tiers, e.g. 1,5,7")
    p_b.add_argument("--limit", type=int, default=None)
    p_b.add_argument("--per-tier", type=int, default=None, help="first N prompts of each tier")
    p_b.add_argument("--output", default=None)
    p_b.add_argument("--fresh", action="store_true", help="start over instead of resuming")
    p_b.add_argument("--voxel-budget", type=int, default=None, help="grid points per design (default 60 M; 8 M in full mode for speed)")
    p_b.add_argument("--allow-llm-code", action="store_true", help="execute LLM-written field functions (isolated process, whitelist-checked)")
    p_b.add_argument("--seed", type=int, default=2026)
    p_b.add_argument("--by-tier", action="store_true")
    p_b.add_argument("files", nargs="*", help="run files for 'report' (default: all in runs/bench)")
    p_b.set_defaults(func=cmd_bench)

    args = parser.parse_args(argv)
    configure_logging(level="DEBUG" if args.verbose else "INFO", json_output=args.json_log)

    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
