"""M1 run 3, exactly as fixed in docs/validation/m1-run3-protocol.md (committed 053c4c3 before this code).

Part A: code-to-code. The engine with svajger2024 Table 10's inputs (libraries/triga-jsi-paper) against Fuchs-Hansen.
Part B: code-to-data per core, on the trace-inferred $ axis, with each core's own library and no calibration.

Usage (from the repo root; needs the trace windows from validation.fetch_trace_windows):
    python -m validation.m1_run3 [--out validation/m1_run3_report.json]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from physics_ref import Library
from validation.trace_period import SUMMARY, TRACES, fit_omega, invert, load_window, model_curve, pulse_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
LIBS = {core: REPO_ROOT / "libraries" / f"triga-jsi-{core}" for core in ("242", "246", "paper")}
OUTER_DT = 0.005                     # as in C1
A_POINTS = [1.5, 1.8, 2.1]
A_RANGE = (0.75, 1.02)
B_MIN_DOLLARS = 1.30
B_GRID = [1.25 + 0.025 * k for k in range(27)]    # $1.25 ... $1.90 (protocol said $1.275 ... $1.75; extended so every pulse and the +-$0.03 shifts fit, before any metric was seen)
B_RMS, B_BIAS, B_SLOPE, B_MIN_N = math.log(1.5), math.log(1.3), 0.4, 20
SHIFT = 0.03


def peak_power(library_path: Path, dollars: float) -> float:
    """Peak power [W] of a pulse set up as in C1 (run until < 1% of peak and >= 0.2 s after it, or 10 s)."""
    e = pulse_engine(library_path, dollars, OUTER_DT)
    while e.t < 10.0:
        e.step()
        if e.t > e.peak_time + 0.2 and e.snapshot()["truth"]["power"] < 0.01 * e.peak_power and e.peak_power > 10.0:
            break
    return e.peak_power


def part_a() -> dict:
    lib = Library(LIBS["paper"])
    gamma = -lib.fuel_temp(lib.ref_tfuel + 1.0) / (lib.fuel_mass * lib.fuel_cp(lib.ref_tfuel))   # linear table: exact
    rows = []
    for d in A_POINTS:
        rho_p = (d - 1.0) * lib.beta_total
        fh = rho_p * rho_p / (2.0 * gamma * lib.gen_time)
        sim = peak_power(LIBS["paper"], d)
        rows.append({"dollars": d, "engine_w": sim, "fh_w": fh, "ratio": sim / fh})
    ok = all(A_RANGE[0] <= r["ratio"] <= A_RANGE[1] for r in rows)
    return {"gamma": gamma, "points": rows, "A1": {"range": list(A_RANGE), "pass": ok}}


def _slope(pts: list[tuple[float, float]]) -> float:
    n = sx = sy = sxx = sxy = 0.0
    for x, y in pts:
        n += 1; sx += x; sy += y; sxx += x * x; sxy += x * y
    return (n * sxy - sx * sy) / (n * sxx - sx * sx)


def _interp_ln(grid: list[tuple[float, float]], d: float) -> float:
    for (d0, l0), (d1, l1) in zip(grid, grid[1:]):
        if d0 <= d <= d1:
            return l0 + (l1 - l0) * (d - d0) / (d1 - d0)
    raise ValueError(f"${d} outside the simulation grid")


def _metrics(pulses: list[dict], grid: list[tuple[float, float]], shift: float = 0.0) -> dict:
    e, exp_pts, sim_pts = [], [], []
    for p in pulses:
        d = p["inferred"] + shift
        ln_sim = _interp_ln(grid, d)
        e.append(ln_sim - math.log(p["peak_mw"] * 1e6))
        exp_pts.append((math.log(d - 1.0), math.log(p["peak_mw"] * 1e6)))
        sim_pts.append((math.log(d - 1.0), ln_sim))
    mean = 0.0
    for v in e:
        mean += v
    mean /= len(e)
    ss = 0.0
    for v in e:
        ss += v * v
    return {"n": len(e), "rms": math.sqrt(ss / len(e)), "bias": mean,
            "slope_exp": _slope(exp_pts), "slope_sim": _slope(sim_pts)}


def part_b(core: str) -> dict:
    curve = model_curve(LIBS[core])
    summary = {p["pulse_id"]: p for p in json.loads(SUMMARY.read_text(encoding="utf-8"))["pulses"]}
    pulses, fitted = [], 0
    for meta in sorted(TRACES.glob("*.json")):
        pid = int(meta.stem)
        s = summary[pid]
        if str(s["core_config"]) != core or not s.get("peak_power_mw"):
            continue
        fit = fit_omega(*load_window(pid))
        if not fit:
            continue
        fitted += 1
        d = invert(curve, fit[0])
        if d is not None and d >= B_MIN_DOLLARS:
            pulses.append({"pulse_id": pid, "date": s["date"], "label": s["rho_dollars"], "omega": fit[0],
                           "inferred": d, "peak_mw": s["peak_power_mw"]})
    grid = [(d, math.log(peak_power(LIBS[core], d))) for d in B_GRID]
    out = {"modelCurve": curve, "fitted": fitted, "used": len(pulses), "grid": grid, "pulses": pulses}
    if len(pulses) < B_MIN_N:
        out["B4"] = {"pass": False, "untestable": True}
        return out
    m = _metrics(pulses, grid)
    out.update({"metrics": m,
                "shift+": _metrics(pulses, grid, SHIFT) if max(p["inferred"] for p in pulses) + SHIFT <= B_GRID[-1] else None,
                "shift-": _metrics(pulses, grid, -SHIFT),
                "B1": {"threshold": B_RMS, "pass": m["rms"] <= B_RMS},
                "B2": {"threshold": B_BIAS, "pass": abs(m["bias"]) <= B_BIAS},
                "B3": {"threshold": B_SLOPE, "pass": abs(m["slope_exp"] - m["slope_sim"]) <= B_SLOPE},
                "B4": {"threshold": B_MIN_N, "pass": True}})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "validation" / "m1_run3_report.json")
    args = ap.parse_args(argv)
    report = {"protocol": "docs/validation/m1-run3-protocol.md (053c4c3)", "A": part_a(), "B": {c: part_b(c) for c in ("242", "246")}}
    b_ok = all(all(report["B"][c].get(k, {}).get("pass", False) for k in ("B1", "B2", "B3", "B4")) for c in ("242", "246"))
    report["proposal"] = "GO" if report["A"]["A1"]["pass"] and b_ok else "NO-GO"
    args.out.write_bytes((json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"))
    print(json.dumps({"A": [(r["dollars"], round(r["ratio"], 3)) for r in report["A"]["points"]], "A1": report["A"]["A1"]["pass"],
                      "B": {c: {k: report["B"][c].get(k) for k in ("fitted", "used", "metrics", "B1", "B2", "B3", "B4")} for c in ("242", "246")},
                      "proposal": report["proposal"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
