"""M7: the hot-element comparison again, with the energy column that integrates the whole pulse, plus stability checks.

Implements docs/validation/m7-hot-element-2-protocol.md exactly (fourth protocol, written before any run of it; it follows
m7-hot-element-protocol.md, its results and its addendum). Read it first: the column, the new checks K1, K2, T, the ring description W,
the bands and the decision process are fixed there, and nothing here may change after results are seen (a change is a new dated protocol).

Metrics G, H1, H2 and R are those of validation/m7_hot_element.py, run with the primary energy column energy_1pct_mws (sensitivity:
energy_tangent_mws); energy_1000pts_mws is reported once for the record and takes no part in any label.

Run from the repo root:  python -m validation.m7_hot_element_2 [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from validation import m7_hot_element as he
from validation import m7_power_ascension as base

REPO_ROOT = base.REPO_ROOT
OUT = REPO_ROOT / "validation" / "m7_hot_element_2_report.json"
COLUMNS = ("energy_1pct_mws", "energy_tangent_mws")
RECORD_COLUMN = "energy_1000pts_mws"
CORE_NUMBER = he.CORE_NUMBER


# ---------------------------------------------------------------- Stage 1 stability checks

def readings(records, lib, core: str, column: str = COLUMNS[0], t0_c: float = 25.0) -> list[dict]:
    """One entry per usable (pulse, thermocouple) reading: pulse id, thermocouple, energy and F_tc (same formula as the first protocol)."""
    out = []
    for r in records:
        if r.core_config != core:
            continue
        e = getattr(r, column)
        if not e or e <= 0:
            continue
        for tc, col in (("t1", "t1_max_c"), ("t2", "t2_max_c")):
            tmax = getattr(r, col)
            if tmax is None:
                continue
            cbar = he.mean_cp(lib, t0_c + base.K0, tmax + base.K0)
            out.append({"pulse": r.pulse_id, "tc": tc, "energy": e, "f": (tmax - t0_c) * lib.fuel_mass * cbar / (e * 1e6)})
    return out


def median_or_none(rows: list[dict]) -> float | None:
    return statistics.median(r["f"] for r in rows) if len(rows) >= he.MIN_PULSES else None


def ratio(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None or b == 0 else a / b


def labelled(r: float | None) -> dict:
    return {"ratio": r, "label": "not computed" if r is None else he.label_ratio(r)}


def split_half(rows: list[dict]) -> float | None:
    return ratio(median_or_none([r for r in rows if r["pulse"] % 2 == 0]), median_or_none([r for r in rows if r["pulse"] % 2 == 1]))


def size_trend(rows: list[dict]) -> float | None:
    """Median F_tc of the lowest energy third over that of the highest third."""
    s = sorted(rows, key=lambda r: r["energy"])
    third = len(s) // 3
    return ratio(median_or_none(s[:third]), median_or_none(s[-third:])) if third else None


def stability(rows: list[dict]) -> dict:
    out = {}
    for name, sel in (("both", rows), ("tc1", [r for r in rows if r["tc"] == "t1"]), ("tc2", [r for r in rows if r["tc"] == "t2"])):
        out[name] = {"n": len(sel), "median": median_or_none(sel), "K1": labelled(split_half(sel)), "T": labelled(size_trend(sel))}
    return out


# ---------------------------------------------------------------- W: every element's peaking by ring

def ring_factors(lib, rods: dict, t_fuel_k: float, f_tc: float | None) -> dict:
    s = lib.shapes
    elements, edges = s["bins"]["elements"], s["bins"]["axialEdgesCm"]
    A = len(edges) - 1
    arr = he.shape_array(lib, rods, t_fuel_k)
    centre = next(a for a in range(A) if edges[a] <= 0.0 < edges[a + 1])
    powered = [e for e in range(len(elements)) if sum(arr[e * A:(e + 1) * A]) > 1e-12]
    per = {elements[e]: arr[e * A + centre] / (edges[centre + 1] - edges[centre]) * len(powered) * he.L_CM for e in powered}
    rings: dict[str, list[float]] = {}
    for name, f in per.items():
        rings.setdefault(name[0], []).append(f)
    out = {"rings": {r: {"n": len(v), "min": min(v), "median": statistics.median(v), "max": max(v)} for r, v in sorted(rings.items())}}
    if f_tc is not None:
        closest = min(per, key=lambda n: abs(per[n] - f_tc))
        out["closest"] = {"element": closest, "ring": closest[0], "factor": per[closest], "fTc": f_tc}
    return out


# ---------------------------------------------------------------- decision

def decide(h1_pulse: str, checks: list[str]) -> dict:
    ok = ("good", "plausible")
    if h1_pulse in ok and all(c in ok for c in checks):
        return {"case": 1, "text": "the chain reproduces the measured rise with the pulse peaking, which is stable; the instrumented elements are not necessarily the library's hottest B element; the library's fuel rise needs no correction."}
    if h1_pulse in ok:
        return {"case": 2, "text": "H-pulse agrees but the pulse peaking is not stable (K1, K2 or T fails): unresolved."}
    return {"case": 3, "text": "H-pulse fails: the first protocol's conflict between the shape-array peaking and the fuel coefficient stands."}


# ---------------------------------------------------------------- the run

def run(libs: dict, records, meas: dict | None = None) -> dict:
    meas = meas or base.load_measured()
    saved = he.ENERGY_COLUMNS
    he.ENERGY_COLUMNS = COLUMNS
    try:
        report = he.run(libs, records, meas)
    finally:
        he.ENERGY_COLUMNS = saved
    report["protocol"] = "docs/validation/m7-hot-element-2-protocol.md"
    reg_step = meas["states"][base.PEAK_STATE - 1]["regulatingRodStep"]

    stab = {}
    for name, lib in libs.items():
        core = CORE_NUMBER.get(name, name)
        stab[name] = stability(readings(records, lib, core))
        entry = report["libraries"][name]
        entry["recordOnly"] = {RECORD_COLUMN: he.describe([r["f"] for r in readings(records, lib, core, RECORD_COLUMN)])}
        entry["stability"] = stab[name]
        case0 = entry["cases"][0]
        if "tFuelPeakK" in case0:
            rods = {r: 1.0 for r in lib.rod_by_id}
            rods["regulating"] = base._x(reg_step)
            entry["W"] = ring_factors(lib, rods, case0["tFuelPeakK"], entry["stage1"]["primary"]["both"]["median"])

    names = list(libs)
    if len(names) > 1:
        k2 = labelled(ratio(stab[names[0]]["both"]["median"], stab[names[-1]]["both"]["median"]))
    else:
        k2 = {"label": "not computed", "ratio": None}
    report["K2"] = {"coresCompared": names, **k2}
    for name in names:
        entry = report["libraries"][name]
        st = entry["stability"]["both"]
        checks = {"K1": st["K1"]["label"], "K2": k2["label"], "T": st["T"]["label"]}
        entry["decision2"] = {**decide(entry["H1pulse"]["primary"]["label"], list(checks.values())), "checks": checks}
    return report


def print_summary(report: dict) -> None:
    print("protocol:", report["protocol"])
    print("K2 cross-core:", report["K2"])
    for name, e in report["libraries"].items():
        st = e["stability"]["both"]
        print(f"\n{name} ({e['id']}, {e['status']})")
        print("  F_tc primary (1% column):", e["stage1"]["primary"]["both"])
        print("  K1", st["K1"], " T", st["T"])
        for key in ("G", "H1pulse", "H1shape"):
            v = e[key]
            s = v["sensitivities"]
            tail = f"  worst {s['worst']} best {s['best']} ratio {s['ratioMin']:.2f}-{s['ratioMax']:.2f}" if s else ""
            print(f"  {key}: primary {v['primary']['label']} (ratio {v['primary']['ratio']}){tail}")
            if "h2" in v:
                print(f"     H2: primary {v['h2']['label']} ({v['h2']['primary']}), worst {v['h2']['worstOverSensitivities']}")
        if "W" in e:
            print("  W closest:", e["W"].get("closest"), " ring medians:", {r: round(x["median"], 2) for r, x in e["W"]["rings"].items()})
        print(f"  decision: case {e['decision2']['case']} {e['decision2']['checks']}: {e['decision2']['text']}")


def main(argv: list[str] | None = None) -> int:
    from validation.pulse_loader import load_pulse_summary

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    libs = {name: base.load_library(path) for name, path in base.LIBRARIES.items()}
    report = run(libs, load_pulse_summary())
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
