"""M7: the core 134 library against the rod worth curves and the power ascension of its own core (1994 benchmark).

Implements docs/validation/m7-core134-library-protocol.md exactly (sixth protocol, written before any run of it). Read it first: the metrics R1-R3,
A' and F, the bands, the sensitivities and the decision process are fixed there, and nothing here may change after results are seen (a change is a
new dated protocol).

Data: validation/data/jsi-core134/rod_worths.csv (Table VI) and power_steps.json (Table IX). Model: libraries/triga-jsi-134-openmc.

Run from the repo root:  python -m validation.m7_core134_library [--out PATH]
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
from pathlib import Path

from validation import m7_fuel_coefficient as fc
from validation import m7_heat_transfer as ht
from validation import m7_power_ascension as base

REPO_ROOT = base.REPO_ROOT
LIBRARY = REPO_ROOT / "libraries" / "triga-jsi-134-openmc"
RODS = REPO_ROOT / "validation" / "data" / "jsi-core134" / "rod_worths.csv"
OUT = REPO_ROOT / "validation" / "m7_core134_library_report.json"

COLUMNS = {"regulating": "R_regulating_pcm", "shim": "C_shim_pcm", "safety": "S_safety_pcm", "transient": "T_transient_pcm"}
TRAVEL_CM = 38.1
CRITICAL_CM = 28.7
R1_BANDS = ((0.90, 1.10), (0.80, 1.25))
R2_BANDS = (0.05, 0.10)
R3_BANDS = (0.05, 0.10)                     # fractions of the measured worth at the critical position
PCM = base.PCM
RANK = base.LABEL_ORDER


def load_rods() -> dict:
    """{rod: {cm: pcm}} for the rows 0..38 and the completely inserted value, from Table VI."""
    rows, full = {r: {} for r in COLUMNS}, {}
    with open(RODS, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            for rid, col in COLUMNS.items():
                if row["inserted_cm"] == "completely_inserted":
                    full[rid] = float(row[col])
                else:
                    rows[rid][int(row["inserted_cm"])] = float(row[col])
    return {"rows": rows, "full": full}


def x_of(rid: str, d_cm: float) -> float:
    """Position fraction withdrawn at d cm inserted: the fuel-followed rods run 700 steps over the 38.1 cm, the transient rod's table spans 900 steps."""
    f = 1.0 - d_cm / TRAVEL_CM
    return f * (7.0 / 9.0) if rid == "transient" else f


def model_worth_pcm(lib, rid: str, d_cm: float) -> float:
    rod = lib.rod_by_id[rid]
    return (rod.worth(1.0) - rod.worth(x_of(rid, d_cm))) * PCM


def measured_worth_at(rows: dict, d_cm: float) -> float:
    lo = int(d_cm)
    if lo == d_cm or lo + 1 not in rows:
        return rows[lo]
    return rows[lo] + (d_cm - lo) * (rows[lo + 1] - rows[lo])


def label_ratio(r: float) -> str:
    return "good" if R1_BANDS[0][0] <= r <= R1_BANDS[0][1] else "plausible" if R1_BANDS[1][0] <= r <= R1_BANDS[1][1] else "fails"


def label_diff(d: float, bands: tuple[float, float]) -> str:
    return "good" if d <= bands[0] else "plausible" if d <= bands[1] else "fails"


def rod_metrics(lib, rod_data: dict) -> dict:
    out = {}
    for rid in COLUMNS:
        rows, full = rod_data["rows"][rid], rod_data["full"][rid]
        # the regulating rod's completely inserted value is a misprint in the paper (2252 after 2550 at 38 cm): its total is the 38 cm row
        meas_total = rows[38] if rid == "regulating" else full
        d_total = 38 if rid == "regulating" else TRAVEL_CM
        model_total = model_worth_pcm(lib, rid, d_total)
        diffs = [abs(model_worth_pcm(lib, rid, d) / model_total - rows[d] / meas_total) for d in sorted(rows)]
        r1 = model_total / meas_total
        out[rid] = {"modelTotalPcm": model_total, "measuredTotalPcm": meas_total, "R1": {"ratio": r1, "label": label_ratio(r1)},
                    "R2": {"maxAbsDiff": max(diffs), "label": label_diff(max(diffs), R2_BANDS)}}
    reg = rod_data["rows"]["regulating"]
    m_crit = measured_worth_at(reg, CRITICAL_CM)
    model_crit = model_worth_pcm(lib, "regulating", CRITICAL_CM)
    err = model_crit - m_crit
    out["regulating"]["R3"] = {"modelPcm": model_crit, "measuredPcm": m_crit, "differencePcm": err,
                               "label": label_diff(abs(err) / m_crit, R3_BANDS)}
    return out


def feedback_metrics(lib, data: dict) -> dict:
    cases = []
    for (gkey, col), profile in itertools.product((("gammaB", 3), ("gammaA", 2)), ("linear", "none", "cumulative")):
        a = fc.feedback_cases(lib, data, gkey, col, profile)
        cases.append({"gamma": gkey, "profile": profile, "A": a["A"], "allSteps": a["allSteps"]})
    worst = [c["A"]["worst"] for c in cases]
    return {"primary": cases[0]["A"], "worst": base.worst(worst), "best": base.best(worst), "cases": cases}


def reported(lib, data: dict, feedback: dict) -> dict:
    steps = data["steps"]
    t0_c = data["conditions"]["T0C"]
    t_mean = fc.mean_fuel_temps_k(steps, 3, data["conversion"]["gammaB"], t0_c)
    wr = fc.water_rise("linear", steps)
    meas = [t - (t0_c + base.K0) - w for t, w in zip(t_mean, wr)]
    ratios = [{"step": i, "powerKW": steps[i][1], "modelRiseK": ht.delta_t(steps[i][1] * 1e3, lib.hA, lib.hA_exponent), "measuredRiseK": meas[i]} for i in fc.RISE_STEPS]
    for r in ratios:
        r["ratio"] = r["modelRiseK"] / r["measuredRiseK"]
    return {
        "cumulativeAtStep13": {"measuredPcm": -steps[13][5], "modelPcm": feedback["cases"][0]["allSteps"][13]["modelPcm"]},
        "slopesPerK": {"fuelFirstInterval": fc.slope(lib.fuel_temp, 294.0, 400.0), "coolantFirstInterval": fc.slope(lib.cool_temp, 294.0, 313.15)},
        "calibrationOffsetPcm": -lib.calibration * PCM, "hA": lib.hA, "hAExponent": lib.hA_exponent, "meanRiseAtPowers": ratios,
    }


def decide(rods: dict, a_worst: str) -> dict:
    ok = ("good", "plausible")
    reg = rods["regulating"]
    reg_ok = all(reg[k]["label"] in ok for k in ("R1", "R2", "R3"))
    out = {"regulatingRod": "supported" if reg_ok else "fails"}
    out["feedback"] = "consistent" if a_worst in ok else "fails"
    out["others"] = {r: (rods[r]["R1"]["label"], rods[r]["R2"]["label"]) for r in ("shim", "safety", "transient")}
    if reg_ok and a_worst in ok:
        out["next"] = "the library reproduces what the power ascension of its own core needs: a seventh protocol may compare the power ascension"
    elif not reg_ok:
        out["next"] = "the regulating rod curve is not usable for the power ascension: record and stop"
    else:
        out["next"] = "the fresh-fuel feedback fails: record; fuel hydrogen and the temperature conversion are the first suspects; no seventh protocol yet"
    return out


def run(lib, rod_data: dict | None = None, data: dict | None = None) -> dict:
    rod_data = rod_data or load_rods()
    data = data or fc.load_steps()
    rods = rod_metrics(lib, rod_data)
    feedback = feedback_metrics(lib, data)
    return {"protocol": "docs/validation/m7-core134-library-protocol.md", "id": lib.id, "status": lib.status, "rods": rods,
            "A": feedback, "F": reported(lib, data, feedback), "decision": decide(rods, feedback["worst"])}


def print_summary(r: dict) -> None:
    print("protocol:", r["protocol"], "|", r["id"], r["status"])
    for rid, m in r["rods"].items():
        extra = f"  R3 diff {m['R3']['differencePcm']:.0f} pcm [{m['R3']['label']}]" if "R3" in m else ""
        print(f"  {rid}: total model {m['modelTotalPcm']:.0f} / measured {m['measuredTotalPcm']:.0f} pcm  R1 {m['R1']['ratio']:.3f} [{m['R1']['label']}]  R2 {m['R2']['maxAbsDiff']:.3f} [{m['R2']['label']}]{extra}")
    a = r["A"]
    for s in a["primary"]["perStep"]:
        print(f"  A' step {s['step']}: mean fuel {s['meanFuelC']:.1f} C  model {s['modelPcm']:.1f} vs measured {s['measuredPcm']:.1f} pcm [{s['label']}]")
    print(f"  A': primary {a['primary']['worst']}  worst {a['worst']} best {a['best']}")
    f = r["F"]
    print(f"  F: step 13 model {f['cumulativeAtStep13']['modelPcm']:.1f} vs measured {f['cumulativeAtStep13']['measuredPcm']:.1f} pcm; slopes {f['slopesPerK']}; offset {f['calibrationOffsetPcm']:.0f} pcm")
    print("  F: constant-hA mean rise ratio (model / measured), steps 4-14:", [round(x["ratio"], 2) for x in f["meanRiseAtPowers"]])
    print("  decision:", r["decision"])


def main(argv: list[str] | None = None) -> int:
    from physics_ref.library import Library

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    report = run(Library(LIBRARY))
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
