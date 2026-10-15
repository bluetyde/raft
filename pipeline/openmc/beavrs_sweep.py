"""Run the BEAVRS library sweep (cases in beavrs_cases.py) with the published BEAVRS OpenMC generator.

Each case is run once (a case already in the results file is skipped). Results are appended, one JSON line per case, to
pipeline/openmc/results/beavrs_sweep.jsonl: k, its error, and the fission-rate tally on a 19 x 19 x 10 mesh over the core lattice and the
active fuel height (flat, mean and standard deviation per bin, in OpenMC's mesh order), plus beta_eff and the generation time for REF.

Run in the openmc-vr env (WSL), from the repo root:

  export OPENMC_CROSS_SECTIONS=/root/nuclear_data/endfb-viii.0-hdf5/cross_sections.xml
  python -m pipeline.openmc.beavrs_sweep --beavrs ~/beavrs --all            # every case not yet run
  python -m pipeline.openmc.beavrs_sweep --beavrs ~/beavrs --case REF --smoke 4000,30,10 --out /tmp/smoke.jsonl
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

from pipeline.openmc import beavrs_cases as bc  # noqa: E402

RESULTS = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_sweep.jsonl"
PATH_RESULTS = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_path.jsonl"
SHADOW_RESULTS = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_shadow.jsonl"
NEAR_RESULTS = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_near.jsonl"
PRESSURE_MPA = 15.5
WATER = ("Borated Water", "Water SPN")
IFP_GENERATIONS = 10


def build(beavrs_dir: Path, spec: dict):
    head = bc.check_beavrs_head(beavrs_dir)
    sys.path.insert(0, str(beavrs_dir / "models" / "openmc"))
    import openmc
    import openmc.data
    from beavrs.builder import BEAVRS
    import beavrs.constants as c

    b = BEAVRS(boron_ppm=spec["boron"], rcca_z=dict(spec["steps"]))
    b.set_params(particles=spec["particles"], batches=spec["batches"], inactive=spec["inactive"])
    note = {"beavrsHead": head}
    if spec["tFuel"] is not None:
        for name, mat in b.mats.items():
            if name.startswith("Fuel"):
                mat.temperature = spec["tFuel"]
    if spec["tWater"] is not None:
        t = spec["tWater"]
        ratio = openmc.data.water_density(t, PRESSURE_MPA) / openmc.data.water_density(c.operating_temperature, PRESSURE_MPA)
        for name in WATER:
            b.mats[name].temperature = t
            b.mats[name].set_density("g/cm3", b.mats[name].density * ratio)
        note["waterDensity"] = openmc.data.water_density(t, PRESSURE_MPA)
    model = b.build_openmc_model()
    if spec["tFuel"] is not None and spec["tFuel"] > 600.0:
        model.settings.temperature["range"] = (300.0, 1000.0)          # the 900 K nuclide data must load to interpolate above 600 K
    mesh = openmc.RegularMesh()
    p = c.latticePitch
    mesh.lower_left = (-19 * p / 2, -19 * p / 2, bc.MESH["zLowerCm"])
    mesh.upper_right = (19 * p / 2, 19 * p / 2, bc.MESH["zUpperCm"])
    mesh.dimension = tuple(bc.MESH["dimension"])
    t = openmc.Tally(name="fission-mesh")
    t.filters = [openmc.MeshFilter(mesh)]
    t.scores = ["fission"]
    model.tallies = openmc.Tallies(list(model.tallies) + [t])
    if spec["ifp"]:
        model.settings.ifp_n_generation = IFP_GENERATIONS
        model.add_kinetics_parameters_tallies(num_groups=6)
    return model, note


def run_case(cid: str, spec: dict, beavrs_dir: Path, out: Path, dry: bool) -> None:
    import openmc

    model, note = build(beavrs_dir, spec)
    print(f"{cid}: {spec['role']}, boron {spec['boron']}, steps {spec['steps']}, Tfuel {spec['tFuel']}, Twater {spec['tWater']}", flush=True)
    if dry:
        return
    work = Path(tempfile.mkdtemp(prefix=f"beavrs_sweep_{cid}_"))
    model.export_to_model_xml(work / "model.xml")
    load_before = os.getloadavg()[0]
    r0, t0 = resource.getrusage(resource.RUSAGE_CHILDREN), time.time()
    subprocess.run(["openmc"], cwd=work, check=True, stdout=open(work / "openmc.out", "w"), stderr=subprocess.STDOUT)
    wall = time.time() - t0
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    with openmc.StatePoint(work / f"statepoint.{spec['batches']}.h5") as sp:
        k = sp.keff
        k_batches = [float(x) for x in sp.k_generation]          # every batch, inactive included (the drift check of the protocols needs them)
        tl = sp.get_tally(name="fission-mesh")
        line = {"case": cid, **spec, "k": float(k.nominal_value), "kStd": float(k.std_dev),
                "fission": [float(x) for x in tl.mean.flatten()], "fissionStd": [float(x) for x in tl.std_dev.flatten()],
                "wallS": wall, "cpuS": r1.ru_utime - r0.ru_utime, "loadBefore": load_before, "loadAfter": os.getloadavg()[0],
                "openmc": openmc.__version__, "seed": int(sp.seed), "waterDensity": note.get("waterDensity"), "beavrsHead": note["beavrsHead"],
                "kBatches": k_batches}
        if spec["ifp"]:
            kin = sp.get_kinetics_parameters()
            groups, lam = kin.beta_effective, kin.generation_time
            line.update(betaGroups=[g.nominal_value for g in groups], betaGroupsStd=[g.std_dev for g in groups],
                        betaEff=sum(g.nominal_value for g in groups), lambdaS=lam.nominal_value, lambdaStdS=lam.std_dev)
    with out.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    print(f"   k = {line['k']:.5f} +- {line['kStd']:.5f}   wall {wall:.0f} s, load {load_before:.1f} -> {line['loadAfter']:.1f}", flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--beavrs", type=Path, required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("--case", action="append")
    ap.add_argument("--family", choices=("sweep", "path", "shadow", "near"), default="sweep", help="the 45 library cases, the nine held-out path cases of the fourteenth protocol, or the 13 held-out cases of the fifteenth")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--smoke", default=None, help="particles,batches,inactive for a test run; only with an --out other than the sweep's file")
    args = ap.parse_args(argv)
    plan, default_out = {"sweep": (bc.sweep_cases, RESULTS), "path": (bc.path_cases, PATH_RESULTS), "shadow": (bc.shadow_cases, SHADOW_RESULTS), "near": (bc.near_cases, NEAR_RESULTS)}[args.family]
    plan = plan()
    if args.out is None:
        args.out = default_out
    ids = list(plan) if args.all else args.case
    for cid in ids:
        if cid not in plan:
            raise SystemExit(f"{cid} is not a sweep case")
    done = {json.loads(x).get("case") for x in args.out.read_text(encoding="utf-8").splitlines() if x.strip()} if args.out.exists() else set()
    if args.smoke and args.out.resolve() == default_out.resolve():
        raise SystemExit("--smoke cannot write to the results file of the family")
    for cid in ids:
        if cid in done:
            print(f"{cid}: already in {args.out.name}, skipped", flush=True)
            continue
        if args.all:
            cmd = [sys.executable, "-m", "pipeline.openmc.beavrs_sweep", "--beavrs", str(args.beavrs), "--family", args.family, "--case", cid, "--out", str(args.out)]
            cmd += (["--dry"] if args.dry else []) + (["--smoke", args.smoke] if args.smoke else [])
            subprocess.run(cmd, check=True, cwd=REPO_ROOT)
            continue
        spec = dict(plan[cid])
        if args.smoke:
            spec["particles"], spec["batches"], spec["inactive"] = (int(x) for x in args.smoke.split(","))
        run_case(cid, spec, args.beavrs, args.out, args.dry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
