"""M7: the model's feedback chain against the measured JSI steady power ascension.

Implements docs/validation/m7-power-ascension-protocol.md exactly (written before any comparison). Read that file first:
the metrics, the bands, the variants and the sensitivities are fixed there, and nothing here may be changed after results are
seen (a change is a new dated protocol).

Data: validation/data/jsi-steady-power/ (power_ascension.json, regulating_rod_core200.csv).
Model: the OpenMC libraries of cores 242 and 246, read through physics_ref.library (the Python reference engine's loader).

At each measured power the reactor is critical, so the reactivity the regulating rod adds equals the feedback reactivity lost
to heating. In the model each state is quasi-steady: T_fuel = T_pool + P / hA, and the feedback is read from the library's tables:

    rho_fb = fuelTemp(T_fuel) + coolantTemp(T_pool)         (library tables are absolute reactivity; pcm = 1e5 x)
    defect = -(rho_fb - rho_fb at the reference state)       (the reactivity the rod must add)

NOTE (2026-10-06): run once on the libraries as shipped then (constant hA 3000 W/K). The libraries now carry the fitted heat transfer law
(thermal.hA.exponent); this script reads only the scalar hA, so re-running it on them is not the comparison the protocol describes.

Run from the repo root:  python -m validation.m7_power_ascension [--out PATH]
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "validation" / "data" / "jsi-steady-power"
OUT = REPO_ROOT / "validation" / "m7_power_ascension_report.json"
LIBRARIES = {
    "core242": REPO_ROOT / "libraries" / "triga-jsi-242-openmc",
    "core246": REPO_ROOT / "libraries" / "triga-jsi-246-openmc",
}

PCM = 1e5
K0 = 273.15
POOL_RISE_K = 6.0          # pool case (ii): rises linearly with the state number to this at state 11 (protocol)
ROD_STEPS = (181, 900)     # Table A.1: step 181 = fully withdrawn (x = 1), step 900 = fully inserted (x = 0)
HELD_OUT = (3, 4, 5, 6)    # up-leg states (1-based) that are held out of V1 and used in metrics B and C
PEAK_STATE = 7             # 250 kW, the calibration state of V1 and the normaliser of metrics B and C

# bands: (good, plausible); the label is "fails" beyond plausible. Fixed in the protocol.
BANDS = {
    "A": ((0.8, 1.25), (0.5, 2.0)),          # ratio model / measured: inside the first interval = good, inside the second = plausible
    "B": (0.05, 0.10),                        # max absolute difference
    "C": (0.05, 0.10),
    "D": (0.05, 0.10),
}
LABEL_ORDER = {"good": 0, "plausible": 1, "fails": 2, "not computed": 3}


# ---------------------------------------------------------------- measured data

def load_measured() -> dict:
    d = json.loads((DATA / "power_ascension.json").read_text(encoding="utf-8"))
    states = d["states"]
    with open(DATA / "regulating_rod_core200.csv", encoding="utf-8", newline="") as f:
        rod = [(int(r["rod_step"]), float(r["integral_worth_pcm"])) for r in csv.DictReader(f)]
    peak = next(s for s in states if s["state"] == PEAK_STATE)
    return {
        "states": states,
        "pCalculatedKW": [s["table2"]["pCalculatedKW"] for s in states],
        "pIndicatedKW": [s["pIndicatedKW"] for s in states],
        "fuelTempC": [s["fuelTempC"] for s in states],
        "fuelTempC_table2_first_row": states[0]["table2"]["fuelTempC"],
        # the cumulative d_rho in the file is feedback-signed (negative); the power defect is its negative
        "defectPcm": [-s["cumulativeDRhoPcm"] for s in states],
        "powerDefectAtPeakPcm": d["powerDefectAtPeakPcm"],
        "rodCurve": rod,
        "peakIndex": states.index(peak),
    }


# ---------------------------------------------------------------- model

def load_library(path: Path):
    """The library through the Python reference engine's loader, with the attributes this script needs."""
    from physics_ref.library import Library

    return Library(path)


def pool_temperatures(n: int, t0_k: float, rising: bool) -> list[float]:
    """Pool temperature at each of the n states (protocol: constant, or rising linearly to T0 + 6 K at the last state)."""
    return [t0_k + (POOL_RISE_K * i / (n - 1) if rising else 0.0) for i in range(n)]


def model_states(lib, powers_kw: list[float], t0_k: float, rising: bool, hA: float | None = None) -> list[dict]:
    """T_fuel, feedback and power defect at each state (state 1 is the reference)."""
    if hA is None and getattr(lib, "hA_exponent", 0.0) != 0.0:
        raise ValueError(f"{lib.id} carries a temperature-dependent hA (exponent {lib.hA_exponent}); this protocol compared the libraries as shipped "
                         "on 2026-10-06 with a constant hA (3000 W/K), and its 'as shipped' numbers cannot be reproduced on this library")
    hA = lib.hA if hA is None else hA
    pool = pool_temperatures(len(powers_kw), t0_k, rising)
    rows = []
    for p_kw, tc in zip(powers_kw, pool):
        tf = tc + p_kw * 1e3 / hA
        rho_fb = (lib.fuel_temp(tf) + lib.cool_temp(tc)) * PCM
        rows.append({"powerKW": p_kw, "tFuelK": tf, "tPoolK": tc, "rhoFbPcm": rho_fb})
    ref = rows[0]["rhoFbPcm"]
    for r in rows:
        r["defectPcm"] = -(r["rhoFbPcm"] - ref)
    return rows


def calibrate_hA(lib, powers_kw, t0_k, rising, target_defect_pcm) -> float | None:
    """The hA at which the model's power defect at the peak state equals the measured one (V1). None if it cannot be reached."""

    def defect(hA):
        return model_states(lib, powers_kw, t0_k, rising, hA)[PEAK_STATE - 1]["defectPcm"]

    lo, hi = 1.0, 1e7            # defect falls as hA rises
    if not (defect(hi) <= target_defect_pcm <= defect(lo)):
        return None
    for _ in range(200):
        mid = (lo * hi) ** 0.5
        if defect(mid) > target_defect_pcm:
            lo = mid
        else:
            hi = mid
    return (lo * hi) ** 0.5


def rod_curve_model(lib, steps_worth: list[tuple[int, float]]) -> list[tuple[float, float]]:
    """(x, normalised inserted worth) of the library's regulating rod; W(x) = rho_rod(1) - rho_rod(x), normalised by W(0)."""
    rod = lib.rod_by_id["regulating"]
    top = rod.worth(1.0)
    total = top - rod.worth(0.0)
    return [(x, (top - rod.worth(x)) / total) for x, _ in ((_x(s), w) for s, w in steps_worth)]


def _x(step: int) -> float:
    lo, hi = ROD_STEPS
    return (hi - step) / (hi - lo)


# ---------------------------------------------------------------- metrics and labels

def label_A(ratio: float) -> str:
    (g_lo, g_hi), (p_lo, p_hi) = BANDS["A"]
    if g_lo <= ratio <= g_hi:
        return "good"
    if p_lo <= ratio <= p_hi:
        return "plausible"
    return "fails"


def label_diff(metric: str, diff: float) -> str:
    good, plausible = BANDS[metric]
    return "good" if diff <= good else "plausible" if diff <= plausible else "fails"


def metrics_for(meas: dict, rows: list[dict]) -> dict:
    """Metrics A, B and C for one set of model rows against the measured states (not D: it has no sensitivities)."""
    peak = PEAK_STATE - 1
    m_defect = meas["defectPcm"]
    ratio = rows[peak]["defectPcm"] / m_defect[peak]
    held = [i - 1 for i in HELD_OUT]
    b_diffs = [abs(rows[i]["defectPcm"] / rows[peak]["defectPcm"] - m_defect[i] / m_defect[peak]) for i in held]
    t_meas = meas["fuelTempC"]
    c_diffs = []
    for i in held:
        theta_model = (rows[i]["tFuelK"] - rows[0]["tFuelK"]) / (rows[peak]["tFuelK"] - rows[0]["tFuelK"])
        theta_meas = (t_meas[i] - t_meas[0]) / (t_meas[peak] - t_meas[0])
        c_diffs.append(abs(theta_model - theta_meas))
    return {
        "A": {"ratio": ratio, "label": label_A(ratio)},
        "B": {"maxAbsDiff": max(b_diffs), "label": label_diff("B", max(b_diffs))},
        "C": {"maxAbsDiff": max(c_diffs), "label": label_diff("C", max(c_diffs))},
        "reported": {
            "modelMeanFuelRiseAtPeakK": rows[peak]["tFuelK"] - rows[0]["tFuelK"],
            "measuredFuelRiseAtPeakK": t_meas[peak] - t_meas[0],
            "modelDefectAtPeakPcm": rows[peak]["defectPcm"],
            "measuredDefectAtPeakPcm": m_defect[peak],
        },
        "downLegDiagnostic": [
            {"state": i + 1, "powerKW": rows[i]["powerKW"], "modelDefectPcm": rows[i]["defectPcm"], "measuredDefectPcm": m_defect[i]}
            for i in range(PEAK_STATE, len(rows))
        ],
    }


def metric_D(meas: dict, lib) -> dict:
    model = rod_curve_model(lib, meas["rodCurve"])
    total = meas["rodCurve"][-1][1]
    diffs = [abs(w_model - w / total) for (_, w_model), (_, w) in zip(model, meas["rodCurve"])]
    rod = lib.rod_by_id["regulating"]
    return {
        "maxAbsDiff": max(diffs),
        "label": label_diff("D", max(diffs)),
        "reported": {
            "modelTotalWorthPcm": (rod.worth(1.0) - rod.worth(0.0)) * PCM,
            "measuredTotalWorthPcm_core200": total,
        },
    }


def worst(labels: list[str]) -> str:
    return max(labels, key=lambda s: LABEL_ORDER[s])


def best(labels: list[str]) -> str:
    return min(labels, key=lambda s: LABEL_ORDER[s])


# ---------------------------------------------------------------- the run

def run(libs: dict, meas: dict | None = None) -> dict:
    meas = meas or load_measured()
    t0_options = {"T0=25.8C(Table1)": meas["fuelTempC"][0] + K0, "T0=30.8C(Table2)": meas["fuelTempC_table2_first_row"] + K0}
    axes = {"pCalculated": meas["pCalculatedKW"], "pIndicated": meas["pIndicatedKW"]}
    pools = {"pool-constant": False, "pool-rising-6K": True}
    target = meas["defectPcm"][meas["peakIndex"]]

    report: dict = {"protocol": "docs/validation/m7-power-ascension-protocol.md", "libraries": {}}
    for name, lib in libs.items():
        entry: dict = {"id": lib.id, "status": lib.status, "hA_asShipped": lib.hA, "variants": {}}
        for variant in ("V0", "V1"):
            cases = []
            for (t0_label, t0), (axis_label, powers), (pool_label, rising) in itertools.product(t0_options.items(), axes.items(), pools.items()):
                hA = None
                if variant == "V1":
                    hA = calibrate_hA(lib, powers, t0, rising, target)
                    if hA is None:
                        cases.append({"case": [t0_label, axis_label, pool_label], "hA": None, "note": "hA cannot be calibrated: the 250 kW defect is out of reach"})
                        continue
                rows = model_states(lib, powers, t0, rising, hA)
                cases.append({"case": [t0_label, axis_label, pool_label], "hA": lib.hA if hA is None else hA, **metrics_for(meas, rows)})
            done = [c for c in cases if "A" in c]
            summary = {}
            for m in ("A", "B", "C"):
                # a case whose hA could not be calibrated is "not computed", and the worst over the sensitivities includes it: seven passing
                # cases of eight do not make a passing summary
                labels = [c[m]["label"] for c in done] + ["not computed"] * (len(cases) - len(done))
                summary[m] = {"worst": worst(labels), "best": best(labels), "sensitive": worst(labels) != best(labels), "notComputed": len(cases) - len(done)}
            entry["variants"][variant] = {"summary": summary, "cases": cases}
        entry["D"] = metric_D(meas, lib)
        report["libraries"][name] = entry
    return report


def print_summary(report: dict) -> None:
    print("protocol:", report["protocol"])
    for name, entry in report["libraries"].items():
        print(f"\n{name} ({entry['id']}, {entry['status']}), hA as shipped {entry['hA_asShipped']:.0f} W/K")
        for variant, v in entry["variants"].items():
            line = "  ".join(f"{m}: {s['worst']}" + (f" (best {s['best']})" if s["sensitive"] else "") for m, s in v["summary"].items())
            print(f"  {variant}  {line}")
        d = entry["D"]
        print(f"  D: {d['label']} (max difference {d['maxAbsDiff']:.3f}; model total {d['reported']['modelTotalWorthPcm']:.0f} pcm vs core 200 {d['reported']['measuredTotalWorthPcm_core200']:.0f} pcm)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    libs = {name: load_library(path) for name, path in LIBRARIES.items()}
    report = run(libs)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
