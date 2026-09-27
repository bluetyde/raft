"""Infer each pulse's inserted reactivity from its own trace, independently of the database's $ labels.

Before feedback starts, a pulse rises exponentially at a rate omega set by the prompt excess and the generation time
(omega ~ (rho - beta) / Lambda). Fuel temperature feedback, fuel mass and gamma don't enter, and neither does the
label. omega is fitted the same way on the measured trace and on the reference engine run over a grid of $,
so delayed neutrons and the transient rod's finite ejection are in the model, and the engine curve omega($) is
inverted to give each pulse's inferred $.

Fit: least squares of ln(P - baseline) against t over the contiguous rising segment just before the peak where
P is between `lo` and `hi` times the peak (baseline = median of the first 0.2 s of the window, noise = its spread).

Usage (from the repo root, after validation.fetch_trace_windows):  python -m validation.trace_period --cores 242 246
"""
from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path

from physics_ref import Engine, Library
from validation.c1_comparison import LIBRARY_PATH, transient_start_position

REPO_ROOT = Path(__file__).resolve().parents[1]
TRACES = REPO_ROOT / "validation" / "data" / "jsi-pulses" / "traces"
SUMMARY = REPO_ROOT / "validation" / "data" / "jsi-pulses" / "pulses_summary.json"
LO, HI = 0.02, 0.20
SIM_DT = 5e-5          # engine outer step for the reference curve, same as the measurement interval
DOLLAR_GRID = [1.05 + 0.05 * k for k in range(24)]   # $1.05 ... $2.20


def load_window(pid: int) -> tuple[list[float], float]:
    meta = json.loads((TRACES / f"{pid}.json").read_text(encoding="utf-8"))
    raw = (TRACES / meta["file"]).read_bytes()
    n = len(raw) // 12
    power = [struct.unpack_from("<3f", raw, 12 * k)[0] for k in range(n)]
    return power, meta["dt"]


def fit_omega(power: list[float], dt: float, lo: float = LO, hi: float = HI, clean: bool = False):
    """Return (omega [1/s], points used, noise [MW]) or None if the rise is too short or too noisy to fit.

    clean=True (engine output): baseline 0 and no noise, instead of estimating both from the first 0.2 s."""
    if clean:
        base = noise = 0.0
    else:
        head = sorted(power[: max(10, int(0.2 / dt))])
        base = head[len(head) // 2]
        noise = (head[int(0.84 * len(head))] - head[int(0.16 * len(head))]) / 2.0
    peak_i = 0
    for k in range(1, len(power)):
        if power[k] > power[peak_i]:
            peak_i = k
    pmax = power[peak_i] - base
    lo_abs = max(lo * pmax, 10.0 * noise)
    hi_abs = hi * pmax
    if lo_abs >= hi_abs / 3.0:
        return None
    k = peak_i
    while k > 0 and power[k] - base > hi_abs:
        k -= 1
    end = k
    while k > 0 and power[k] - base > lo_abs:
        k -= 1
    start = k + 1
    if end - start < 8:
        return None
    n = sx = sy = sxx = sxy = 0.0
    for i in range(start, end + 1):
        x, y = i * dt, math.log(power[i] - base)
        n += 1; sx += x; sy += y; sxx += x * x; sxy += x * y
    omega = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return omega, int(n), noise


def pulse_engine(library_path: Path, dollars: float, outer_dt: float, p0: float = 1.0) -> Engine:
    """Engine set up as in C1: other rods out, transient rod at the position that inserts `dollars`, exactly critical
    (test-only calibration offset), source off, P0 = p0 W, pulse mode, rod fire submitted."""
    lib = Library(library_path)
    lib.ext_source = 0.0
    x0 = transient_start_position(lib, dollars)
    rods = {r.id: 1.0 for r in lib.rods}
    rods["transient"] = x0
    rho_rods = 0.0
    for r in lib.rods:
        rho_rods += r.worth(rods[r.id])
    lib.calibration = -(lib.ref_rho + rho_rods)
    lib.mark_modified(f"pulse:d={dollars!r}:p0={p0!r}")
    e = Engine(lib, {"rods": rods, "mode": "pulse", "power": {"mode": "critical-equilibrium", "value": p0}},
               config={"outerDt": outer_dt})
    e.submit({"type": "rod.fire", "rod": "transient"})
    return e


def engine_trace(dollars: float, p0: float = 1.0, t_max: float = 1.5, library_path: Path = LIBRARY_PATH) -> list[float]:
    """Power [MW] every SIM_DT for a pulse of `dollars` fired from critical at p0 W (same setup as C1)."""
    e = pulse_engine(library_path, dollars, SIM_DT, p0)
    out = []
    while e.t < t_max:
        if e.halted:  # a halted engine makes no progress (M1 review finding 3)
            raise RuntimeError(f"engine halted: {e.halted}")
        e.step()
        out.append(e.snapshot()["truth"]["power"] / 1e6)
        if e.t > e.peak_time + 0.1 and out[-1] < 0.01 * e.peak_power / 1e6:
            break
    return out


def model_curve(library_path: Path = LIBRARY_PATH) -> list[tuple[float, float]]:
    curve = []
    for d in DOLLAR_GRID:
        fit = fit_omega(engine_trace(d, library_path=library_path), SIM_DT, clean=True)
        if fit:
            curve.append((d, fit[0]))
    return curve


def invert(curve: list[tuple[float, float]], omega: float):
    for (d0, w0), (d1, w1) in zip(curve, curve[1:]):
        if w0 <= omega <= w1:
            return d0 + (d1 - d0) * (omega - w0) / (w1 - w0)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cores", nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "validation" / "trace_period_report.json")
    args = ap.parse_args(argv)
    curve = model_curve()
    pulses = {p["pulse_id"]: p for p in json.loads(SUMMARY.read_text(encoding="utf-8"))["pulses"]}
    rows = []
    for meta_path in sorted(TRACES.glob("*.json")):
        pid = int(meta_path.stem)
        p = pulses[pid]
        if str(p["core_config"]) not in args.cores or p.get("rho_dollars") is None:
            continue
        power, dt = load_window(pid)
        fit = fit_omega(power, dt)
        row = {"pulse_id": pid, "core": str(p["core_config"]), "date": p["date"], "label": p["rho_dollars"],
               "rod_position": p.get("rod_position"), "peak_mw": p.get("peak_power_mw")}
        if fit:
            row.update({"omega": fit[0], "points": fit[1], "noise_mw": fit[2], "inferred": invert(curve, fit[0])})
        rows.append(row)
    report = {"method": __doc__.split("\n\n")[1], "lo": LO, "hi": HI, "modelCurve": curve, "pulses": rows}
    args.out.write_bytes((json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"))
    fitted = [r for r in rows if r.get("inferred") is not None]
    print(f"model curve: {[(round(d, 2), round(w, 1)) for d, w in curve]}")
    print(f"{len(rows)} pulses, {len(fitted)} with an inferred $; report {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
