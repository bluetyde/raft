"""Run the cases of the M8 BEAVRS hot zero power protocol (docs/validation/m8-beavrs-hzp-protocol.md) with the published BEAVRS OpenMC generator.

The cases and their settings are fixed in validation/m8_beavrs_hzp.py. Each case is run once: a case already in the results file is refused.
Results are appended, one JSON line per case, to pipeline/openmc/results/beavrs_hzp.jsonl.

Run in the openmc-vr env (WSL), from the repo root, with the BEAVRS repository (mit-crpg/BEAVRS, MIT) cloned somewhere:

  export OPENMC_CROSS_SECTIONS=/root/nuclear_data/endfb-viii.0-hdf5/cross_sections.xml
  python -m pipeline.openmc.beavrs_run --beavrs ~/beavrs --stage 1          # W0 W7 K0a K0b (then --stage 2, --stage 3)
  python -m pipeline.openmc.beavrs_run --beavrs ~/beavrs --all              # the 20 cases in the protocol's order
  python -m pipeline.openmc.beavrs_run --beavrs ~/beavrs --case W3          # one case
  python -m pipeline.openmc.beavrs_run --beavrs ~/beavrs --case T0p --dry   # build the model only and report what it would run

Nothing of BEAVRS is copied into this repository; the generator is imported from the clone.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from validation import m8_beavrs_hzp as bv  # noqa: E402

RESULTS = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_hzp.jsonl"
WATER = ("Borated Water", "Water SPN")             # the materials that are water; their density follows the temperature
PRESSURE_MPA = 15.5
# Stages, so a defect in the runner shows up after minutes, not hours. Stage 1 exercises the whole path (bank insertion, boron, the convergence windows,
# the boron worth pair); stage 2 is the rest of the 300-batch cases; stage 3 holds the long temperature cases.
STAGES = {1: ["W0", "W7", "K0a", "K0b"],
          2: ["W1", "W2", "W3", "W4", "W5", "W6", "B1", "B2", "B4", "B7", "K7a", "K7b"],
          3: ["T0m", "T0p", "T2m", "T2p"]}


def build(beavrs_dir: Path, spec: dict):
    """The openmc.Model for one case, and what was changed from the published model (for the record)."""
    sys.path.insert(0, str(beavrs_dir / "models" / "openmc"))
    import openmc.data
    from beavrs.builder import BEAVRS
    import beavrs.constants as c

    rcca = dict(c.rcca_bank_steps_withdrawn_default)
    for bank in bv.banks_in(spec["state"]):
        rcca[bank] = 0
    b = BEAVRS(boron_ppm=spec["boron"], rcca_z=rcca)
    b.set_params(particles=spec["particles"], batches=spec["batches"], inactive=spec["inactive"])
    note = {"banksIn": bv.banks_in(spec["state"]), "rccaSteps": rcca}
    t = spec["temperature"]
    if abs(t - c.operating_temperature) > 1e-9:
        ratio = openmc.data.water_density(t, PRESSURE_MPA) / openmc.data.water_density(c.operating_temperature, PRESSURE_MPA)
        for name, mat in b.mats.items():
            mat.temperature = t
            if name in WATER:
                mat.set_density("g/cm3", mat.density * ratio)
        note.update({"waterDensityRatio": ratio, "waterDensity": openmc.data.water_density(t, PRESSURE_MPA), "pressureMPa": PRESSURE_MPA})
    model = b.build_openmc_model()
    model.settings.temperature["default"] = t
    return model, note


def run_case(cid: str, spec: dict, beavrs_dir: Path, out: Path, dry: bool) -> None:
    if out.exists() and any(json.loads(x).get("case") == cid for x in out.read_text(encoding="utf-8").splitlines() if x.strip()):
        raise SystemExit(f"case {cid} is already in {out.name}; each case is run once")
    import openmc

    model, note = build(beavrs_dir, spec)
    print(f"{cid}: {note['banksIn']} in, {spec['boron']} ppm, {spec['temperature']} K, {spec['particles']} x {spec['batches']} / {spec['inactive']}"
          + (f", water {note['waterDensity']:.5f} g/cm3" if "waterDensity" in note else ""), flush=True)
    if dry:
        return
    work = Path(tempfile.mkdtemp(prefix=f"beavrs_{cid}_"))
    model.export_to_model_xml(work / "model.xml")
    load_before = os.getloadavg()
    r0, t0 = resource.getrusage(resource.RUSAGE_CHILDREN), time.time()
    subprocess.run(["openmc"], cwd=work, check=True, stdout=open(work / "openmc.out", "w"), stderr=subprocess.STDOUT)
    wall = time.time() - t0
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    sp = openmc.StatePoint(work / f"statepoint.{spec['batches']}.h5")
    k = sp.keff
    line = {"case": cid, **spec, "k": float(k.nominal_value), "kStd": float(k.std_dev), "kBatches": [float(x) for x in sp.k_generation],
            "wallS": wall, "cpuS": (r1.ru_utime - r0.ru_utime), "loadBefore": load_before[0], "loadAfter": os.getloadavg()[0],
            "openmc": openmc.__version__, "seed": int(sp.seed), "waterDensity": note.get("waterDensity"), "crossSections": os.environ.get("OPENMC_CROSS_SECTIONS", "")}
    sp.close()
    with out.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    print(f"   k = {line['k']:.5f} +- {line['kStd']:.5f}   wall {wall:.0f} s, cpu {line['cpuS']:.0f} s, load {load_before[0]:.1f} -> {line['loadAfter']:.1f}", flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--beavrs", type=Path, required=True, help="the clone of mit-crpg/BEAVRS")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("--stage", type=int, choices=sorted(STAGES), help="1: W0 W7 K0a K0b; 2: the other 300-batch cases; 3: the four long temperature cases")
    g.add_argument("--case", action="append")
    ap.add_argument("--out", type=Path, default=RESULTS)
    ap.add_argument("--dry", action="store_true", help="build each model and print it; run nothing")
    ap.add_argument("--smoke", default=None, help="particles,batches,inactive for a test run; only with an --out other than the protocol's file")
    args = ap.parse_args(argv)
    plan = bv.cases()
    ids = list(plan) if args.all else STAGES[args.stage] if args.stage else args.case
    for cid in ids:
        if cid not in plan:
            raise SystemExit(f"{cid} is not one of the protocol's cases: {', '.join(plan)}")
    if args.all or args.stage:
        # one process per case: BEAVRS objects keep their ids, and a crash costs one case
        done = {json.loads(x).get("case") for x in args.out.read_text(encoding="utf-8").splitlines() if x.strip()} if args.out.exists() else set()
        for cid in ids:
            if cid in done:
                print(f"{cid}: already in {args.out.name}, skipped", flush=True)
                continue
            cmd = [sys.executable, "-m", "pipeline.openmc.beavrs_run", "--beavrs", str(args.beavrs), "--case", cid, "--out", str(args.out)]
            cmd += (["--dry"] if args.dry else []) + (["--smoke", args.smoke] if args.smoke else [])
            subprocess.run(cmd, check=True, cwd=REPO_ROOT)
        return 0
    for cid in ids:
        spec = dict(plan[cid])
        if args.smoke:
            if args.out.resolve() == RESULTS.resolve():
                raise SystemExit("--smoke cannot write to the protocol's results file")
            spec["particles"], spec["batches"], spec["inactive"] = (int(x) for x in args.smoke.split(","))
        run_case(cid, spec, args.beavrs, args.out, args.dry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
