"""Command-line interface entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from porous_designer import __version__
from porous_designer.blackboard.persistence import persist_blackboard
from porous_designer.blackboard.state import Blackboard
from porous_designer.blackboard.state_machine import StateMachine
from porous_designer.domain.enums import RunStatus
from porous_designer.domain.specification import DesignSpecification, load_legacy_spec
from porous_designer.logging_config import configure_logging, get_logger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="porous-designer",
        description="Porous Structure Designer — deterministic porous scaffold generation",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "spec",
        nargs="?",
        help="Path to specification file (legacy key:value or YAML)",
    )
    parser.add_argument("--yaml", action="store_true", help="Interpret spec as YAML DesignSpecification")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--json-log", action="store_true", help="Emit structured JSON logs")
    args = parser.parse_args(argv)

    configure_logging(level="DEBUG" if args.verbose else "INFO", json_output=args.json_log)
    log = get_logger("cli")

    if not args.spec:
        parser.print_help()
        return 0

    spec_path = Path(args.spec)
    if not spec_path.exists():
        log.error("spec_not_found", path=str(spec_path))
        return 1

    bb = Blackboard(raw_request=spec_path.read_text(encoding="utf-8"))
    sm = StateMachine(bb)
    sm.transition(RunStatus.PARSING, "Loading specification")

    try:
        if args.yaml or spec_path.suffix in (".yaml", ".yml"):
            spec = DesignSpecification.from_yaml_file(spec_path)
        else:
            spec = load_legacy_spec(spec_path)
    except Exception as exc:
        log.error("spec_load_failed", error=str(exc))
        sm.transition(RunStatus.FAILED, str(exc))
        persist_blackboard(bb)
        return 1

    bb.set_parsed_spec(spec)
    bb.set_approved_spec(spec)  # CLI auto-approves; GUI will require explicit approval
    sm.transition(RunStatus.SPECIFICATION_APPROVED, "Specification loaded (CLI auto-approve)")

    log.info(
        "specification_loaded",
        run_id=bb.run_id,
        family=spec.structure.family.value,
        domain=spec.domain.shape.value,
        porosity_target=spec.targets.porosity_target.target,
    )

    out_path = persist_blackboard(bb, spec.export.output_directory)
    run_dir = out_path.parent
    spec.save_yaml(run_dir / "approved_specification.yaml")
    log.info("blackboard_saved", path=str(run_dir))

    print(f"Porous Structure Designer v{__version__}")
    print(f"  Run ID:    {bb.run_id}")
    print(f"  Status:    {bb.status.value}")
    print(f"  Family:    {spec.structure.family.value}")
    print(f"  Domain:    {spec.domain.shape.value} {spec.domain.dimensions_mm}")
    print(f"  Porosity:  {spec.targets.porosity_target.target * 100:.1f}%")
    print(f"  Output:    {run_dir}")
    print()
    print("Generation pipeline not yet wired (Phase 2+). Specification validated and saved.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
