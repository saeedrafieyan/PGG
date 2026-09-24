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
    print(f"  Lattice spacing:     {result.lattice_spacing_mm:.4f} mm")
    print(f"  Tuning-grid porosity:{result.tuning_grid_porosity * 100:.2f}%")
    print(f"  Final voxel porosity:{result.final_voxel_porosity * 100:.2f}%")
    print(f"  Final mesh porosity: {result.final_mesh_porosity * 100:.2f}%")
    print(f"  Triangles:           {result.triangle_count}")
    print(f"  Watertight:          {result.watertight}")
    print(f"  Solid components:    {result.solid_components}")
    print(f"  STL:                 {result.stl_path}")
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

    args = parser.parse_args(argv)
    configure_logging(level="DEBUG" if args.verbose else "INFO", json_output=args.json_log)

    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
