"""M7: the library's fuel temperature feedback and heat transfer law against the 1994 JSI core 134 power ascension (and the 2002 coefficients).

Implements docs/validation/m7-fuel-coefficient-protocol.md exactly (fifth protocol, written and amended before any run of it). Read it first:
the data, the conversion, the metrics A-F, the bands, the sensitivities and the decision process are fixed there, and nothing here may change
after results are seen (a change is a new dated protocol).

Data: validation/data/jsi-core134/power_steps.json (Table IX, Mele, Ravnik, Trkov, Nucl. Technol. 105 (1994)); the 2002 values are constants below.
Model: the libraries of cores 242 and 246 read through physics_ref.library, their `fuelTemp` and `coolantTemp` tables (absolute reactivity, pcm = 1e5 x)
and the heat transfer law `hA = h0 (dT / 100 K)^n` they now carry (hA, hA_exponent, hA_dt_ref).

Run from the repo root:  python -m validation.m7_fuel_coefficient [--out PATH]
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path

from validation import m7_hot_element as he
from validation import m7_heat_transfer as ht
from validation import m7_power_ascension as base

REPO_ROOT = base.REPO_ROOT
DATA = REPO_ROOT / "validation" / "data" / "jsi-core134" / "power_steps.json"
OUT = REPO_ROOT / "validation" / "m7_fuel_coefficient_report.json"

PCM = base.PCM
K0 = base.K0
WATER_RISE_K = 8.0                      # total pool warming during the experiment (paper), no times given
RELIABLE_STEPS = range(1, 8)            # average fuel temperature up to about 100 C
FIT_STEPS = range(4, 14)                # exponent fit: P >= 45 kW, up to step 13
RISE_STEPS = range(4, 15)               # absolute rise (metric E)
POSITIONS = {"primary": 48.0, "paper": 47.6}    # fuel positions of core 134: 45 elements + 3 followers (the library convention), or 45 + 2.6
POSITIONS_LIB = {"core242": 61, "core246": 67}  # fuel positions with power in the libraries' shape arrays
ISO_MEASURED = (3.5, 3.4, 3.6)          # pcm/C, 2002 (primary, then the two runs); +- 0.3
FUEL_B_MEASURED = -4.8                  # pcm/C per B-ring kelvin, 2002; +- 0.5
F_TC = {"core242": 1.276, "core246": 1.390}     # thermocouple peaking found in the second hot-element protocol (the first version's conversion)
POWER_2002_W = 600.0
A_GOOD, A_PLAUSIBLE = (0.10, 10.0), (0.25, 25.0)          # (relative, floor in pcm)
B_BANDS, C_BANDS = (0.6, 1.75), (1.0, 2.4)                # absolute pcm/C
D_BANDS = (0.10, 0.20)
E_BANDS = ((0.85, 1.15), (0.70, 1.40))
RANK = base.LABEL_ORDER


def label_band(diff: float, bands: tuple[float, float]) -> str:
    return "good" if diff <= bands[0] else "plausible" if diff <= bands[1] else "fails"


def label_cumulative(model: float, measured: float) -> str:
    err = abs(model - measured)
    if err <= max(A_GOOD[0] * abs(measured), A_GOOD[1]):
        return "good"
    return "plausible" if err <= max(A_PLAUSIBLE[0] * abs(measured), A_PLAUSIBLE[1]) else "fails"


def label_ratio(r: float) -> str:
    return he.label_ratio(r, E_BANDS)


# ---------------------------------------------------------------- measured side

def load_steps() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def mean_fuel_temps_k(steps: list, column: int, gamma: float, t0_c: float) -> list[float]:
    """Volume-averaged fuel temperature (K) at each step from the thermocouple column (index 2 = TA, 3 = TB): T0 + (T - T0) / gamma."""
    return [t0_c + (row[column] - t0_c) / gamma + K0 for row in steps]


def water_rise(profile: str, steps: list) -> list[float]:
    """Pool warming above T0 at each step (K): none, linear in the step number, or proportional to the cumulative power."""
    n = len(steps) - 1
    if profile == "none":
        return [0.0] * len(steps)
    if profile == "linear":
        return [WATER_RISE_K * i / n for i in range(len(steps))]
    cum = []
    total = 0.0
    for row in steps:
        total += row[1]
        cum.append(total)
    return [WATER_RISE_K * c / cum[-1] for c in cum]


# ---------------------------------------------------------------- model side

def model_loss_pcm(lib, t_mean_k: list[float], water_k: list[float]) -> list[float]:
    """Reactivity loss D_i (pcm) of the library's fuel and coolant tables relative to step 0."""
    rho = [(lib.fuel_temp(t) + lib.cool_temp(w)) * PCM for t, w in zip(t_mean_k, water_k)]
    return [-(r - rho[0]) for r in rho]


def powered_elements(lib) -> int:
    s = lib.shapes
    arr = he.shape_array(lib, {r: 1.0 for r in lib.rod_by_id}, 400.0)
    A = len(s["bins"]["axialEdgesCm"]) - 1
    return sum(1 for e in range(len(s["bins"]["elements"])) if sum(arr[e * A:(e + 1) * A]) > 1e-12)


def slope(table, lo: float, hi: float) -> float:
    return (table(hi) - table(lo)) / (hi - lo) * PCM


def fit_exponent(power_kw: list[float], rise_k: list[float]) -> float | None:
    """n of a rise ~ P^(1/(1+n)) by least squares of ln(rise) on ln(P); None if the fit is degenerate."""
    pts = [(math.log(p), math.log(r)) for p, r in zip(power_kw, rise_k) if p > 0 and r > 0]
    if len(pts) < 3:
        return None
    mx = sum(x for x, _ in pts) / len(pts)
    my = sum(y for _, y in pts) / len(pts)
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    b = sum((x - mx) * (y - my) for x, y in pts) / sxx
    return None if b <= 0 else 1.0 / b - 1.0


def law_h0(lib) -> float:
    """The library's heat transfer coefficient at the 100 K reference of the helpers: hA (dT / dTRef)^n = h0 (dT / 100 K)^n with h0 = hA (100 / dTRef)^n."""
    return lib.hA * (ht.DT_REF / getattr(lib, "hA_dt_ref", ht.DT_REF)) ** getattr(lib, "hA_exponent", 0.0)


def predicted_rise_k(p_kw: float, h0: float, n: float, scale: float) -> float:
    return ht.delta_t(p_kw * 1e3, h0 * scale, n)


def per_step_coefficients(lib, data: dict) -> list[dict]:
    """Metric F: the incremental coefficient d(rho)/d(T mean) of each step of Table IX, measured and from the library's tables (primary conversion: TB, gamma_B, linear water warming), pcm/K."""
    steps = data["steps"]
    t0_c = data["conditions"]["T0C"]
    t_mean = mean_fuel_temps_k(steps, 3, data["conversion"]["gammaB"], t0_c)
    w = [t0_c + K0 + r for r in water_rise("linear", steps)]
    model = model_loss_pcm(lib, t_mean, w)
    out = []
    for i in range(1, 14):
        d_t = t_mean[i] - t_mean[i - 1]
        out.append({"step": i, "dMeanFuelK": d_t, "measuredPcmPerK": steps[i][4] / d_t, "modelPcmPerK": -(model[i] - model[i - 1]) / d_t})
    return out


# ---------------------------------------------------------------- the metrics for one library

def feedback_cases(lib, data: dict, gamma_key: str, column: int, profile: str) -> dict:
    steps = data["steps"]
    t0_c = data["conditions"]["T0C"]
    gamma = data["conversion"][gamma_key]
    t_mean = mean_fuel_temps_k(steps, column, gamma, t0_c)
    w = [t0_c + K0 + r for r in water_rise(profile, steps)]
    model = model_loss_pcm(lib, t_mean, w)
    per = []
    for i in RELIABLE_STEPS:
        measured = -steps[i][5]
        per.append({"step": i, "meanFuelC": t_mean[i] - K0, "modelPcm": model[i], "measuredPcm": measured, "errorPcm": model[i] - measured, "label": label_cumulative(model[i], measured)})
    all_steps = [{"step": i, "meanFuelC": t_mean[i] - K0, "modelPcm": model[i], "measuredPcm": None if steps[i][5] is None else -steps[i][5]} for i in range(len(steps))]
    return {"A": {"worst": base.worst([p["label"] for p in per]), "perStep": per}, "allSteps": all_steps, "tMeanK": t_mean}


def heat_cases(lib, name: str, data: dict, gamma_key: str, column: int, profile: str, positions_key: str) -> dict:
    steps = data["steps"]
    t0_c = data["conditions"]["T0C"]
    gamma = data["conversion"][gamma_key]
    t_mean = mean_fuel_temps_k(steps, column, gamma, t0_c)
    wr = water_rise(profile, steps)
    measured = [t - (t0_c + K0) - w for t, w in zip(t_mean, wr)]          # mean fuel rise over the water
    # step 14 has the B-ring reading only (the paper gives no A-ring value for it that the protocol uses): TB with gamma_B whatever thermocouple the case selects
    t_b14 = mean_fuel_temps_k(steps, 3, data["conversion"]["gammaB"], t0_c)[14]
    measured[14] = t_b14 - (t0_c + K0) - wr[14]
    n_lib, h0 = lib.hA_exponent, law_h0(lib)
    scale = POSITIONS[positions_key] / POSITIONS_LIB[name]
    fit = fit_exponent([steps[i][1] for i in FIT_STEPS], [measured[i] for i in FIT_STEPS])
    d = {"n134": fit, "nLibrary": n_lib}
    d["D"] = {"label": "not computed" if fit is None else label_band(abs(fit - n_lib), D_BANDS), "difference": None if fit is None else fit - n_lib}
    per = []
    for i in RISE_STEPS:
        model = predicted_rise_k(steps[i][1], h0, n_lib, scale)
        per.append({"step": i, "powerKW": steps[i][1], "modelRiseK": model, "measuredRiseK": measured[i], "ratio": model / measured[i], "label": label_ratio(model / measured[i])})
    d["E"] = {"worst": base.worst([p["label"] for p in per]), "ratioMin": min(p["ratio"] for p in per), "ratioMax": max(p["ratio"] for p in per), "perStep": per}
    return d


def secondary(lib, name: str) -> dict:
    """B and C (2002 data) from the first tabulated interval of the library tables, and the chain conversion for C's sensitivity."""
    out = {"slopes": {}}
    for label, fuel_hi, cool_hi in (("first-interval", 400.0, 313.15), ("wide", 500.0, 333.15)):
        s_f = slope(lib.fuel_temp, 294.0, fuel_hi)
        s_c = slope(lib.cool_temp, 294.0, cool_hi)
        out["slopes"][label] = {"fuelPerMeanK": s_f, "coolantPerK": s_c, "isothermal": s_f + s_c}
    # the chain conversion r_B at 600 W with the library's own law and the core's F_tc
    n_el = powered_elements(lib)
    dt_mean = ht.delta_t(POWER_2002_W, law_h0(lib), lib.hA_exponent)
    tc = he.chain_temperatures([POWER_2002_W / 1e3], [K0 + 22.0], law_h0(lib), lib.hA_exponent, F_TC.get(name, 1.3), he.K_PRIMARY, he.R_TC_PRIMARY, n_el)[0]
    r_b = (tc - (K0 + 22.0)) / dt_mean
    out["rB"] = r_b
    return out


def evaluate_library(lib, name: str, data: dict) -> dict:
    sec = secondary(lib, name)
    gamma_b = data["conversion"]["gammaB"]
    b_records, c_records = [], []
    for interval, meas in itertools.product(("first-interval", "wide"), ISO_MEASURED):
        diff = abs(sec["slopes"][interval]["isothermal"] - meas)
        b_records.append({"interval": interval, "measured": meas, "difference": diff, "label": label_band(diff, B_BANDS)})
    for interval, conv in itertools.product(("first-interval", "wide"), ("gammaB", "chain")):
        per_b = sec["slopes"][interval]["fuelPerMeanK"] / (gamma_b if conv == "gammaB" else sec["rB"])
        diff = abs(per_b - FUEL_B_MEASURED)
        c_records.append({"interval": interval, "conversion": conv, "perBRingK": per_b, "difference": diff, "label": label_band(diff, C_BANDS)})
    a_cases, hd_cases = [], []
    for (gkey, col), profile in itertools.product((("gammaB", 3), ("gammaA", 2)), ("linear", "none", "cumulative")):
        a = feedback_cases(lib, data, gkey, col, profile)
        a_cases.append({"gamma": gkey, "profile": profile, "A": a["A"], "allSteps": a["allSteps"]})
        for pk in POSITIONS:
            hd_cases.append({"gamma": gkey, "profile": profile, "positions": pk, **heat_cases(lib, name, data, gkey, col, profile, pk)})

    def worst_best(records, key):
        labels = [r[key] for r in records]
        return {"worst": base.worst(labels), "best": base.best(labels)}

    return {
        "id": lib.id, "status": lib.status, "secondary": sec,
        "A": {"primary": a_cases[0]["A"], **worst_best([c["A"] for c in a_cases], "worst"), "cases": a_cases},
        "B": {"primary": b_records[0], **worst_best(b_records, "label"), "records": b_records},
        "C": {"primary": c_records[0], **worst_best(c_records, "label"), "records": c_records},
        "D": {"primary": hd_cases[0]["D"], **worst_best([c["D"] for c in hd_cases], "label"), "n134Range": [min(c["n134"] for c in hd_cases if c["n134"] is not None), max(c["n134"] for c in hd_cases if c["n134"] is not None)],
              "nLibrary": lib.hA_exponent},
        "E": {"primary": {"worst": hd_cases[0]["E"]["worst"], "ratioMin": hd_cases[0]["E"]["ratioMin"], "ratioMax": hd_cases[0]["E"]["ratioMax"]}, **worst_best([c["E"] for c in hd_cases], "worst"),
              "ratioMin": min(c["E"]["ratioMin"] for c in hd_cases), "ratioMax": max(c["E"]["ratioMax"] for c in hd_cases)},
        "F": {"heatCases": hd_cases[:2], "cumulativeAtStep13": {"measuredPcm": -data["steps"][13][5], "modelPcm": a_cases[0]["allSteps"][13]["modelPcm"]},
              "perStepCoefficients": per_step_coefficients(lib, data)},
    }


def decide(entry: dict) -> dict:
    """The protocol's decision process, read on the primary line."""
    ok = ("good", "plausible")
    a = entry["A"]["primary"]["worst"]
    d = entry["D"]["primary"]["label"]
    e = entry["E"]["primary"]["worst"]
    out = {"feedback": "consistent" if a in ok else "fails (burnup is the first candidate)"}
    if e not in ok:
        out["heatTransfer"] = "the law is specific to the earlier exercise (E fails): add a known limit"
    elif d in ok:
        out["heatTransfer"] = "the law transfers to core 134 (D and E good or plausible)"
    else:
        out["heatTransfer"] = "the scale transfers, the exponent does not (D fails, E good or plausible)"
    out["secondary"] = {"B": entry["B"]["primary"]["label"], "C": entry["C"]["primary"]["label"]}
    return out


def run(libs: dict, data: dict | None = None) -> dict:
    data = data or load_steps()
    report = {"protocol": "docs/validation/m7-fuel-coefficient-protocol.md", "libraries": {}}
    for name, lib in libs.items():
        entry = evaluate_library(lib, name, data)
        entry["decision"] = decide(entry)
        report["libraries"][name] = entry
    return report


def print_summary(report: dict) -> None:
    print("protocol:", report["protocol"])
    for name, e in report["libraries"].items():
        print(f"\n{name} ({e['id']}, {e['status']})")
        for step in e["A"]["primary"]["perStep"]:
            print(f"  A step {step['step']}: mean fuel {step['meanFuelC']:.1f} C  model {step['modelPcm']:.1f} vs measured {step['measuredPcm']:.1f} pcm  [{step['label']}]")
        print(f"  A: primary {e['A']['primary']['worst']}  worst {e['A']['worst']} best {e['A']['best']}")
        print(f"  B: primary {e['B']['primary']['label']} (diff {e['B']['primary']['difference']:.2f})  worst {e['B']['worst']} best {e['B']['best']}")
        print(f"  C: primary {e['C']['primary']['label']} (per B-ring K {e['C']['primary']['perBRingK']:.2f})  worst {e['C']['worst']} best {e['C']['best']}")
        d = e["D"]
        diff = d["primary"]["difference"]
        print(f"  D: primary {d['primary']['label']} (n134 {None if diff is None else diff + d['nLibrary']:.3f}, library {d['nLibrary']})  worst {d['worst']} best {d['best']}  n134 range {d['n134Range']}")
        ee = e["E"]
        print(f"  E: primary {ee['primary']['worst']} (ratio {ee['primary']['ratioMin']:.2f}-{ee['primary']['ratioMax']:.2f})  worst {ee['worst']} best {ee['best']}  all {ee['ratioMin']:.2f}-{ee['ratioMax']:.2f}")
        print(f"  F: defect at step 13 model {e['F']['cumulativeAtStep13']['modelPcm']:.1f} vs measured {e['F']['cumulativeAtStep13']['measuredPcm']:.1f} pcm; slopes {e['secondary']['slopes']}")
        print(f"  decision: {e['decision']}")


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
