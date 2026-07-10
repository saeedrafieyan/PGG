"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from porous_designer import __version__
from porous_designer.domain.specification import DesignSpecification, load_legacy_spec
from porous_designer.logging_config import configure_logging, get_logger
from porous_designer.services.generation_service import GenerationProfile, generate_sphere_lattice_stl
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

    profile = GenerationProfile.PREVIEW if args.preview else GenerationProfile.FINAL
    result = generate_sphere_lattice_stl(spec, profile=profile)

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
    print(f"  Timing (s):          total={result.timing.total_s:.1f}  "
          f"tune={result.timing.tuning_s:.1f}  voxel={result.timing.voxel_generation_s:.1f}  "
          f"mc={result.timing.marching_cubes_s:.1f}  val={result.timing.validation_s:.1f}")
    print(f"  Peak memory:         {result.peak_memory_mb:.1f} MB")
    for msg in result.messages:
        print(f"  NOTE: {msg}")
    if result.tuning and not result.tuning.converged:
        print(f"  WARNING: {result.tuning.message}")

    return 0 if result.success else 1


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="porous-designer",
        description="Porous Structure Designer - deterministic porous scaffold generation",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--json-log", action="store_true")
    sub = parser.add_subparsers(dest="command")

    p_gen = sub.add_parser("generate", help="Generate STL from specification")
    p_gen.add_argument("spec", help="Specification file path")
    p_gen.add_argument("--yaml", action="store_true")
    p_gen.add_argument("--preview", action="store_true", help="Fast low-resolution preview profile")
    p_gen.set_defaults(func=cmd_generate)

    p_val = sub.add_parser("validate", help="Validate an STL file")
    p_val.add_argument("stl", help="STL file path")
    p_val.add_argument("--dims", help="Expected X,Y,Z dimensions mm (comma-separated)")
    p_val.set_defaults(func=cmd_validate)

    p_ins = sub.add_parser("inspect-run", help="Inspect a run directory")
    p_ins.add_argument("run_dir", help="Path to runs/<run_id>")
    p_ins.set_defaults(func=cmd_inspect_run)

    args = parser.parse_args(argv)
    configure_logging(level="DEBUG" if args.verbose else "INFO", json_output=args.json_log)

    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
