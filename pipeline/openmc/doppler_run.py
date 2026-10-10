"""Run the Doppler-defect cases (pipeline/openmc/doppler_cases.py) with OpenMC, one process per case.

The model of a case is the Mosteller pin cell of docs/validation/doppler-defect-protocol.md: fuel, void gap, Zircaloy cladding and
borated water in a square reflective box 20 cm high. Water and cladding are at 600 K; the fuel is at 600 K (hzp) or 900 K (hfp). The
dimensions and densities come from pipeline/openmc/data/mosteller_doppler.json. Temperature method "nearest", tolerance 10 K;
resonance scattering is not turned on.

Each case is run once. A case already in the results file is refused (an explicit --case) or skipped (--all) unless it is a smoke
run. One JSON line per case is appended to pipeline/openmc/results/doppler_defect.jsonl (or --out).

Run in the openmc-vr env (WSL), from the repo root:
  python -m pipeline.openmc.doppler_run --dry --all                                   # list the 32 cases, run nothing
  python -m pipeline.openmc.doppler_run --all                                         # every case not yet in the results file
  python -m pipeline.openmc.doppler_run --case "uo2-3.1/hzp"                          # one case
  python -m pipeline.openmc.doppler_run --case "uo2-3.1/hzp" --smoke 2000,30,10 --out /tmp/doppler_smoke.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.openmc import doppler_cases as dc  # noqa: E402

DATA = REPO_ROOT / "pipeline" / "openmc" / "data" / "mosteller_doppler.json"
RESULTS = REPO_ROOT / "pipeline" / "openmc" / "results" / "doppler_defect.jsonl"
CROSS_SECTIONS = "/root/nuclear_data/endfb-viii.0-hdf5/cross_sections.xml"
WATER_K = 600.0
TEMPERATURE = {"method": "nearest", "tolerance": 10.0}


def load_data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def build(spec: dict, data: dict):
    import openmc

    k = str(spec["fuelK"])
    sub, content = spec["subset"], str(spec["content"])
    pitch, r_fuel, r_ci, r_co = data["pitch"][k], data["fuel_or"][k], data["clad_ir"][k], data["clad_or"][k]

    water = openmc.Material(name="H2O", temperature=WATER_K)
    water.set_density("sum")
    for nuc, dens in data["water_comp"]["600"]:
        water.add_nuclide(nuc, dens)
    water.add_s_alpha_beta("c_H_in_H2O")

    zircaloy = openmc.Material(name="Zircaloy", temperature=WATER_K)
    zircaloy.set_density("atom/b-cm", data["clad_density"]["600"])
    zircaloy.add_element("Zr", 1.0)

    comp = data["composition"][sub]
    fuel = openmc.Material(name=f"fuel {sub} {content}", temperature=float(spec["fuelK"]))
    for nuc, dens in zip(comp["nuclides"], comp["densities"][k][content]):
        fuel.add_nuclide(nuc, dens)
    fuel.set_density("sum")

    x0 = openmc.XPlane(x0=-pitch / 2, boundary_type="reflective")
    x1 = openmc.XPlane(x0=pitch / 2, boundary_type="reflective")
    y0 = openmc.YPlane(y0=-pitch / 2, boundary_type="reflective")
    y1 = openmc.YPlane(y0=pitch / 2, boundary_type="reflective")
    z0 = openmc.ZPlane(z0=-10.0, boundary_type="reflective")
    z1 = openmc.ZPlane(z0=10.0, boundary_type="reflective")
    box = +x0 & -x1 & +y0 & -y1 & +z0 & -z1

    f_surf = openmc.ZCylinder(r=r_fuel)
    ci_surf = openmc.ZCylinder(r=r_ci)
    co_surf = openmc.ZCylinder(r=r_co)
    fuel_cell = openmc.Cell(name="fuel", fill=fuel, region=-f_surf & box)
    gap_cell = openmc.Cell(name="gap (void)", region=+f_surf & -ci_surf & box)
    clad_cell = openmc.Cell(name="cladding", fill=zircaloy, region=+ci_surf & -co_surf & box)
    water_cell = openmc.Cell(name="water", fill=water, region=+co_surf & box)
    geometry = openmc.Geometry(openmc.Universe(cells=[fuel_cell, gap_cell, clad_cell, water_cell]))

    materials = openmc.Materials([water, zircaloy, fuel])
    materials.cross_sections = CROSS_SECTIONS

    settings = openmc.Settings()
    settings.run_mode = "eigenvalue"
    settings.particles = spec["particles"]
    settings.batches = spec["batches"]
    settings.inactive = spec["inactive"]
    settings.seed = spec["seed"]
    settings.temperature = dict(TEMPERATURE)
    settings.source = openmc.IndependentSource(
        space=openmc.stats.Box((-r_fuel, -r_fuel, -10.0), (r_fuel, r_fuel, 10.0)), constraints={"fissionable": True})
    return openmc.Model(geometry=geometry, materials=materials, settings=settings)


def run_case(spec: dict, out: Path, dry: bool) -> None:
    cid = f"{spec['case']}/{spec['state']}"
    print(f"{cid}: fuel {spec['fuelK']} K, {spec['particles']} x {spec['batches']} / inactive {spec['inactive']}, seed {spec['seed']}",
          flush=True)
    if dry:
        return
    import openmc
    import resource  # POSIX only: the real runs happen in WSL

    data = load_data()
    model = build(spec, data)
    work = Path(tempfile.mkdtemp(prefix=f"doppler_{spec['case']}_{spec['state']}_"))
    model.export_to_model_xml(work / "model.xml")
    load_before = os.getloadavg()[0]
    r0, t0 = resource.getrusage(resource.RUSAGE_CHILDREN), time.time()
    subprocess.run(["openmc"], cwd=work, check=True, stdout=open(work / "openmc.out", "w"), stderr=subprocess.STDOUT)
    wall = time.time() - t0
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    with openmc.StatePoint(work / f"statepoint.{spec['batches']}.h5") as sp:
        k = sp.keff
        k_gen = [float(x) for x in sp.k_generation]
        line = {"case": spec["case"], "state": spec["state"], "fuelK": spec["fuelK"], "subset": spec["subset"],
                "content": spec["content"], "particles": spec["particles"], "batches": spec["batches"],
                "inactive": spec["inactive"], "seed": spec["seed"], "k": float(k.nominal_value), "kStd": float(k.std_dev),
                "kBatches": k_gen, "openmc": openmc.__version__, "wallS": wall, "cpuS": r1.ru_utime - r0.ru_utime,
                "loadBefore": load_before, "loadAfter": os.getloadavg()[0], "crossSections": CROSS_SECTIONS}
    with out.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    print(f"   k = {line['k']:.5f} +- {line['kStd']:.5f}   wall {wall:.0f} s, load {load_before:.1f} -> {line['loadAfter']:.1f}",
          flush=True)


def finished(out: Path) -> set[tuple[str, str]]:
    if not out.exists():
        return set()
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {(r.get("case"), r.get("state")) for r in rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("--case", action="append", help='"<subset>-<content>/<hzp|hfp>", e.g. "uo2-3.1/hzp"')
    ap.add_argument("--out", type=Path, default=RESULTS)
    ap.add_argument("--dry", action="store_true", help="print the cases and run nothing")
    ap.add_argument("--smoke", default=None, help="particles,batches,inactive for a test run; only with an --out other than the default file")
    args = ap.parse_args(argv)

    plan = dc.cases()
    if args.smoke:
        if args.out.resolve() == RESULTS.resolve():
            raise SystemExit("--smoke cannot write to the default results file")
        particles, batches, inactive = (int(x) for x in args.smoke.split(","))
    ids = list(plan) if args.all else args.case
    for cid in ids:
        if cid not in plan:
            raise SystemExit(f"{cid} is not a case (see doppler_cases.py)")

    if args.dry:
        for cid in ids:
            run_case(dict(plan[cid]), args.out, dry=True)
        return 0

    done = finished(args.out)
    for cid in ids:
        spec = dict(plan[cid])
        key = (spec["case"], spec["state"])
        if args.smoke:
            spec["particles"], spec["batches"], spec["inactive"] = particles, batches, inactive
        elif key in done:
            if args.all:
                print(f"{cid}: already in {args.out.name}, skipped", flush=True)
                continue
            raise SystemExit(f"{cid} is already in {args.out}; refusing to run it again")
        if args.all:
            cmd = [sys.executable, "-m", "pipeline.openmc.doppler_run", "--case", cid, "--out", str(args.out)]
            if args.smoke:
                cmd += ["--smoke", args.smoke]
            subprocess.run(cmd, check=True, cwd=REPO_ROOT)
            continue
        run_case(spec, args.out, dry=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
