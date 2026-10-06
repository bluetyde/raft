"""M7: ZrH nuclear data, temperature treatment and effective fuel temperature as explanations of the weak core 134 feedback.

Implements docs/validation/m7-core134-data-protocol.md exactly (ninth protocol, written before any run of it). Read it first: parts P, D, C and W, the
bands and the decision process are fixed there, and nothing here may change after results are seen (a change is a new dated protocol).

P  pin-cell runs with the current temperature treatment and with `nearest` (pipeline/openmc/results/core134_pincell_p1.json, _p2.json)
D  the same pin cell with ENDF/B-VII.1 (core134_pincell_vii1.json); only if the download was approved, otherwise "not run"
C  the reactivity-effective fuel temperature factor kappa from the core 134 library's shape arrays (no OpenMC)
W  what-ifs: the library's fuel table with Table IX temperatures scaled by kappa (and the data factor, if part D was run)

Clarifications made while implementing, none of which changes a band: the P2 run set also contains 294 K (its own baseline for the differences of
reactivity); part C leaves out the bin below the core, whose volume for the regular elements is nominal (they hold no fuel there) and which holds only
part of the fuelled followers' fuel.

Run from the repo root:  python -m validation.m7_core134_data [--out PATH]
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

from physics_ref.library import Table
from validation import m7_core134_conversion as cv
from validation import m7_fuel_coefficient as fc
from validation import m7_hot_element as he
from validation import m7_power_ascension as base

REPO_ROOT = base.REPO_ROOT
RESULTS = REPO_ROOT / "pipeline" / "openmc" / "results"
P1, P2, VII1 = RESULTS / "core134_pincell_p1.json", RESULTS / "core134_pincell_p2.json", RESULTS / "core134_pincell_vii1.json"
FUEL = REPO_ROOT / "pipeline" / "openmc" / "data" / "jsi_standard_fuel.json"
LIBRARY = REPO_ROOT / "libraries" / "triga-jsi-134-openmc"
OUT = REPO_ROOT / "validation" / "m7_core134_data_report.json"

R_TEMPS = (400.0, 500.0, 600.0)
R_SPREAD = 0.08
SMOOTH_TOL = 0.25
D_GOOD = (0.95, 1.05)
D_PART = 0.05
KAPPA_LARGE, KAPPA_PARTIAL = 1.35, 1.05
POWER_P = (2.0, 1.0, 3.0)                  # weights F^p V; the first is the primary
EXPONENTS = (0.22, 0.0)                    # n of the heat transfer law; the first is the primary
PARTS = ("full", "radial", "axial")
PCM = base.PCM


# ---------------------------------------------------------------- pin-cell runs (P and D)

def load_pincell(path: Path) -> dict[float, dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return {r["T"]: {"rho": r["rhoPcm"], "sigma": r["rhoUncPcm"]} for r in d["rows"]}


def reference_deltas() -> dict[float, float]:
    ref = json.loads(FUEL.read_text(encoding="utf-8"))["referenceAlpha"]
    by_t = dict(zip(ref["temperaturesK"], ref["rhoPcm"]))
    return {t: v - by_t[294.0] for t, v in by_t.items()}


def delta(rows: dict, t: float) -> tuple[float, float]:
    """Delta rho (pcm) of a pin-cell run set against its own 294 K run, and its standard error."""
    a, b = rows[t], rows[294.0]
    return a["rho"] - b["rho"], (a["sigma"] ** 2 + b["sigma"] ** 2) ** 0.5


def p_metrics(p1: dict, p2: dict, ref: dict[float, float]) -> dict:
    ratios = {t: delta(p1, t)[0] / ref[t] for t in R_TEMPS}
    ratio_err = {t: delta(p1, t)[1] / abs(ref[t]) for t in R_TEMPS}
    spread = max(ratios.values()) - min(ratios.values())
    d400 = delta(p1, 400.0)[0]
    smooth = {}
    for t in (330.0, 372.0):
        expected = (t - 294.0) / (400.0 - 294.0)
        got = delta(p1, t)[0] / d400
        smooth[t] = {"fractionOf400": got, "linearExpectation": expected, "relativeDeparture": abs(got - expected) / expected, "within": abs(got - expected) / expected <= SMOOTH_TOL}
    effects = {}
    for t in (330.0, 372.0, 400.0, 500.0):
        d1, s1 = delta(p1, t)
        d2, s2 = delta(p2, t)
        diff, sig = d1 - d2, (s1 ** 2 + s2 ** 2) ** 0.5
        effects[t] = {"p1Pcm": d1, "p2Pcm": d2, "differencePcm": diff, "sigmaPcm": sig, "treatmentEffect": abs(diff) > 2.0 * sig}
    return {"R": ratios, "RError": ratio_err, "spread": spread, "constant": spread <= R_SPREAD, "smooth": smooth, "smoothAll": all(v["within"] for v in smooth.values()), "p2Effects": effects}


def d_metrics(vii1: dict, p1: dict, ref: dict[float, float]) -> dict:
    ratios = {t: delta(vii1, t)[0] / ref[t] for t in R_TEMPS}
    r8 = {t: delta(p1, t)[0] / ref[t] for t in R_TEMPS}
    mean_vii1, mean_viii = sum(ratios.values()) / len(ratios), sum(r8.values()) / len(r8)
    explains = all(D_GOOD[0] <= r <= D_GOOD[1] for r in ratios.values())
    part = (mean_vii1 - mean_viii) >= D_PART
    factors = {t: delta(vii1, t)[0] / delta(p1, t)[0] for t in R_TEMPS}
    return {"RVII1": ratios, "RVIII0": r8, "meanVII1": mean_vii1, "meanVIII0": mean_viii, "label": "explains" if explains else "part" if part else "not the explanation", "factorsVII1OverVIII0": factors}


# ---------------------------------------------------------------- part C: the effective fuel temperature

def bins_of(lib) -> dict:
    """Fission fraction and volume of every (element, in-core axial bin) at the reference state, and the bin and element indices."""
    s = lib.shapes
    elements, edges = s["bins"]["elements"], s["bins"]["axialEdgesCm"]
    A = len(edges) - 1
    arr = he.shape_array(lib, dict(lib.ref_rods), base.K0 + 21.6)
    vol = lib.arrays[s["volumes"]]
    in_core = [a for a in range(A) if edges[a] >= -19.05 - 1e-9]
    cells = [(e, a, arr[e * A + a], vol[e * A + a]) for e in range(len(elements)) for a in in_core if arr[e * A + a] > 0.0]
    return {"cells": cells, "elements": elements, "inCoreBins": in_core}


def kappa(cells: list[tuple], p: float, n: float, part: str) -> float:
    """Reactivity-effective fuel temperature rise over the volume-mean rise, for temperatures following the local power density F^(1/(1+n))
    and weights F^p V. `radial` averages each element over its bins first, `axial` averages each bin over the elements."""
    if part == "radial":
        by = {}
        for e, a, f, v in cells:
            by.setdefault(e, [0.0, 0.0])
            by[e][0] += f
            by[e][1] += v
        units = [(f, v) for f, v in by.values()]
    elif part == "axial":
        by = {}
        for e, a, f, v in cells:
            by.setdefault(a, [0.0, 0.0])
            by[a][0] += f
            by[a][1] += v
        units = [(f, v) for f, v in by.values()]
    else:
        units = [(f, v) for e, a, f, v in cells]
    total_f = sum(f for f, _ in units)
    total_v = sum(v for _, v in units)
    mean_density = total_f / total_v
    rel = [(f / v / mean_density, v) for f, v in units]
    raw = [(F ** (1.0 / (1.0 + n)), F, v) for F, v in rel]
    scale = sum(t * v for t, _, v in raw) / total_v               # so that the volume mean rise is 1
    num = sum(F ** p * (t / scale) * v for t, F, v in raw)
    den = sum(F ** p * v for _, F, v in raw)
    return num / den


def c_metrics(lib) -> dict:
    cells = bins_of(lib)["cells"]
    cases = []
    for p, n, part in itertools.product(POWER_P, EXPONENTS, PARTS):
        k = kappa(cells, p, n, part)
        cases.append({"p": p, "n": n, "part": part, "kappa": k, "label": "large" if k >= KAPPA_LARGE else "partial" if k >= KAPPA_PARTIAL else "none"})
    primary = next(c for c in cases if c["p"] == POWER_P[0] and c["n"] == EXPONENTS[0] and c["part"] == "full")
    ks = [c["kappa"] for c in cases]
    return {"primary": primary, "min": min(ks), "max": max(ks), "cases": cases, "volumeCells": len(cells)}


# ---------------------------------------------------------------- part W: the what-ifs

def whatif(lib, data: dict, kappa_value: float, data_factor: float | None = None) -> dict:
    """Labels of the loss at steps 1-7 with the mean fuel rise multiplied by kappa (the conversion divided by it) and, if given, the fuel table's reactivity
    multiplied by the data factor; and the fraction of the step 7 shortfall removed (against the library as it is, with the paper's conversion)."""
    use = lib
    if data_factor is not None:
        use = SimpleNamespace(fuel_temp=Table(list(lib.fuel_temp.xs), [y * data_factor for y in lib.fuel_temp.ys]), cool_temp=lib.cool_temp)
    gb, ga = data["conversion"]["gammaB"] / kappa_value, data["conversion"]["gammaA"] / kappa_value
    labels = cv.labels_for(use, data, gb, ga)
    measured = -data["steps"][7][5]
    base_loss = cv.loss_at(lib, data, data["conversion"]["gammaB"], 3, 7)
    loss = cv.loss_at(use, data, gb, 3, 7)
    return {"labels": labels, "step7Pcm": loss, "fractionOfShortfallRemoved": (loss - base_loss) / (measured - base_loss)}


def w_metrics(lib, data: dict, c: dict, d: dict | None) -> dict:
    k = c["primary"]["kappa"]
    out = {"W0": whatif(lib, data, 1.0), "W1": whatif(lib, data, k)}
    if d is not None:
        factor = sum(d["factorsVII1OverVIII0"].values()) / len(d["factorsVII1OverVIII0"])
        out["W2"] = whatif(lib, data, 1.0, factor)
        out["W3"] = whatif(lib, data, k, factor)
    else:
        out["W2"] = out["W3"] = {"status": "not computed (part D not run)"}
    return out


# ---------------------------------------------------------------- decision and run

def decide(p: dict, d: dict | None, c: dict, w: dict) -> dict:
    ok = ("good", "plausible")
    items = []
    if p["constant"] and p["smoothAll"]:
        items.append("1. OpenMC's temperature treatment is not responsible for the shortfall (P1 constant, the curve smooth)")
    else:
        items.append("1. a treatment artefact exists (P1 varying or the curve not smooth); record its size; a corrected library needs its own protocol")
    if d is None:
        items.append("2. part D not run (no ENDF/B-VII.1 download approved)")
    elif d["label"] == "not the explanation":
        items.append("2. the ENDF/B-VII.1 data do not explain the pin-cell deficit")
    else:
        items.append(f"2. the evaluation of the ZrH and nuclide data is a lever of the size found ({d['label']}); not adopted")
    if c["primary"]["label"] in ("large", "partial"):
        items.append(f"3. the uniform fuel temperature of the library is a known limit: kappa {c['primary']['kappa']:.2f} ({c['primary']['label']}); a transport test with per-element temperatures is the next protocol")
    else:
        items.append("3. the effective-temperature factor is negligible (kappa below 1.05)")
    if "labels" in w["W3"]:
        final = w["W3"]
        if final["labels"]["primary"]["worst"] in ok:
            items.append("4. the evaluation of the data and the temperature distribution together explain the weak feedback (W3 is good or plausible)")
        else:
            items.append(f"4. a residual remains with the data and the distribution together: {1.0 - final['fractionOfShortfallRemoved']:.0%} of the step 7 shortfall")
    else:
        w1 = w["W1"]
        items.append(f"4. W3 not computed (part D not run): a residual remains, {1.0 - w1['fractionOfShortfallRemoved']:.0%} of the step 7 shortfall after the effective temperature alone "
                     f"(W1 is {w1['labels']['primary']['worst']} in the primary line)")
    return {"items": items, "libraryChanged": False}


def run(lib, p1: dict, p2: dict, vii1: dict | None, data: dict | None = None) -> dict:
    data = data or fc.load_steps()
    ref = reference_deltas()
    p = p_metrics(p1, p2, ref)
    d = None if vii1 is None else d_metrics(vii1, p1, ref)
    c = c_metrics(lib)
    w = w_metrics(lib, data, c, d)
    return {"protocol": "docs/validation/m7-core134-data-protocol.md", "P": p, "D": d if d is not None else {"status": "not run"}, "C": c, "W": w, "decision": decide(p, d, c, w)}


def print_summary(r: dict) -> None:
    print("protocol:", r["protocol"])
    p = r["P"]
    print("  P1: R(T) =", {int(t): round(v, 3) for t, v in p["R"].items()}, f"+- {max(p['RError'].values()):.3f}; spread {p['spread']:.3f} -> {'constant' if p['constant'] else 'varying'}")
    print("  P1 smooth:", {int(t): (round(v["fractionOf400"], 3), round(v["linearExpectation"], 3), v["within"]) for t, v in p["smooth"].items()})
    print("  P2 effects (P1 - P2, pcm):", {int(t): (round(v["differencePcm"], 1), round(v["sigmaPcm"], 1), v["treatmentEffect"]) for t, v in p["p2Effects"].items()})
    d = r["D"]
    print("  D:", d if "status" in d else {k: d[k] for k in ("label", "meanVII1", "meanVIII0")})
    c = r["C"]
    pr = c["primary"]
    print(f"  C1: kappa {pr['kappa']:.3f} ({pr['label']}) primary p={pr['p']} n={pr['n']}; range {c['min']:.3f}-{c['max']:.3f}")
    print("     all:", [(x["p"], x["n"], x["part"][:3], round(x["kappa"], 3)) for x in c["cases"]])
    for k in ("W0", "W1", "W2", "W3"):
        v = r["W"][k]
        if "labels" in v:
            steps = "  ".join(f"{s['step']}:{s['modelPcm']:.0f}/{s['measuredPcm']:.0f}[{s['label'][0]}]" for s in v["labels"]["primary"]["perStep"])
            print(f"  {k}: primary {v['labels']['primary']['worst']} worst {v['labels']['worst']} best {v['labels']['best']}; step 7 {v['step7Pcm']:.0f} pcm, shortfall removed {v['fractionOfShortfallRemoved']:.0%}   {steps}")
        else:
            print(f"  {k}: {v['status']}")
    for item in r["decision"]["items"]:
        print("  decision:", item)


def main(argv: list[str] | None = None) -> int:
    from physics_ref.library import Library

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    report = run(Library(LIBRARY), load_pincell(P1), load_pincell(P2), load_pincell(VII1) if VII1.exists() else None)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
