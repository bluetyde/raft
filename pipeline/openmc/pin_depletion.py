"""Deplete the standard JSI TRIGA fuel pin (pin_cell.py unit cell) and tabulate fuel number densities against burnup.

Output: pipeline/openmc/data/jsi_fuel_depleted.json, the fuel composition at each burnup step (MWd/kg of initial heavy metal),
for core_model.py --burnup (every element given the same burnup: a labelled calibration, see docs/validation/m2-burnup.md).

Choices (all labelled, none from a JSI source):
- specific power 14 W/g(HM): 250 kW over ~64 elements of 277 g U (NET 2024 Table 1), i.e. continuous full-power operation;
- fuel and every other material at 294 K during depletion (the real fuel runs hotter at 250 kW);
- after each step the zero-power, xenon-free state of the Monday excess-reactivity measurements is approximated by
  removing I-135 and Xe-135 and moving Pm-149 into Sm-149 (a weekend's decay);
- chain: OpenMC's ENDF/B-VIII.0 thermal-spectrum chain (openmc.org/data), path in $OPENMC_CHAIN_FILE or --chain.

Run in the openmc-vr env (WSL):  python -m pipeline.openmc.pin_depletion
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path

from pipeline.openmc import pin_cell

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "pipeline" / "openmc" / "data" / "jsi_fuel_depleted.json"
DEFAULT_CHAIN = "/root/nuclear_data/chains/chain_endfb80_pwr.xml"
SPECIFIC_POWER_W_PER_G = 14.0
STEPS_MWD_PER_KG = [0.25, 0.25, 0.5, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]  # to 28
DIRECT_NUCLIDES = ["U234", "U235", "U236", "U238", "Np237", "Pu238", "Pu239", "Pu240", "Pu241", "Pu242", "Am241",
                   "Xe135", "Sm149", "Sm151", "Gd155", "Gd157", "Nd143", "Rh103", "Cs133", "Eu155"]
MIN_DENSITY = 1e-12                                # atoms/b-cm kept in the table


def xenon_free(dens: dict[str, float]) -> dict[str, float]:
    """The Monday state: no I-135 or Xe-135, Pm-149 decayed to Sm-149."""
    d = dict(dens)
    d.pop("I135", None)
    d.pop("Xe135", None)
    d["Sm149"] = d.get("Sm149", 0.0) + d.pop("Pm149", 0.0)
    return d


def deplete(chain: str, particles: int, batches: int, inactive: int, workdir: Path) -> Path:
    """Run the depletion in `workdir`; returns the path of OpenMC's depletion_results.h5 (kept, so tabulate() can be re-run)."""
    import openmc
    import openmc.deplete
    import openmc.mgxs

    d = json.loads(pin_cell.DATA.read_text(encoding="utf-8"))
    model = pin_cell.build_model(d, 294.0, particles, batches, inactive)
    fuel = next(m for m in model.materials if m.name == "U-ZrH1.6")
    r = d["radiiCm"]
    fuel.volume = math.pi * (r["fuel"] ** 2 - r["zrRod"] ** 2) * 2.0      # the unit cell is 2 cm tall
    fuel.depletable = True
    hm_g = sum(fuel.get_mass(n) for n in ("U235", "U238"))
    workdir.mkdir(parents=True, exist_ok=True)
    cwd = os.getcwd()
    os.chdir(workdir)
    try:
        # reaction rates from a fine-group flux spectrum (CCFE-709) for most nuclides; the ones that matter most tallied directly
        opts = {"energies": openmc.mgxs.GROUP_STRUCTURES["CCFE-709"], "nuclides": DIRECT_NUCLIDES,
                "reactions": ["fission", "(n,gamma)"]}
        op = openmc.deplete.CoupledOperator(model, chain, normalization_mode="fission-q",
                                            reaction_rate_mode="flux", reaction_rate_opts=opts)
        integ = openmc.deplete.CECMIntegrator(op, STEPS_MWD_PER_KG, power=SPECIFIC_POWER_W_PER_G * hm_g,
                                              timestep_units="MWd/kg")
        integ.integrate()
    finally:
        os.chdir(cwd)
    (workdir / "fuel_id.txt").write_text(str(fuel.id), encoding="utf-8")
    return workdir / "depletion_results.h5"


def tabulate(results: Path, meta: dict) -> dict:
    import openmc
    import openmc.deplete

    res = openmc.deplete.Results(str(results))
    fuel_id = (results.parent / "fuel_id.txt").read_text(encoding="utf-8").strip()
    burnups = [0.0]
    for s in STEPS_MWD_PER_KG:
        burnups.append(burnups[-1] + s)
    if len(res) != len(burnups):
        raise ValueError(f"{len(res)} result steps, expected {len(burnups)}")
    _, keff = res.get_keff()
    series = {n: res.get_atoms(fuel_id, n, nuc_units="atom/b-cm")[1] for n in res[0].index_nuc}
    rows = []
    for i, bu in enumerate(burnups):
        dens = {n: float(v[i]) for n, v in series.items() if v[i] > MIN_DENSITY}
        rows.append({"burnupMWdPerKg": bu, "kInfOperating": [float(keff[i][0]), float(keff[i][1])],
                     "atomDensityPerBarnCm": xenon_free(dens)})
    return {"description": __doc__.splitlines()[0], "specificPowerWPerG": SPECIFIC_POWER_W_PER_G, "openmc": openmc.__version__,
            "labels": "calibration input, not measured; see the module docstring", **meta, "steps": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--chain", default=os.environ.get("OPENMC_CHAIN_FILE", DEFAULT_CHAIN))
    ap.add_argument("--particles", type=int, default=5000)
    ap.add_argument("--batches", type=int, default=50)
    ap.add_argument("--inactive", type=int, default=10)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--quick", action="store_true", help="testing only: 1000 particles x 20 batches")
    ap.add_argument("--workdir", type=Path, default=Path(tempfile.gettempdir()) / "vr_pin_depletion",
                    help="where depletion_results.h5 is kept")
    ap.add_argument("--tabulate-only", action="store_true", help="re-tabulate an existing --workdir without re-running")
    a = ap.parse_args(argv)
    if a.quick:
        a.particles, a.batches, a.inactive = 1000, 20, 5
    results = a.workdir / "depletion_results.h5"
    if not a.tabulate_only:
        results = deplete(a.chain, a.particles, a.batches, a.inactive, a.workdir)
    meta = {"chain": Path(a.chain).name, "particles": a.particles, "batches": a.batches, "inactive": a.inactive}
    rep = tabulate(results, meta)
    a.out.write_bytes((json.dumps(rep, indent=1) + "\n").encode("utf-8"))
    for row in rep["steps"]:
        k, s = row["kInfOperating"]
        print(f"{row['burnupMWdPerKg']:5.2f} MWd/kg  k_inf {k:.5f} +- {s:.5f}  U235 {row['atomDensityPerBarnCm']['U235']:.4e}  "
              f"nuclides {len(row['atomDensityPerBarnCm'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
