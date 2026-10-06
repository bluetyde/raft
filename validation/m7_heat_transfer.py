"""M7: does a temperature-dependent heat transfer law explain the measured power ascension?

Implements docs/validation/m7-heat-transfer-protocol.md exactly (second protocol, written before any run of it; it follows
m7-power-ascension-protocol.md and its results). Read it first: the family, the split, the bands and the decision rule are fixed
there, and nothing here may change after results are seen (a change is a new dated protocol).

Law L1:  hA(dT) = h0 * (dT / 100 K)^n,  Q = hA * dT = P  =>  dT = (P * (100 K)^n / h0)^(1 / (1 + n))
Law L0:  constant hA (n = 0), refitted on the same two states, as the baseline.

Fitted to the measured power defect at states 3 and 7 only; scored on held-out states 4, 5, 6 (reactivity and temperature shape),
state 2 (extrapolation) and the return leg (information only).

NOTE (2026-10-06): run once on the libraries as shipped then (constant hA 3000 W/K). The libraries now carry the fitted heat transfer law
(thermal.hA.exponent); this script reads only the scalar hA, so re-running it on them is not the comparison the protocol describes.

Run from the repo root:  python -m validation.m7_heat_transfer [--out PATH]
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path

from validation import m7_power_ascension as base

REPO_ROOT = base.REPO_ROOT
OUT = REPO_ROOT / "validation" / "m7_heat_transfer_report.json"

DT_REF = 100.0                      # K, the reference temperature difference of h0
CALIBRATION = (3, 7)                # 1-based states the law is fitted to
HELD_OUT = (4, 5, 6)                # interpolation states: A2 and C2
EXTRAPOLATION = 2                   # state 2: X
RETURN_LEG = (8, 9, 10)             # information only
N_PHYSICAL = (0.0, 0.5)
A2_GOOD = (0.10, 8.0)               # (fraction of the measured value, floor in pcm): good if error <= max of the two
A2_PLAUSIBLE = (0.25, 20.0)
RANK = base.LABEL_ORDER


# ---------------------------------------------------------------- the law

def delta_t(p_w: float, h0: float, n: float) -> float:
    """Fuel-to-pool temperature difference at power p_w for hA = h0 (dT / 100 K)^n."""
    return (p_w * DT_REF**n / h0) ** (1.0 / (1.0 + n))


def law_states(lib, powers_kw: list[float], t0_k: float, rising: bool, h0: float, n: float) -> list[dict]:
    """T_fuel, feedback and power defect at each state (state 1 is the reference), as base.model_states but with the law."""
    pool = base.pool_temperatures(len(powers_kw), t0_k, rising)
    rows = []
    for p_kw, tc in zip(powers_kw, pool):
        tf = tc + delta_t(p_kw * 1e3, h0, n)
        rho_fb = (lib.fuel_temp(tf) + lib.cool_temp(tc)) * base.PCM
        rows.append({"powerKW": p_kw, "tFuelK": tf, "tPoolK": tc, "rhoFbPcm": rho_fb})
    ref = rows[0]["rhoFbPcm"]
    for r in rows:
        r["defectPcm"] = -(r["rhoFbPcm"] - ref)
    return rows


# ---------------------------------------------------------------- calibration

def _bisect(f, lo: float, hi: float, iters: int = 200) -> float:
    """Root of a function that changes sign on [lo, hi] (geometric mean steps when both ends are positive)."""
    flo = f(lo)
    for _ in range(iters):
        mid = (lo * hi) ** 0.5 if lo > 0 and hi > 0 else 0.5 * (lo + hi)
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo * hi) ** 0.5 if lo > 0 and hi > 0 else 0.5 * (lo + hi)


def calibrate_law(lib, powers_kw, t0_k, rising, targets: dict[int, float]) -> tuple[float, float] | None:
    """(h0, n) at which the model's defect equals the measured one at both calibration states, or None."""
    s_lo, s_hi = CALIBRATION

    def defect(h0, n, state):
        return law_states(lib, powers_kw, t0_k, rising, h0, n)[state - 1]["defectPcm"]

    def h0_for(n):
        """For a given n, h0 fixes the top state's defect (the defect falls as h0 rises)."""
        # bracket by the top state's temperature difference, from 1 K to 2000 K (beyond that a table that clamps goes flat)
        p_top = powers_kw[s_hi - 1] * 1e3
        lo, hi = p_top * DT_REF**n / 2000.0 ** (1.0 + n), p_top * DT_REF**n
        if not (defect(hi, n, s_hi) <= targets[s_hi] <= defect(lo, n, s_hi)):
            return None
        return _bisect(lambda h: defect(h, n, s_hi) - targets[s_hi], lo, hi)

    def residual(n):
        h0 = h0_for(n)
        return None if h0 is None else defect(h0, n, s_lo) - targets[s_lo]

    grid = [-0.9 + 0.1 * i for i in range(40)]           # n from -0.9 to 3.0
    prev = None
    for n in grid:
        r = residual(n)
        if r is not None and prev is not None and prev[1] is not None and (r > 0) != (prev[1] > 0):
            n_root = _bisect_n(residual, prev[0], n)
            return h0_for(n_root), n_root
        prev = (n, r)
    return None


def _bisect_n(residual, lo: float, hi: float, iters: int = 100) -> float:
    rlo = residual(lo)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        rm = residual(mid)
        if rm is None:
            break
        if (rm > 0) == (rlo > 0):
            lo, rlo = mid, rm
        else:
            hi = mid
    return 0.5 * (lo + hi)


def refit_constant_hA(lib, powers_kw, t0_k, rising, targets: dict[int, float]) -> float:
    """L0: the constant hA that best fits both calibration states (least squares on the relative errors)."""

    def objective(log_h):
        rows = base.model_states(lib, powers_kw, t0_k, rising, math.exp(log_h))
        return sum((rows[s - 1]["defectPcm"] / targets[s] - 1.0) ** 2 for s in CALIBRATION)

    lo, hi = math.log(1.0), math.log(1e7)
    g = (math.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - g * (b - a), a + g * (b - a)
    for _ in range(200):
        if objective(c) < objective(d):
            b = d
        else:
            a = c
        c, d = b - g * (b - a), a + g * (b - a)
    return math.exp(0.5 * (a + b))


# ---------------------------------------------------------------- metrics

def label_state_defect(model: float, measured: float) -> str:
    err = abs(model - measured)
    if err <= max(A2_GOOD[0] * abs(measured), A2_GOOD[1]):
        return "good"
    if err <= max(A2_PLAUSIBLE[0] * abs(measured), A2_PLAUSIBLE[1]):
        return "plausible"
    return "fails"


def theta(values: list[float], state: int) -> float:
    peak = base.PEAK_STATE - 1
    return (values[state - 1] - values[0]) / (values[peak] - values[0])


def law_metrics(meas: dict, rows: list[dict]) -> dict:
    """A2, C2, X, E and the return leg for one set of model rows."""
    m_defect = meas["defectPcm"]
    m_temp = meas["fuelTempC"]
    t_model = [r["tFuelK"] for r in rows]

    a2 = [label_state_defect(rows[s - 1]["defectPcm"], m_defect[s - 1]) for s in HELD_OUT]
    c2_diffs = [abs(theta(t_model, s) - theta(m_temp, s)) for s in HELD_OUT]
    s2 = EXTRAPOLATION
    x_a = label_state_defect(rows[s2 - 1]["defectPcm"], m_defect[s2 - 1])
    x_c = base.label_diff("C", abs(theta(t_model, s2) - theta(m_temp, s2)))
    peak = base.PEAK_STATE - 1
    model_rise = t_model[peak] - t_model[0]
    return {
        "A2": {"label": max(a2, key=RANK.get), "perState": {str(s): {"model": rows[s - 1]["defectPcm"], "measured": m_defect[s - 1], "label": lab} for s, lab in zip(HELD_OUT, a2)}},
        "C2": {"maxAbsDiff": max(c2_diffs), "label": base.label_diff("C", max(c2_diffs))},
        "X": {"defect": x_a, "tempShape": x_c, "modelDefectPcm": rows[s2 - 1]["defectPcm"], "measuredDefectPcm": m_defect[s2 - 1]},
        "E": {"peakingFactor": (m_temp[peak] - m_temp[0]) / model_rise, "modelMeanRiseAtPeakK": model_rise, "measuredRiseAtPeakK": m_temp[peak] - m_temp[0]},
        "returnLeg": [
            {
                "state": s,
                "powerKW": rows[s - 1]["powerKW"],
                "defectLabel": label_state_defect(rows[s - 1]["defectPcm"], m_defect[s - 1]),
                "thetaDiff": abs(theta(t_model, s) - theta(m_temp, s)),
            }
            for s in RETURN_LEG
        ],
    }


# ---------------------------------------------------------------- one sensitivity combination

def evaluate_case(lib, meas: dict, t0_k: float, powers_kw: list[float], rising: bool) -> dict:
    targets = {s: meas["defectPcm"][s - 1] for s in CALIBRATION}
    hA0 = refit_constant_hA(lib, powers_kw, t0_k, rising, targets)
    out = {"L0": {"hA": hA0, **law_metrics(meas, base.model_states(lib, powers_kw, t0_k, rising, hA0))}}
    fit = calibrate_law(lib, powers_kw, t0_k, rising, targets)
    if fit is None:
        out["L1"] = {"note": "no (h0, n) reproduces both calibration states"}
    else:
        h0, n = fit
        out["L1"] = {"h0": h0, "n": n, "nPhysical": N_PHYSICAL[0] <= n <= N_PHYSICAL[1], **law_metrics(meas, law_states(lib, powers_kw, t0_k, rising, h0, n))}
    return out


# ---------------------------------------------------------------- the run

def summarise(cases: list[dict], law: str) -> dict:
    got = [c[law] for c in cases if "A2" in c[law]]
    if len(got) != len(cases):
        return {"computed": False, "combinationsWithoutFit": len(cases) - len(got)}
    s = {
        "computed": True,
        "A2": {"worst": base.worst([g["A2"]["label"] for g in got]), "best": base.best([g["A2"]["label"] for g in got])},
        "C2": {"maxAbsDiff": max(g["C2"]["maxAbsDiff"] for g in got), "worst": base.worst([g["C2"]["label"] for g in got]), "best": base.best([g["C2"]["label"] for g in got])},
        "X": {"defectWorst": base.worst([g["X"]["defect"] for g in got]), "tempShapeWorst": base.worst([g["X"]["tempShape"] for g in got])},
        "E": {"min": min(g["E"]["peakingFactor"] for g in got), "max": max(g["E"]["peakingFactor"] for g in got)},
    }
    if law == "L1":
        s["N"] = {"min": min(g["n"] for g in got), "max": max(g["n"] for g in got), "allPhysical": all(g["nPhysical"] for g in got)}
    return s


def adoption(summary: dict) -> dict:
    """The protocol's rule for one library; the overall decision needs both cores to pass."""
    l0, l1 = summary["L0"], summary["L1"]
    if not l1["computed"]:
        return {"adopt": False, "reasons": ["no fit in some combinations"]}
    reasons = []
    ok = ("good", "plausible")
    if l1["A2"]["worst"] not in ok:
        reasons.append(f"A2 {l1['A2']['worst']}")
    if l1["C2"]["worst"] not in ok:
        reasons.append(f"C2 {l1['C2']['worst']}")
    if "fails" in (l1["X"]["defectWorst"], l1["X"]["tempShapeWorst"]):
        reasons.append("extrapolation to state 2 fails")
    if not l1["N"]["allPhysical"]:
        reasons.append(f"n outside {N_PHYSICAL} (range {l1['N']['min']:.2f} to {l1['N']['max']:.2f})")
    improvement = l0["computed"] and l1["C2"]["maxAbsDiff"] <= 0.5 * l0["C2"]["maxAbsDiff"] and RANK[l1["A2"]["worst"]] <= RANK[l0["A2"]["worst"]]
    if not improvement:
        reasons.append("not an improvement over a constant hA refitted on the same states")
    return {"adopt": not reasons, "improvementOverL0": improvement, "reasons": reasons}


def run(libs: dict, meas: dict | None = None) -> dict:
    meas = meas or base.load_measured()
    t0_options = {"T0=25.8C(Table1)": meas["fuelTempC"][0] + base.K0, "T0=30.8C(Table2)": meas["fuelTempC_table2_first_row"] + base.K0}
    axes = {"pCalculated": meas["pCalculatedKW"], "pIndicated": meas["pIndicatedKW"]}
    pools = {"pool-constant": False, "pool-rising-6K": True}

    report: dict = {"protocol": "docs/validation/m7-heat-transfer-protocol.md", "libraries": {}}
    for name, lib in libs.items():
        cases = []
        for (t0_label, t0), (axis_label, powers), (pool_label, rising) in itertools.product(t0_options.items(), axes.items(), pools.items()):
            cases.append({"case": [t0_label, axis_label, pool_label], **evaluate_case(lib, meas, t0, powers, rising)})
        summary = {law: summarise(cases, law) for law in ("L0", "L1")}
        report["libraries"][name] = {"id": lib.id, "status": lib.status, "summary": summary, "adoption": adoption(summary), "cases": cases}
    both = all(e["adoption"]["adopt"] for e in report["libraries"].values())
    report["adoptAsCandidate"] = both
    return report


def print_summary(report: dict) -> None:
    print("protocol:", report["protocol"])
    for name, e in report["libraries"].items():
        print(f"\n{name} ({e['id']}, {e['status']})")
        for law in ("L0", "L1"):
            s = e["summary"][law]
            if not s["computed"]:
                print(f"  {law}: no fit in {s['combinationsWithoutFit']} combinations")
                continue
            extra = f"  n {s['N']['min']:.2f} to {s['N']['max']:.2f} (physical: {s['N']['allPhysical']})" if law == "L1" else ""
            print(f"  {law}: A2 {s['A2']['worst']}  C2 {s['C2']['worst']} (max {s['C2']['maxAbsDiff']:.3f})  X {s['X']['defectWorst']}/{s['X']['tempShapeWorst']}  peaking {s['E']['min']:.2f}-{s['E']['max']:.2f}{extra}")
        a = e["adoption"]
        print(f"  adopt: {a['adopt']}  {'; '.join(a['reasons'])}")
    print(f"\nadopt as a candidate (both cores): {report['adoptAsCandidate']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    libs = {name: base.load_library(path) for name, path in base.LIBRARIES.items()}
    report = run(libs)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
