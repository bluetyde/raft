"""M7: can the library's shape arrays, an in-element conduction model and the pulse data account for the measured hot-element temperature?

Implements docs/validation/m7-hot-element-protocol.md exactly (third protocol, written before any run of it; it follows
m7-power-ascension-protocol.md and m7-heat-transfer-protocol.md and their results). Read it first: the stages, the inputs, the bands and the
decision process are fixed there, and nothing here may change after results are seen (a change is a new dated protocol).

Stage 1  F_tc    thermocouple peaking from the pulse database (adiabatic pulse heating)         read blind
Stage 2  F_shape peaking of the B-ring elements from the library's separable shape arrays
Stage 3  chain   T_tc - T_pool = dT_s,hot + F q'''_mean c(r_tc) / k, with the fitted law of the heat-transfer protocol (h0, n)

Choices the protocol leaves open, made here and stated in the report:
  * F_shape is evaluated once per fit case, at the 250 kW state (its regulating-rod step and the law's mean fuel temperature there), and is
    used at every state.
  * The decision process reads the primary line (first fit case, primary k, r_tc and elements); worst and best over the sensitivities are reported beside it.
  * Case 2 of the decision (G fails, H-pulse good or plausible) is read as F_tc / F_shape below the plausible band.

Run from the repo root:  python -m validation.m7_hot_element [--out PATH]
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
from pathlib import Path

from validation import m7_heat_transfer as ht
from validation import m7_power_ascension as base

REPO_ROOT = base.REPO_ROOT
OUT = REPO_ROOT / "validation" / "m7_hot_element_report.json"

RI, RO = 0.31750, 1.82245          # cm, Zr rod radius and fuel radius (Svajger 2024 Table 1)
L_CM = 38.1                        # cm, fuel length
CORE_NUMBER = {"core242": "242", "core246": "246"}
K_PRIMARY, K_SENS = 17.6, (15.0, 25.0)               # W/m.K
R_TC_PRIMARY, R_TC_SENS = RI, (0.762,)                # cm
ENERGY_COLUMNS = ("energy_1000pts_mws", "energy_1pct_mws", "energy_tangent_mws")
PULSE_T0_C = (25.0, 20.0, 30.0)                       # first is primary
MIN_PULSES = 5
G_BANDS = H1_BANDS = ((0.85, 1.15), (0.70, 1.40))     # (good, plausible) intervals of a ratio
R_CONSISTENT = (0.8, 1.25)
LABEL_ORDER = base.LABEL_ORDER


def label_ratio(r: float, bands=G_BANDS) -> str:
    (g_lo, g_hi), (p_lo, p_hi) = bands
    if g_lo <= r <= g_hi:
        return "good"
    return "plausible" if p_lo <= r <= p_hi else "fails"


# ---------------------------------------------------------------- Stage 1: the pulses

def mean_cp(lib, t0_k: float, t1_k: float) -> float:
    """Mean of the library's fuel cp table between two temperatures (the value at t0 if they coincide)."""
    a, b = sorted((t0_k, t1_k))
    return lib.fuel_cp(a) if b == a else lib.fuel_cp.integral(a, b) / (b - a)


def pulse_peakings(records, lib, core: str, energy_col: str, t0_c: float) -> dict[str, list[float]]:
    """F_tc = (T_max - T0) * M * cbar / E for each usable pulse and thermocouple. Only an empty field or a zero energy drops a pulse."""
    out = {"t1": [], "t2": []}
    for r in records:
        if r.core_config != core:
            continue
        e = getattr(r, energy_col)
        if not e or e <= 0:
            continue
        for key, col in (("t1", "t1_max_c"), ("t2", "t2_max_c")):
            tmax = getattr(r, col)
            if tmax is None:
                continue
            cbar = mean_cp(lib, t0_c + base.K0, tmax + base.K0)
            out[key].append((tmax - t0_c) * lib.fuel_mass * cbar / (e * 1e6))
    return out


def describe(values: list[float]) -> dict:
    if len(values) < MIN_PULSES:
        return {"n": len(values), "median": None, "iqr": None, "note": "not computed (fewer than 5)"}
    q = statistics.quantiles(values, n=4, method="inclusive")
    return {"n": len(values), "median": statistics.median(values), "iqr": [q[0], q[2]]}


def stage1(records, lib, core: str) -> dict:
    """The primary F_tc and its sensitivities. Pulses of other cores are only counted, never used."""
    counts: dict[str, int] = {}
    for r in records:
        counts[str(r.core_config)] = counts.get(str(r.core_config), 0) + 1
    variants = {}
    for col, t0 in itertools.product(ENERGY_COLUMNS, PULSE_T0_C):
        v = pulse_peakings(records, lib, core, col, t0)
        both = v["t1"] + v["t2"]
        variants[f"{col}|T0={t0:g}C"] = {"both": describe(both), "tc1": describe(v["t1"]), "tc2": describe(v["t2"])}
    primary = variants[f"{ENERGY_COLUMNS[0]}|T0={PULSE_T0_C[0]:g}C"]
    return {"coreConfigCounts": counts, "primary": primary, "variants": variants, "fuelFractionInLibrary": lib.fuel_fraction}


# ---------------------------------------------------------------- Stage 2: the shape arrays

def shape_array(lib, rods: dict[str, float], t_fuel_k: float) -> list[float]:
    """Power shape (fractions of total power) at a rod state and mean fuel temperature: base + rod deltas + temperature delta.
    The same separable reconstruction as physics_ref.engine.Engine.shape."""
    s = lib.shapes
    E, A = len(s["bins"]["elements"]), len(s["bins"]["axialEdgesCm"]) - 1
    n = E * A
    out = list(lib.arrays[s["base"]])

    def add(grid, arr, x):
        x = min(grid[-1], max(grid[0], x))
        k = 0
        while k < len(grid) - 2 and x > grid[k + 1]:
            k += 1
        w = (x - grid[k]) / (grid[k + 1] - grid[k])
        a, b = arr[k * n:(k + 1) * n], arr[(k + 1) * n:(k + 2) * n]
        for j in range(n):
            out[j] += (1 - w) * a[j] + w * b[j]

    for rid, d in s["rodDeltas"].items():
        add(d["x"], lib.arrays[d["array"]], rods[rid])
    add(s["tempDelta"]["T"], lib.arrays[s["tempDelta"]["array"]], t_fuel_k)
    return out


def shape_peakings(lib, rods: dict[str, float], t_fuel_k: float) -> dict:
    """F_shape = (fraction(e, bin) / bin height) * N * L for each B-ring element, at the centre-plane bin and at the element's hottest bin."""
    s = lib.shapes
    elements, edges = s["bins"]["elements"], s["bins"]["axialEdgesCm"]
    A = len(edges) - 1
    arr = shape_array(lib, rods, t_fuel_k)
    heights = [edges[a + 1] - edges[a] for a in range(A)]
    centre = next(a for a in range(A) if edges[a] <= 0.0 < edges[a + 1])
    n_powered = sum(1 for e in range(len(elements)) if sum(arr[e * A:(e + 1) * A]) > 1e-12)
    per = {}
    for e, name in enumerate(elements):
        if not name.startswith("B"):
            continue
        factors = [arr[e * A + a] / heights[a] * n_powered * L_CM for a in range(A)]
        hot = max(range(A), key=factors.__getitem__)
        per[name] = {"centre": factors[centre], "hottest": factors[hot], "hottestBin": hot}
    return {"elementsWithPower": n_powered, "centreBin": centre, "B": per}


def primary_element(peak: dict) -> str:
    return max(peak["B"], key=lambda e: peak["B"][e]["centre"])


# ---------------------------------------------------------------- Stage 3: the conduction chain

def c_of_r(r: float) -> float:
    """cm^2: the conduction drop per unit volumetric power over conductivity for an annulus with an adiabatic inner wall and a fixed outer surface."""
    return ((RO**2 - r**2) - 2.0 * RI**2 * math.log(RO / r)) / 4.0


def c_mean(steps: int = 2000) -> float:
    """Volume mean of c(r) over the fuel annulus (Simpson)."""
    h = (RO - RI) / steps
    f = lambda r: c_of_r(r) * r
    total = f(RI) + f(RO) + sum((4 if i % 2 else 2) * f(RI + i * h) for i in range(1, steps))
    return 2.0 / (RO**2 - RI**2) * total * h / 3.0


def chain_temperatures(p_kw: list[float], pool_k: list[float], h0: float, n: float, f: float, k_wmk: float, r_tc: float,
                       n_elements: int, dt_scale: float = 1.0) -> list[float]:
    """Thermocouple temperature (K) at each state for peaking f; dt_scale multiplies the law's mean fuel rise (used by metric R only)."""
    area = math.pi * (RO**2 - RI**2)
    k_cm = k_wmk / 100.0
    cbar, c_tc = c_mean(), c_of_r(r_tc)
    out = []
    for p, tp in zip(p_kw, pool_k):
        dt = dt_scale * ht.delta_t(p * 1e3, h0, n)
        q3 = p * 1e3 / (n_elements * L_CM * area)               # W/cm^3, mean element
        surface_mean = dt - q3 * cbar / k_cm
        hot_surface = surface_mean * f ** (1.0 / (1.0 + n))
        out.append(tp + hot_surface + f * q3 * c_tc / k_cm)
    return out


def rise_ratio_and_shape(meas: dict, t_tc: list[float]) -> dict:
    peak = base.PEAK_STATE - 1
    measured = meas["fuelTempC"][peak] - meas["fuelTempC"][0]
    predicted = t_tc[peak] - t_tc[0]
    h2 = max(abs(ht.theta(t_tc, s) - ht.theta(meas["fuelTempC"], s)) for s in ht.HELD_OUT)
    return {"predictedRiseK": predicted, "measuredRiseK": measured, "ratio": predicted / measured, "h2MaxDiff": h2}


def scaled_defect(lib, p_kw, t0_k, rising, h0, n, scale: float) -> float:
    """Power defect at the peak state when the law's mean fuel rise is multiplied by scale."""
    pool = base.pool_temperatures(len(p_kw), t0_k, rising)
    rho = [(lib.fuel_temp(tc + scale * ht.delta_t(p * 1e3, h0, n)) + lib.cool_temp(tc)) * base.PCM for p, tc in zip(p_kw, pool)]
    return -(rho[base.PEAK_STATE - 1] - rho[0])


def implied_coefficient(lib, meas, p_kw, t0_k, rising, h0, n, f, k_wmk, r_tc, n_elements) -> dict:
    """R: the mean fuel rise for which the chain reproduces the measured hot-element rise, and the defect ratio that rise implies."""
    pool = base.pool_temperatures(len(p_kw), t0_k, rising)
    peak = base.PEAK_STATE - 1
    target = meas["fuelTempC"][peak] - meas["fuelTempC"][0]

    def gap(scale):
        t = chain_temperatures(p_kw, pool, h0, n, f, k_wmk, r_tc, n_elements, scale)
        return (t[peak] - t[0]) - target

    if not gap(0.01) < 0 < gap(100.0):
        return {"note": "no scale between 0.01 and 100 reproduces the measured rise"}
    scale = ht._bisect(gap, 0.01, 100.0)
    dt_inf = scale * ht.delta_t(p_kw[peak] * 1e3, h0, n)
    defect = scaled_defect(lib, p_kw, t0_k, rising, h0, n, scale)
    r_alpha = meas["defectPcm"][peak] / defect
    return {"dTInfK": dt_inf, "scale": scale, "libraryDefectPcm": defect, "rAlpha": r_alpha, "consistent": R_CONSISTENT[0] <= r_alpha <= R_CONSISTENT[1]}


# ---------------------------------------------------------------- aggregation, decision, run

def tally(records: list[dict]) -> dict:
    labels = [r["label"] for r in records]
    ratios = [r["ratio"] for r in records]
    return {"n": len(records), "worst": base.worst(labels), "best": base.best(labels), "ratioMin": min(ratios), "ratioMax": max(ratios)}


def decide(entry: dict) -> dict:
    """The protocol's decision process, read on the primary line."""
    s1 = entry["stage1"]["primary"]["both"]
    g, hs, hp = entry["G"]["primary"], entry["H1shape"]["primary"], entry["H1pulse"]["primary"]
    if s1["median"] is None:
        return {"case": 3, "text": "Stage 1 not computed: the explanation is not found in these inputs."}
    ok = ("good", "plausible")
    if g["label"] in ok and hs["label"] == "fails" and hs["ratio"] > 1.0:
        return {"case": 1, "text": "peaking understood; the chain predicts a hotter thermocouple than measured (read R)."}
    if g["label"] == "fails" and g["ratio"] < G_BANDS[1][0] and hp["label"] in ok:
        return {"case": 2, "text": "the thermocouples sit in lower-peaking elements than the library's hottest B element; the data are consistent with the fitted law."}
    if hs["label"] == "fails" and hp["label"] == "fails":
        return {"case": 3, "text": "both variants fail: the explanation is not found in these inputs."}
    return {"case": None, "text": "none of the protocol's cases applies as written; read the metrics."}


def run(libs: dict, records, meas: dict | None = None) -> dict:
    meas = meas or base.load_measured()
    t0_options = {"T0=25.8C(Table1)": meas["fuelTempC"][0] + base.K0, "T0=30.8C(Table2)": meas["fuelTempC_table2_first_row"] + base.K0}
    axes = {"pCalculated": meas["pCalculatedKW"], "pIndicated": meas["pIndicatedKW"]}
    pools = {"pool-constant": False, "pool-rising-6K": True}
    peak = base.PEAK_STATE - 1
    reg_step = meas["states"][peak]["regulatingRodStep"]
    report: dict = {"protocol": "docs/validation/m7-hot-element-protocol.md", "libraries": {}}

    for name, lib in libs.items():
        s1 = stage1(records, lib, CORE_NUMBER.get(name, name))
        f_tc_variants = [v["both"]["median"] for v in s1["variants"].values() if v["both"]["median"] is not None]
        f_tc_primary = s1["primary"]["both"]["median"]
        rods = {r: 1.0 for r in lib.rod_by_id}
        rods["regulating"] = base._x(reg_step)

        lines = {"pulse": [], "shape": [], "G": []}
        primary = {}
        cases = []
        for ci, ((t0_label, t0), (axis_label, powers), (pool_label, rising)) in enumerate(itertools.product(t0_options.items(), axes.items(), pools.items())):
            targets = {s: meas["defectPcm"][s - 1] for s in ht.CALIBRATION}
            fit = ht.calibrate_law(lib, powers, t0, rising, targets)
            case = {"case": [t0_label, axis_label, pool_label]}
            if fit is None:
                case["note"] = "no (h0, n) reproduces both calibration states"
                cases.append(case)
                continue
            h0, n = fit
            pool = base.pool_temperatures(len(powers), t0, rising)
            t_fuel_peak = ht.law_states(lib, powers, t0, rising, h0, n)[peak]["tFuelK"]
            sp = shape_peakings(lib, rods, t_fuel_peak)
            prim_e = primary_element(sp)
            f_shape_primary = sp["B"][prim_e]["centre"]
            n_el = sp["elementsWithPower"]
            shape_variants = {f"{e}|{kind}": v[kind] for e, v in sp["B"].items() for kind in ("centre", "hottest")}
            case.update({"h0": h0, "n": n, "elementsWithPower": n_el, "primaryElement": prim_e, "fShapePrimary": f_shape_primary,
                         "fShapeB": sp["B"], "tFuelPeakK": t_fuel_peak})
            case["hotElement"] = {}
            for label, f in (("H-pulse", f_tc_primary), ("H-shape", f_shape_primary)):
                if f is None:
                    case["hotElement"][label] = {"note": "not computed"}
                    continue
                t_tc = chain_temperatures(powers, pool, h0, n, f, K_PRIMARY, R_TC_PRIMARY, n_el)
                case["hotElement"][label] = {"F": f, **rise_ratio_and_shape(meas, t_tc),
                                             "R": implied_coefficient(lib, meas, powers, t0, rising, h0, n, f, K_PRIMARY, R_TC_PRIMARY, n_el)}
            if f_tc_primary is not None:
                case["G"] = f_tc_primary / f_shape_primary
            cases.append(case)

            # sensitivities: the worst and best over the table's lists
            for k, r_tc in itertools.product((K_PRIMARY, *K_SENS), (R_TC_PRIMARY, *R_TC_SENS)):
                for f in f_tc_variants:
                    t_tc = chain_temperatures(powers, pool, h0, n, f, k, r_tc, n_el)
                    m = rise_ratio_and_shape(meas, t_tc)
                    lines["pulse"].append({"ratio": m["ratio"], "label": label_ratio(m["ratio"], H1_BANDS), "h2": m["h2MaxDiff"]})
                for f in shape_variants.values():
                    t_tc = chain_temperatures(powers, pool, h0, n, f, k, r_tc, n_el)
                    m = rise_ratio_and_shape(meas, t_tc)
                    lines["shape"].append({"ratio": m["ratio"], "label": label_ratio(m["ratio"], H1_BANDS), "h2": m["h2MaxDiff"]})
            for ft in f_tc_variants:
                for fs in shape_variants.values():
                    lines["G"].append({"ratio": ft / fs, "label": label_ratio(ft / fs, G_BANDS)})
            if ci == 0:
                primary = case

        entry = {"id": lib.id, "status": lib.status, "stage1": s1, "cases": cases}
        prim = primary.get("hotElement", {}) if primary else {}
        for key, line, label in (("H1pulse", "pulse", "H-pulse"), ("H1shape", "shape", "H-shape")):
            h = prim.get(label, {})
            entry[key] = {"primary": {"label": label_ratio(h["ratio"], H1_BANDS), "ratio": h["ratio"]} if "ratio" in h else {"label": "not computed", "ratio": None},
                          "sensitivities": tally(lines[line]) if lines[line] else None}
            entry[key]["h2"] = {"primary": h.get("h2MaxDiff"), "label": base.label_diff("C", h["h2MaxDiff"]) if "h2MaxDiff" in h else "not computed",
                                "worstOverSensitivities": max((r["h2"] for r in lines[line]), default=None)}
        g = primary.get("G")
        entry["G"] = {"primary": {"label": label_ratio(g, G_BANDS) if g is not None else "not computed", "ratio": g}, "sensitivities": tally(lines["G"]) if lines["G"] else None}
        entry["decision"] = decide(entry) if g is not None and entry["H1shape"]["primary"]["ratio"] is not None and entry["H1pulse"]["primary"]["ratio"] is not None else \
            {"case": 3, "text": "Stage 1 not computed (or no fit): the explanation is not found in these inputs."}
        report["libraries"][name] = entry
    return report


def print_summary(report: dict) -> None:
    print("protocol:", report["protocol"])
    for name, e in report["libraries"].items():
        print(f"\n{name} ({e['id']}, {e['status']})")
        p = e["stage1"]["primary"]
        print(f"  pulses by core_config: {e['stage1']['coreConfigCounts']}")
        print(f"  F_tc primary: both {p['both']}  tc1 {p['tc1']['median']}  tc2 {p['tc2']['median']}")
        for key in ("G", "H1pulse", "H1shape"):
            v = e[key]
            s = v["sensitivities"]
            tail = f"  worst {s['worst']} best {s['best']} ratio {s['ratioMin']:.2f}-{s['ratioMax']:.2f}" if s else ""
            print(f"  {key}: primary {v['primary']['label']} (ratio {v['primary']['ratio']}){tail}")
            if "h2" in v:
                print(f"     H2: primary {v['h2']['label']} ({v['h2']['primary']}), worst over sensitivities {v['h2']['worstOverSensitivities']}")
        print(f"  decision: case {e['decision']['case']}: {e['decision']['text']}")


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
