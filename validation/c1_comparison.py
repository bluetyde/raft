"""M1 comparison C1: condition-matched pulse comparison, as fixed in docs/validation/m1-c1-protocol.md.

Usage (repo root):  python -m validation.c1_comparison [--out validation/c1_report.json]

Scores simulated peak power against screened JSI pulses of ONE core configuration (246), with a single
labelled calibration (a scale factor s on the fuel-temperature reactivity table) fitted on odd pulse ids and
evaluated on even ones, then transferred unchanged to core 242. Pulses are started by firing the transient
rod (finite ejection ramp), not by an instant reactivity step. No verdict is decided here: the thresholds
from the protocol are evaluated and the result is proposed to the user.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

from physics_ref import Engine, Library
from physics_ref.engine import IEP, IP, ITF
from physics_ref.library import Table
from validation.pulse_loader import load_pulse_summary
from validation.pulse_screening import SCREEN_VERSION, screen_pulses

REPO_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = REPO_ROOT / "libraries" / "triga-jsi"
DEFAULT_OUT = Path(__file__).resolve().parent / "c1_report.json"

PRIMARY_CORE = "246"
CROSS_CORE = "242"
MIN_DOLLARS = 1.05
SCORE_FROM = 1.30              # d >= this is scored (primary groups)
S_BOUNDS = (0.25, 4.0)
OUTER_DT = 0.005
P0_DEFAULT = 1.0               # W, pre-pulse power (assumption; sensitivity reported)
DOLLAR_SHIFT = 0.05            # $ uncertainty probe
THRESHOLDS = {"H1_rms_heldout_246": math.log(1.5), "H2_rms_cross_242": math.log(2.0), "H3_s_range": [0.5, 2.0]}


@dataclass(frozen=True)
class SimResult:
    dollars: float
    s: float
    p0: float
    x0: float
    peak_power_w: float
    peak_time_s: float
    energy_j: float
    max_fuel_rise_k: float


def _fresh_library(s: float) -> Library:
    lib = Library(LIBRARY_PATH)
    t = lib.fuel_temp
    lib.fuel_temp = Table(t.xs, [s * y for y in t.ys], t.out_of_range)
    lib.ext_source = 0.0
    return lib


def transient_start_position(lib: Library, dollars: float) -> float:
    """x0 such that firing the transient rod from x0 to fully out inserts dollars * beta (bisection)."""
    w = lib.rod_by_id["transient"].worth
    target = dollars * lib.beta_total
    if target > w(1.0) - w(0.0) + 1e-15:
        raise ValueError(f"${dollars} exceeds the transient rod's worth")
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if w(1.0) - w(mid) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def simulate(dollars: float, s: float = 1.0, p0: float = P0_DEFAULT, t_max: float = 10.0) -> SimResult:
    lib = _fresh_library(s)
    x0 = transient_start_position(lib, dollars)
    rods = {r.id: 1.0 for r in lib.rods}
    rods["transient"] = x0
    rho_rods = 0.0
    for r in lib.rods:
        rho_rods += r.worth(rods[r.id])
    lib.calibration = -(lib.ref_rho + rho_rods)          # test-only: this state is exactly critical
    lib.mark_modified(f"c1:d={dollars!r}:s={s!r}:p0={p0!r}")
    e = Engine(lib, {"rods": rods, "mode": "pulse", "power": {"mode": "critical-equilibrium", "value": p0}},
               config={"outerDt": OUTER_DT})
    tf0 = e.y[ITF]
    max_tf = tf0
    seq = e.submit({"type": "rod.fire", "rod": "transient"})
    e.step()
    status = next(ev for ev in e.events if ev.get("seq") == seq)
    if status["status"] != "accepted":
        raise RuntimeError(f"fire rejected: {status}")
    while e.t < t_max:
        if e.halted:  # a halted engine makes no progress (M1 review finding 3)
            raise RuntimeError(f"engine halted: {e.halted}")
        e.step()
        max_tf = max(max_tf, e.y[ITF])
        if e.t > e.peak_time + 0.2 and e.y[IP] < 0.01 * e.peak_power and e.peak_power > 10 * p0:
            break
    return SimResult(dollars, s, p0, x0, e.peak_power, e.peak_time, e.y[IEP], max_tf - tf0)


class SimCache:
    def __init__(self):
        self._c: dict[tuple, SimResult] = {}

    def get(self, dollars: float, s: float, p0: float = P0_DEFAULT) -> SimResult:
        key = (round(dollars, 6), s, p0)
        if key not in self._c:
            self._c[key] = simulate(dollars, s, p0)
        return self._c[key]


def core_pulses(core: str):
    res = screen_pulses(load_pulse_summary())
    return sorted((p for p in res.kept if p.core_config == core and p.rho_dollars is not None
                   and p.rho_dollars >= MIN_DOLLARS and p.peak_power_mw), key=lambda p: p.pulse_id)


def errors(pulses, cache: SimCache, s: float, shift: float = 0.0, p0: float = P0_DEFAULT):
    out = []
    for p in pulses:
        d = p.rho_dollars + shift
        sim = cache.get(d, s, p0)
        out.append(math.log(sim.peak_power_w / (p.peak_power_mw * 1e6)))
    return out


def rms(v):
    return math.sqrt(sum(x * x for x in v) / len(v)) if v else None


def mean(v):
    return sum(v) / len(v) if v else None


def fit_s(cal, cache: SimCache) -> float:
    """Golden-section search for s minimizing the sum of squared log errors on the calibration pulses."""
    f = lambda s: sum(x * x for x in errors(cal, cache, s))
    lo, hi = math.log(S_BOUNDS[0]), math.log(S_BOUNDS[1])
    g = (math.sqrt(5) - 1) / 2
    a, b = hi - g * (hi - lo), lo + g * (hi - lo)
    fa, fb = f(math.exp(a)), f(math.exp(b))
    for _ in range(30):
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - g * (hi - lo)
            fa = f(math.exp(a))
        else:
            lo, a, fa = a, b, fb
            b = lo + g * (hi - lo)
            fb = f(math.exp(b))
        if hi - lo < 1e-3:
            break
    return round(math.exp(0.5 * (lo + hi)), 4)


def group_stats(pulses, cache, s, label):
    e = errors(pulses, cache, s)
    stats = {"group": label, "n": len(pulses), "rms": rms(e), "bias": mean(e)}
    for shift in (-DOLLAR_SHIFT, DOLLAR_SHIFT):
        es = errors(pulses, cache, s, shift)
        stats[f"rms_shift_{shift:+.2f}"] = rms(es)
    return stats


def per_dollar_table(pulses, cache, s):
    by = {}
    for p in pulses:
        by.setdefault(p.rho_dollars, []).append(p)
    rows = []
    for d in sorted(by):
        g = by[d]
        sim = cache.get(d, s)
        med = sorted(q.peak_power_mw for q in g)[len(g) // 2]
        t1 = sorted(q.t1_max_c for q in g if q.t1_max_c is not None)
        e1000 = sorted(q.energy_1000pts_mws for q in g if q.energy_1000pts_mws is not None)
        rows.append({"dollars": d, "n": len(g), "exp_peak_mw_median": med, "sim_peak_mw": sim.peak_power_w / 1e6,
                     "ratio": sim.peak_power_w / 1e6 / med,
                     "exp_e1000_mws_median": e1000[len(e1000) // 2] if e1000 else None, "sim_energy_mws": sim.energy_j / 1e6,
                     "exp_t1_median_c": t1[len(t1) // 2] if t1 else None, "sim_fuel_rise_k": sim.max_fuel_rise_k,
                     "sim_peak_time_s": sim.peak_time_s})
    return rows


def run() -> dict:
    cache = SimCache()
    p246 = core_pulses(PRIMARY_CORE)
    p242 = core_pulses(CROSS_CORE)
    cal = [p for p in p246 if p.pulse_id % 2 == 1 and p.rho_dollars >= SCORE_FROM]
    held = [p for p in p246 if p.pulse_id % 2 == 0]
    held_hi = [p for p in held if p.rho_dollars >= SCORE_FROM]
    held_lo = [p for p in held if p.rho_dollars < SCORE_FROM]
    cross = [p for p in p242 if p.rho_dollars >= SCORE_FROM]

    s_fit = fit_s(cal, cache)
    report = {
        "protocol": "docs/validation/m1-c1-protocol.md",
        "screenVersion": SCREEN_VERSION,
        "library": str(LIBRARY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "assumptions": {"p0_w": P0_DEFAULT, "outerDt_s": OUTER_DT, "fireTime_s": "library (assumed 0.08)"},
        "counts": {"core246": len(p246), "calibration": len(cal), "heldout_hi": len(held_hi), "heldout_lo": len(held_lo),
                   "core242_scored": len(cross)},
        "s_fit": s_fit,
        "uncalibrated": [group_stats(held_hi, cache, 1.0, "heldout246_d>=1.30"),
                         group_stats(held_lo, cache, 1.0, "heldout246_d<1.30"),
                         group_stats(cross, cache, 1.0, "core242_d>=1.30")],
        "calibrated": [group_stats(held_hi, cache, s_fit, "heldout246_d>=1.30"),
                       group_stats(held_lo, cache, s_fit, "heldout246_d<1.30"),
                       group_stats(cross, cache, s_fit, "core242_d>=1.30")],
        "p0_sensitivity": {"p0_w": 100.0, "heldout246_hi_rms": rms(errors(held_hi, cache, s_fit, p0=100.0))},
        "table246_calibrated": per_dollar_table(p246, cache, s_fit),
        "table242_calibrated": per_dollar_table(p242, cache, s_fit),
        "thresholds": THRESHOLDS,
    }
    h1 = report["calibrated"][0]["rms"]
    h2 = report["calibrated"][2]["rms"]
    report["checks"] = {
        "H1": {"value": h1, "pass": h1 <= THRESHOLDS["H1_rms_heldout_246"]},
        "H2": {"value": h2, "pass": h2 <= THRESHOLDS["H2_rms_cross_242"]},
        "H3": {"value": s_fit, "pass": THRESHOLDS["H3_s_range"][0] <= s_fit <= THRESHOLDS["H3_s_range"][1]},
    }
    report["proposal"] = "GO" if all(c["pass"] for c in report["checks"].values()) else "NO-GO"
    report["note"] = "Proposal only; the decision is the user's (protocol)."
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="M1 comparison C1 (see docs/validation/m1-c1-protocol.md)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    report = run()
    args.out.write_bytes((json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"))
    print(json.dumps({k: report[k] for k in ("s_fit", "checks", "proposal")}, indent=1))
    for g in report["calibrated"]:
        print(f"calibrated   {g['group']:22} n={g['n']:3d} rms={g['rms']:.3f} bias={g['bias']:+.3f}")
    for g in report["uncalibrated"]:
        print(f"uncalibrated {g['group']:22} n={g['n']:3d} rms={g['rms']:.3f} bias={g['bias']:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
