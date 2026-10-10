"""The OpenMC cases that build the BEAVRS hot zero power library (M8 step 3, docs/m8-format-fit-check.md).

Pure Python (no OpenMC import), so it can be tested anywhere. The cases follow the reduced rod grid decided on 2026-10-07: each of the nine
control banks at 0, 76 and 152 steps withdrawn (a third-point grid of 228 steps) beside the reference, and bank D also at 228. Every case
changes one thing from the reference (the benchmark's hot zero power configuration) except the joint checks, which move several banks. More
points can be added later; finished cases are reused.

  id            what changes from the reference
  REF           nothing (with the IFP tallies for beta_eff and the generation time)
  R-<bank>-<n>  that bank at n steps withdrawn (n = 0, 76, 152; bank D also 228)
  TF-<K>        fuel temperature only (500, 700, 900 K)
  TC-<K>        moderator temperature and density only (500, 540, 600, 620 K; water at 15.5 MPa)
  B-<ppm>       boron concentration (300, 600, 1300, 1600 ppm)
  J-W2, W4, W7  banks D, C (and B, A) (and SE, SD, SC) fully in, at the reference boron: joint checks
  J-B4, J-B7    the same banks in as W4 and W7, at the measured critical boron (686 and 508 ppm)
"""
from __future__ import annotations

import subprocess
from collections import OrderedDict
from pathlib import Path

BEAVRS_HEAD = "1ccae04"                  # the mit-crpg/BEAVRS commit every protocol and the sweep fix (docs/validation/m8-beavrs-hzp-protocol.md)
T_REF = 566.483                       # K, 560 F
BORON_REF = 975.0                     # ppm
STEPS_FULL = 228
REF_STEPS = {"A": 228, "B": 228, "C": 228, "D": 213, "SA": 228, "SB": 228, "SC": 228, "SD": 228, "SE": 228}
BANKS = ["A", "B", "C", "D", "SA", "SB", "SC", "SD", "SE"]
ROD_STEPS = (0, 76, 152)
FUEL_T = (500.0, 700.0, 900.0)
WATER_T = (500.0, 540.0, 600.0, 620.0)
BORON = (300.0, 600.0, 1300.0, 1600.0)
INSERT_ORDER = ["D", "C", "B", "A", "SE", "SD", "SC"]         # the benchmark's insertion sequence
SETTINGS = {"particles": 60000, "batches": 300, "inactive": 100}
MESH = {"dimension": [19, 19, 10], "zLowerCm": 36.748, "zUpperCm": 402.508}     # the core lattice (with baffle ring), the active fuel height


def _case(role, steps=None, boron=BORON_REF, t_fuel=None, t_water=None, ifp=False):
    s = dict(REF_STEPS)
    s.update(steps or {})
    return {"role": role, "steps": s, "boron": boron, "tFuel": t_fuel, "tWater": t_water, "ifp": ifp, **SETTINGS}


def sweep_cases() -> "OrderedDict[str, dict]":
    out: "OrderedDict[str, dict]" = OrderedDict()
    out["REF"] = _case("reference", ifp=True)
    for b in BANKS:
        for n in ROD_STEPS:
            out[f"R-{b}-{n}"] = _case("rod", {b: n})
    out["R-D-228"] = _case("rod", {"D": 228})
    for t in FUEL_T:
        out[f"TF-{int(t)}"] = _case("fuelTemp", t_fuel=t)
    for t in WATER_T:
        out[f"TC-{int(t)}"] = _case("coolantTemp", t_water=t)
    for c in BORON:
        out[f"B-{int(c)}"] = _case("boron", boron=c)
    for n, name in ((2, "W2"), (4, "W4"), (7, "W7")):
        out[f"J-{name}"] = _case("joint", {b: 0 for b in INSERT_ORDER[:n]})
    out["J-B4"] = _case("joint", {b: 0 for b in INSERT_ORDER[:4]}, boron=686.0)
    out["J-B7"] = _case("joint", {b: 0 for b in INSERT_ORDER[:7]}, boron=508.0)
    return out


def check_beavrs_head(beavrs_dir: Path, expected: str | None = None) -> str:
    """The clone the runners import the model from must be at the commit the protocols fix; returns it, else raises."""
    want = expected or BEAVRS_HEAD
    head = subprocess.run(["git", "-C", str(beavrs_dir), "rev-parse", f"--short={len(want)}", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    if head != want:
        raise RuntimeError(f"the BEAVRS clone {beavrs_dir} is at {head}, the protocols fix {want}")
    return head


def rod_fraction(steps: int) -> float:
    """Fraction withdrawn, the library's rod axis."""
    return steps / STEPS_FULL
