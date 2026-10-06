"""M7: is the paper's thermocouple-to-mean-fuel-temperature conversion for core 134 supported by independent evidence?

Implements docs/validation/m7-core134-conversion-protocol.md exactly (eighth protocol, written before any run of it). Read it first: the three
computations C1-C3, the metrics G1-G4, the bands, the sensitivities and the decision process are fixed there, and nothing here may change after
results are seen (a change is a new dated protocol).

C1  the radial factor gamma_r recomputed from Table VIII (ring temperatures) and the core 134 loading
C2  the model's power factors of the A-1 and B-5 elements from the core 134 library's shape arrays, as temperature factors
C3  the conversion the library's feedback would need (a diagnostic, never applied) and the labels with the independent conversions

Run from the repo root:  python -m validation.m7_core134_conversion [--out PATH]
"""
from __future__ import annotations

import argparse
import copy
import csv
import itertools
import json
import math
from pathlib import Path

from validation import m7_fuel_coefficient as fc
from validation import m7_hot_element as he
from validation import m7_power_ascension as base

REPO_ROOT = base.REPO_ROOT
DATA = REPO_ROOT / "validation" / "data" / "jsi-core134"
GEOMETRY = REPO_ROOT / "pipeline" / "openmc" / "data" / "jsi_core_geometry.json"
LIBRARY = REPO_ROOT / "libraries" / "triga-jsi-134-openmc"
OUT = REPO_ROOT / "validation" / "m7_core134_conversion_report.json"

PAPER_GAMMA_R = {"A": 1.26, "B": 1.22}
PAPER_GAMMA_Z = 1.25
PAPER_GAMMA = {"A": 1.575, "B": 1.525}
LOCATION = {"A": "A-1", "B": "B-5"}               # the instrumented elements of Table IX
BANDS_G1 = (0.05, 0.10)
BANDS_G2 = (0.10, 0.20)
BANDS_G3 = ((0.90, 1.10), (0.80, 1.25))
T0_OPTIONS = (21.6, 20.0, 25.0)
WEIGHTS = ("count", "count-no-followers", "area")
POWERS = ("250", "125")
N_OPTIONS = (0.0, 0.22)
AXIAL_MODES = ("midplane", "three-bins")
RANK = base.LABEL_ORDER


def label_diff(d: float, bands: tuple[float, float]) -> str:
    return "good" if d <= bands[0] else "plausible" if d <= bands[1] else "differs"


def label_ratio(r: float) -> str:
    return "good" if BANDS_G3[0][0] <= r <= BANDS_G3[0][1] else "plausible" if BANDS_G3[1][0] <= r <= BANDS_G3[1][1] else "differs"


def worst(labels: list[str]) -> str:
    return max(labels, key=lambda s: {"good": 0, "plausible": 1, "fails": 2, "differs": 2}.get(s, 3))


def best(labels: list[str]) -> str:
    return min(labels, key=lambda s: {"good": 0, "plausible": 1, "fails": 2, "differs": 2}.get(s, 3))


# ---------------------------------------------------------------- C1: the radial factor from Table VIII

def load_rings() -> dict[str, dict[str, float | None]]:
    """{location: {"250": T, "125": T or None}} from Table VIII (cooling on)."""
    out = {}
    with open(DATA / "ring_temperatures.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out[r["location"]] = {"250": float(r["T_250kW_C"]), "125": float(r["T_125kW_C"]) if r["T_125kW_C"] else None}
    return out


def fuel_positions(loading: dict) -> tuple[list[str], list[str]]:
    """The 45 fuel elements' positions and the three fuelled followers' positions of core 134."""
    followers = [p for p, what in loading["other"].items() if "fuelled follower" in what]
    return sorted(loading["fuel"]), sorted(followers)


def ring_values(rings: dict, power: str) -> dict[str, float]:
    """The ring temperature of each ring A..E at one power: the mean of the locations given in that ring (the single value where only one is given)."""
    def vals(*locs):
        v = [rings[l][power] for l in locs if rings[l][power] is not None]
        return sum(v) / len(v)
    return {"A": vals("A-1"), "B": vals("B-2", "B-5"), "C": vals("C-8", "C-9"), "D": vals("D-11", "D-13"), "E": vals("E-14")}


def mean_temperature(values: dict[str, float], fuel: list[str], followers: list[str], weighting: str, radii: dict[str, float]) -> float:
    """Volume-averaged fuel temperature (C): the mean of the ring values over the fuel positions (the followers given their ring's value, or not
    counted), or the area integral of a piecewise linear T(r) through the ring radii (the paper integrated its Fig. 5 numerically)."""
    if weighting == "area":
        rs = [radii[r] for r in "ABCDE"]
        ts = [values[r] for r in "ABCDE"]
        total = 0.0
        for (r0, t0), (r1, t1) in zip(zip(rs, ts), zip(rs[1:], ts[1:])):
            n = 200
            for i in range(n):
                a, b = r0 + (r1 - r0) * i / n, r0 + (r1 - r0) * (i + 1) / n
                f = lambda r: (t0 + (t1 - t0) * (r - r0) / (r1 - r0)) * r
                total += 0.5 * (f(a) + f(b)) * (b - a)
        return total / (rs[-1] ** 2 / 2.0)
    positions = fuel + (followers if weighting == "count" else [])
    return sum(values[p[0]] for p in positions) / len(positions)


def gamma_r(rings: dict, fuel: list[str], followers: list[str], radii: dict[str, float], power: str, weighting: str, t0: float) -> dict[str, float]:
    vals = ring_values(rings, power)
    tbar = mean_temperature(vals, fuel, followers, weighting, radii)
    out = {}
    for ring, loc in LOCATION.items():
        t_loc = rings[loc][power] if rings[loc][power] is not None else rings["B-2"][power]      # B-5 is given at 250 kW only
        out[ring] = (t_loc - t0) / (tbar - t0)
    return {"A": out["A"], "B": out["B"], "meanC": tbar}


def c1(rings: dict, loading: dict, radii: dict) -> dict:
    fuel, followers = fuel_positions(loading)
    cases = []
    for t0, weighting, power in itertools.product(T0_OPTIONS, WEIGHTS, POWERS):
        g = gamma_r(rings, fuel, followers, radii, power, weighting, t0)
        labels = {r: label_diff(abs(g[r] - PAPER_GAMMA_R[r]), BANDS_G1) for r in "AB"}
        cases.append({"T0C": t0, "weighting": weighting, "powerKW": power, "gammaA": g["A"], "gammaB": g["B"], "meanFuelC": g["meanC"], "labelA": labels["A"], "labelB": labels["B"]})
    prim = cases[0]
    both = [c["labelA"] for c in cases] + [c["labelB"] for c in cases]
    return {"primary": prim, "worst": worst(both), "best": best(both), "gammaBRange": [min(c["gammaB"] for c in cases), max(c["gammaB"] for c in cases)],
            "gammaARange": [min(c["gammaA"] for c in cases), max(c["gammaA"] for c in cases)], "cases": cases}


# ---------------------------------------------------------------- C2: the model's power factors

def model_factors(lib, element: str, n: float, axial_mode: str) -> dict:
    s = lib.shapes
    elements, edges = s["bins"]["elements"], s["bins"]["axialEdgesCm"]
    A = len(edges) - 1
    rods = dict(lib.ref_rods)
    arr = he.shape_array(lib, rods, base.K0 + 21.6)
    powered = [e for e in range(len(elements)) if sum(arr[e * A:(e + 1) * A]) > 1e-12]
    e = elements.index(element)
    heights = [edges[a + 1] - edges[a] for a in range(A)]
    in_core = [a for a in range(A) if edges[a] >= -19.05 - 1e-9]                        # the bins of the active height (the first bin lies below the core)
    centre = next(a for a in range(A) if edges[a] <= 0.0 < edges[a + 1])
    f_r = sum(arr[e * A + a] for a in range(A)) * len(powered)
    length = sum(heights[a] for a in in_core)
    mean_density = sum(arr[e * A + a] for a in in_core) / length
    mid = [centre] if axial_mode == "midplane" else [centre - 1, centre, centre + 1]
    mid_density = sum(arr[e * A + a] for a in mid) / sum(heights[a] for a in mid)
    f_z = mid_density / mean_density
    expo = 1.0 / (1.0 + n)
    g_r, g_z = f_r ** expo, f_z ** expo
    return {"element": element, "n": n, "axial": axial_mode, "Fr": f_r, "Fz": f_z, "gammaR": g_r, "gammaZ": g_z, "gamma": g_r * g_z, "poweredElements": len(powered)}


def c2(lib) -> dict:
    cases = []
    for ring, (n, mode) in itertools.product("AB", itertools.product(N_OPTIONS, AXIAL_MODES)):
        m = model_factors(lib, LOCATION[ring].replace("-", ""), n, mode)
        d = abs(m["gamma"] / PAPER_GAMMA[ring] - 1.0)
        cases.append({"ring": ring, **m, "relativeDifference": d, "label": label_diff(d, BANDS_G2)})
    prim = {r: next(c for c in cases if c["ring"] == r and c["n"] == 0.0 and c["axial"] == "midplane") for r in "AB"}
    labels = [c["label"] for c in cases]
    return {"primary": prim, "worst": worst(labels), "best": best(labels), "cases": cases}


# ---------------------------------------------------------------- C3: implied conversion and the labels with independent ones

def with_gamma(data: dict, gamma_b: float, gamma_a: float) -> dict:
    d = copy.deepcopy(data)
    d["conversion"]["gammaB"], d["conversion"]["gammaA"] = gamma_b, gamma_a
    return d


def loss_at(lib, data: dict, gamma: float, column: int, step: int, profile: str = "linear") -> float:
    steps = data["steps"]
    t_mean = fc.mean_fuel_temps_k(steps, column, gamma, data["conditions"]["T0C"])
    w = [data["conditions"]["T0C"] + base.K0 + r for r in fc.water_rise(profile, steps)]
    return fc.model_loss_pcm(lib, t_mean, w)[step]


def implied_gamma(lib, data: dict, column: int, step: int) -> float | None:
    """The conversion at which the library's tables give the measured cumulative loss at one step (bisection; the loss falls as gamma rises)."""
    target = -data["steps"][step][5]
    lo, hi = 0.3, 4.0
    f = lambda g: loss_at(lib, data, g, column, step) - target
    if f(lo) < 0 or f(hi) > 0:
        return None
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
    return 0.5 * (lo + hi)


def labels_for(lib, data: dict, gamma_b: float, gamma_a: float) -> dict:
    d = with_gamma(data, gamma_b, gamma_a)
    cases = []
    for (gkey, col), profile in itertools.product((("gammaB", 3), ("gammaA", 2)), ("linear", "none", "cumulative")):
        a = fc.feedback_cases(lib, d, gkey, col, profile)
        cases.append({"gamma": gkey, "profile": profile, "A": a["A"]})
    w = [c["A"]["worst"] for c in cases]
    return {"gammaB": gamma_b, "gammaA": gamma_a, "primary": cases[0]["A"], "worst": base.worst(w), "best": base.best(w)}


def c3(lib, data: dict, c1_res: dict, c2_res: dict) -> dict:
    steps = range(1, 8)
    implied = {}
    for ring, col in (("B", 3), ("A", 2)):
        per = {s: implied_gamma(lib, data, col, s) for s in steps}
        vals = [v for v in per.values() if v is not None]
        complete = len(vals) == len(per)                                    # a mean over a partial set of steps is not the protocol's quantity
        mean = sum(vals) / len(vals) if complete else None
        implied[ring] = {"perStep": per, "mean": mean, "ratioToPaper": None if mean is None else mean / PAPER_GAMMA[ring],
                         "complete": complete, "partialMean": sum(vals) / len(vals) if vals and not complete else None}
        implied[ring]["label"] = "not computed" if mean is None else label_ratio(mean / PAPER_GAMMA[ring])
    routes = {
        "paper": (PAPER_GAMMA["B"], PAPER_GAMMA["A"]),
        "table8-radial-times-paper-axial": (c1_res["primary"]["gammaB"] * PAPER_GAMMA_Z, c1_res["primary"]["gammaA"] * PAPER_GAMMA_Z),
        "model-power-factors": (c2_res["primary"]["B"]["gamma"], c2_res["primary"]["A"]["gamma"]),
    }
    labelled = {k: labels_for(lib, data, gb, ga) for k, (gb, ga) in routes.items()}
    # the fraction of the shortfall at step 7 that an independent conversion removes (B ring, primary profile)
    measured = -data["steps"][7][5]
    base_loss = loss_at(lib, data, PAPER_GAMMA["B"], 3, 7)
    removed = {}
    for k, (gb, _) in routes.items():
        loss = loss_at(lib, data, gb, 3, 7)
        removed[k] = {"lossPcm": loss, "measuredPcm": measured, "fractionOfShortfallRemoved": (loss - base_loss) / (measured - base_loss)}
    return {"implied": implied, "routes": labelled, "step7": removed}


# ---------------------------------------------------------------- decision and run

def decide(c1_res: dict, c2_res: dict, c3_res: dict) -> dict:
    ok = ("good", "plausible")
    g1_ok = c1_res["primary"]["labelA"] in ok and c1_res["primary"]["labelB"] in ok
    g2_ok = all(c2_res["primary"][r]["label"] in ok for r in "AB")
    routes = c3_res["routes"]
    indep_ok = all(routes[k]["primary"]["worst"] in ok for k in ("table8-radial-times-paper-axial", "model-power-factors"))
    paper_ok = routes["paper"]["primary"]["worst"] in ok
    g3_differs = c3_res["implied"]["B"]["label"] == "differs"
    if c3_res["implied"]["B"]["label"] == "not computed":
        return {"case": None, "text": "G3 is incomplete (the implied conversion has no root at some step): the decision is not made on partial evidence", "removed": {}}
    removed = {k: v["fractionOfShortfallRemoved"] for k, v in c3_res["step7"].items() if k != "paper"}
    if g1_ok and g2_ok and indep_ok:
        return {"case": 1, "text": "the paper's conversion was too high; the feedback is consistent with the measurement with the independent conversion", "removed": removed}
    if g1_ok and g2_ok and g3_differs and not paper_ok:
        return {"case": 2, "text": "the paper's conversion is supported; the feedback is too weak by the implied factor; the next protocol tests OpenMC's fuel temperature treatment", "removed": removed}
    if not (g1_ok and g2_ok) and not indep_ok:
        return {"case": 3, "text": "the conversion is partly off but does not explain the shortfall; the fraction it removes at step 7 is in 'removed'", "removed": removed}
    return {"case": None, "text": "none of the protocol's cases applies as written; read the metrics", "removed": removed}


def run(lib, rings: dict, loading: dict, radii: dict, data: dict | None = None) -> dict:
    data = data or fc.load_steps()
    r1 = c1(rings, loading, radii)
    r2 = c2(lib)
    r3 = c3(lib, data, r1, r2)
    return {"protocol": "docs/validation/m7-core134-conversion-protocol.md", "G1": r1, "G2": r2, "G3G4": r3, "decision": decide(r1, r2, r3)}


def print_summary(r: dict) -> None:
    print("protocol:", r["protocol"])
    g1 = r["G1"]
    p = g1["primary"]
    print(f"  G1 (primary: T0 {p['T0C']}, {p['weighting']}, {p['powerKW']} kW): gamma_r A {p['gammaA']:.3f} [{p['labelA']}] (paper 1.26), B {p['gammaB']:.3f} [{p['labelB']}] (paper 1.22); mean fuel {p['meanFuelC']:.1f} C")
    print(f"     over the sensitivities: A {g1['gammaARange'][0]:.3f}-{g1['gammaARange'][1]:.3f}, B {g1['gammaBRange'][0]:.3f}-{g1['gammaBRange'][1]:.3f}; worst {g1['worst']} best {g1['best']}")
    g2 = r["G2"]
    for ring in "AB":
        m = g2["primary"][ring]
        print(f"  G2 {ring}: F_r {m['Fr']:.3f} F_z {m['Fz']:.3f} -> gamma_model {m['gamma']:.3f} (paper {PAPER_GAMMA[ring]}) diff {m['relativeDifference']:.1%} [{m['label']}]")
    print("     all combinations (n, axial):", [(c["ring"], c["n"], c["axial"][:3], round(c["gamma"], 3), c["label"]) for c in g2["cases"]], f"worst {g2['worst']} best {g2['best']}")
    c3r = r["G3G4"]
    for ring in "BA":
        im = c3r["implied"][ring]
        print(f"  G3 {ring}: implied conversion by step {{ {', '.join(f'{s}: {v:.2f}' if v else f'{s}: none' for s, v in im['perStep'].items())} }} mean {'incomplete' if im['mean'] is None else format(im['mean'], '.3f')} = {'n/a' if im['ratioToPaper'] is None else format(im['ratioToPaper'], '.2f')} x paper [{im['label']}]")
    for k, v in c3r["routes"].items():
        steps = "  ".join(f"{s['step']}:{s['modelPcm']:.0f}/{s['measuredPcm']:.0f}[{s['label'][0]}]" for s in v["primary"]["perStep"])
        print(f"  G4 {k} (gamma_B {v['gammaB']:.3f}): primary {v['primary']['worst']} worst {v['worst']} best {v['best']}   {steps}")
    print("  step 7 shortfall removed:", {k: f"{v['fractionOfShortfallRemoved']:.0%} (loss {v['lossPcm']:.0f} of {v['measuredPcm']:.0f})" for k, v in c3r["step7"].items()})
    print("  decision:", r["decision"])


def main(argv: list[str] | None = None) -> int:
    from physics_ref.library import Library

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    loading = json.loads((DATA / "loading_map.json").read_text(encoding="utf-8"))
    radii = json.loads(GEOMETRY.read_text(encoding="utf-8"))["grid"]["ringRadiiCm"]
    report = run(Library(LIBRARY), load_rings(), loading, radii)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
