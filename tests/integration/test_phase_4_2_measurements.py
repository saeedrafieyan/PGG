"""Phase 4.2 end to end: measurements and printability in generated runs, CLI tools."""

from __future__ import annotations

import csv
import json

import pytest

from porous_designer.cli import main as cli_main
from porous_designer.domain.enums import DomainShape, SkinMode, StructureFamily, ValidationStatus
from porous_designer.domain.specification import (
    ConstraintsSpec,
    DesignSpecification,
    DomainSpec,
    ExportSpec,
    GenerationSpec,
    ManufacturingSpec,
    PorosityTarget,
    StructureSpec,
    TargetsSpec,
)
from porous_designer.services.generation_service import GenerationProfile, generate_porous_stl


def _spec(tmp_path, family=StructureFamily.GYROID, *, process="sla", level="basic", enforce=False, domain=None, constraints=None, **structure):
    structure.setdefault("unit_cell_size_mm", 2.0)
    return DesignSpecification(
        domain=domain or DomainSpec(shape=DomainShape.BOX, dimensions_mm=[4.0, 4.0, 4.0]),
        structure=StructureSpec(family=family, **structure),
        targets=TargetsSpec(porosity_target=PorosityTarget(target=0.7, tolerance=0.02)),
        constraints=constraints or ConstraintsSpec(),
        manufacturing=ManufacturingSpec(process=process, enforce_printability=enforce),
        generation=GenerationSpec(preview_resolution_mm=0.2, final_resolution_mm=0.08, metrology=level, compute_backend="cpu"),
        export=ExportSpec(output_directory=str(tmp_path), output_name=family.value),
    )


def _checks(result):
    return {c["name"]: c for c in json.loads((result.run_dir / "validation_report.json").read_text())["checks"]}


def test_basic_measurements_and_sla_printability(tmp_path):
    result = generate_porous_stl(_spec(tmp_path, constraints=ConstraintsSpec(minimum_wall_thickness_mm=0.1, minimum_throat_size_mm=0.2)))
    assert result.success, result.messages
    m = result.measurements
    assert 0.1 < m["wall_d50_mm"] < 0.35 and 0.4 < m["pore_d50_mm"] < 1.2
    assert m["percolation_diameter_mm"] > 0.2 and m["closed_void_fraction"] == 0.0
    assert 1.0 <= m["tortuosity"] < 1.3
    metrology = json.loads((result.run_dir / "metrology.json").read_text())
    assert metrology["part"]["curvature"]["saddle_fraction"] > 0.8  # TPMS surfaces are saddles
    checks = _checks(result)
    assert checks["minimum_wall_thickness"]["status"] == "pass"
    assert checks["minimum_throat_size"]["status"] == "pass"
    assert {"print_min_wall", "print_drainage", "print_islands", "print_closed_pores"} <= set(checks)
    assert (result.run_dir / "printability.json").exists()


def test_min_wall_constraint_fails_when_walls_are_thinner(tmp_path):
    result = generate_porous_stl(_spec(tmp_path, constraints=ConstraintsSpec(minimum_wall_thickness_mm=0.5)))
    assert not result.success
    assert _checks(result)["minimum_wall_thickness"]["status"] == "fail"


def test_enforced_printability_fails_the_run(tmp_path):
    # FDM cannot print ~0.2 mm gyroid sheets; enforced, that is a failure.
    warn = generate_porous_stl(_spec(tmp_path / "w", process="fdm"))
    assert warn.success and _checks(warn)["print_min_wall"]["status"] == "warning"
    enforced = generate_porous_stl(_spec(tmp_path / "e", process="fdm", enforce=True))
    assert not enforced.success and _checks(enforced)["print_min_wall"]["status"] == "fail"


def test_full_skin_traps_resin(tmp_path):
    domain = DomainSpec(shape=DomainShape.BOX, dimensions_mm=[4.0, 4.0, 4.0], skin_thickness_mm=0.3, skin_mode=SkinMode.ALL)
    spec = _spec(tmp_path, domain=domain, constraints=ConstraintsSpec(require_open_pores=False))
    result = generate_porous_stl(spec)
    assert result.measurements["closed_void_fraction"] > 0.9
    assert _checks(result)["print_closed_pores"]["status"] == "warning"


def test_full_level_adds_permeability_and_stiffness(tmp_path):
    result = generate_porous_stl(_spec(tmp_path, level="full"))
    assert result.success, result.messages
    m = result.measurements
    assert 1e-10 < m["permeability_m2"] < 1e-7  # mm-scale gyroid
    assert 0.05 < m["youngs_relative"] < 0.2


def test_no_process_skips_printability_and_preview_skips_measurements(tmp_path):
    result = generate_porous_stl(_spec(tmp_path, process="unknown"))
    assert result.printability is None and not any(n.startswith("print_") for n in _checks(result))
    preview = generate_porous_stl(_spec(tmp_path, process="sla"), profile=GenerationProfile.PREVIEW)
    assert preview.measurements == {} and not (preview.run_dir / "metrology.json").exists()


def test_cli_printers_coupon_and_calibrate(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGE_HOME", str(tmp_path / "home"))
    assert cli_main(["printers"]) == 0
    assert "generic_msla" in capsys.readouterr().out
    out = tmp_path / "coupon"
    assert cli_main(["make-coupon", str(out), "--profile", "generic_fdm_0.4"]) == 0
    sheet = out / "coupon_generic_fdm_0.4_measurements.csv"
    rows = list(csv.DictReader(sheet.open(encoding="utf-8")))
    for r in rows:
        r["printed_ok"] = "yes" if float(r["nominal_mm"]) >= 0.5 else "no"
    with sheet.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert cli_main(["calibrate", "--profile", "generic_fdm_0.4", "--measurements", str(sheet), "--name", "lab_fdm"]) == 0
    assert (tmp_path / "home" / "printers" / "lab_fdm.yaml").exists()
    assert cli_main(["printers"]) == 0
    assert "lab_fdm" in capsys.readouterr().out
