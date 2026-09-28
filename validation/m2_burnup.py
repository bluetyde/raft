"""M2 burnup calibration and tests, as fixed in docs/validation/m2-burnup-protocol.md.

Fit: B246 = the uniform burnup at which core 246 at its critical rods (T up, K 536.6, V up, R 535; pungercic2024) has k = 1.
Tests: T1 core 242's critical state at B246; T2 the burnup reactivity coefficient around B246; T3 B246 vs the open burnups;
T4 core 242's transient rod worth in dollars at B246.

Run in the openmc-vr env (WSL), from the repo root:  python -m validation.m2_burnup [--grid 14 16 ... 28] [--out report.json]
Each point is one pipeline.openmc.core_model run (20,000 x 150, 50 inactive, about a minute).
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROD_246 = "T=0,K=536.6,V=200,R=535"
ROD_242 = "T=0,K=499,V=200,R=500"
ROD_242_T_IN = "T=900,K=499,V=200,R=500"
COEF_MEAS, COEF_MEAS_STD = -232.8, 19.8          # pcm per MWd/kg, pungercic2024 Table 7 (cores 216-232)
T1_BOUND_PCM = 500.0                              # pungercic2021: 1 sigma of an absolute excess reactivity measurement
TABLE_PCM_PER_DOLLAR = 700.0                      # the s242 rod table's pcm are dollars x 700 pcm (m2-core.md)
T_WORTH_TABLE_PCM = 3034.0


def run_point(core: str, rods: str, burnup: float, log: Path, extra=()) -> dict:
    cmd = [sys.executable, "-B", "-m", "pipeline.openmc.core_model", "--core", core, "--rods", rods,
           "--burnup", str(burnup), "--json", str(log), *extra]
    before = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    after = log.read_text(encoding="utf-8").splitlines()
    if len(after) != len(before) + 1:
        raise RuntimeError(f"expected one new result line from {cmd}")
    r = json.loads(after[-1])
    r["burnup"] = burnup
    return r


def rho(k: float) -> float:
    return (k - 1.0) / k * 1e5


def rho_std(r: dict) -> float:
    return r["kStd"] / r["k"] ** 2 * 1e5


def crossing_std(b0: float, b1: float, r0: float, r1: float, s0: float, s1: float) -> float:
    """Standard deviation of the zero crossing B = b0 + r0 (b1 - b0) / (r0 - r1) of the line through (b0, r0) and (b1, r1),
    with independent errors s0, s1 on r0, r1: first-order propagation through the actual interpolation (Codex M2 review,
    finding 14; the first version used equal weights and the T2 slope, 0.256 instead of 0.219 MWd/kg for the committed run)."""
    d = (r0 - r1) ** 2
    dB_dr0 = -r1 * (b1 - b0) / d
    dB_dr1 = r0 * (b1 - b0) / d
    return math.hypot(dB_dr0 * s0, dB_dr1 * s1)


def linfit(xs, ys, ss):
    """Weighted least squares y = a + b x; returns (a, b, cov)."""
    w = [1 / s ** 2 for s in ss]
    S, Sx, Sy = sum(w), sum(wi * x for wi, x in zip(w, xs)), sum(wi * y for wi, y in zip(w, ys))
    Sxx, Sxy = sum(wi * x * x for wi, x in zip(w, xs)), sum(wi * x * y for wi, x, y in zip(w, xs, ys))
    D = S * Sxx - Sx ** 2
    a, b = (Sxx * Sy - Sx * Sxy) / D, (S * Sxy - Sx * Sy) / D
    return a, b, [[Sxx / D, -Sx / D], [-Sx / D, S / D]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--grid", type=float, nargs="+", default=[14, 16, 18, 20, 22, 24, 26, 28])
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "validation" / "m2_burnup_report.json")
    a = ap.parse_args(argv)
    log = Path(tempfile.mkdtemp()) / "points.jsonl"

    grid = [run_point("246", ROD_246, b, log) for b in a.grid]
    rhos = [rho(r["k"]) for r in grid]
    cross = [i for i in range(len(grid) - 1) if rhos[i] >= 0 > rhos[i + 1]]
    if not cross:
        raise SystemExit(f"k = 1 not bracketed by the grid {a.grid}: rho = {[round(x) for x in rhos]}")
    i = cross[0]
    b0, b1, r0, r1 = a.grid[i], a.grid[i + 1], rhos[i], rhos[i + 1]
    b246 = b0 + r0 / (r0 - r1) * (b1 - b0)

    # T2: slope over B246 +- 3 MWd/kg (grid points inside that window, at least 2)
    win = [(b, x, rho_std(r)) for b, x, r in zip(a.grid, rhos, grid) if abs(b - b246) <= 3.0 + 1e-9]
    if len(win) < 2:
        raise SystemExit("fewer than two grid points within B246 +- 3 MWd/kg")
    _, slope, cov = linfit([w[0] for w in win], [w[1] for w in win], [w[2] for w in win])
    slope_std = math.sqrt(cov[1][1])
    z2 = (slope - COEF_MEAS) / math.hypot(slope_std, COEF_MEAS_STD)
    # uncertainty of B246 from the two bracketing points' statistics
    b246_std = crossing_std(b0, b1, r0, r1, rho_std(grid[i]), rho_std(grid[i + 1]))

    t1 = run_point("242", ROD_242, b246, log, ["--kinetics"])
    t4 = run_point("242", ROD_242_T_IN, b246, log)
    rho1 = rho(t1["k"])
    beta = t1["betaEff"]
    worth_pcm = rho1 - rho(t4["k"])
    worth_std = math.hypot(rho_std(t1), rho_std(t4))

    rep = {
        "protocol": "docs/validation/m2-burnup-protocol.md",
        "grid246": [{"burnup": b, "k": r["k"], "kStd": r["kStd"], "rhoPcm": x} for b, r, x in zip(a.grid, grid, rhos)],
        "B246": b246, "B246Std": b246_std,
        "T1": {"rhoPcm": rho1, "rhoStdPcm": rho_std(t1), "boundPcm": T1_BOUND_PCM, "pass": abs(rho1) <= T1_BOUND_PCM},
        "T2": {"slopePcmPerMWdKg": slope, "slopeStd": slope_std, "measured": COEF_MEAS, "measuredStd": COEF_MEAS_STD,
               "z": z2, "pass": abs(z2) <= 2.0, "points": [w[0] for w in win]},
        "T3": {"B246": b246, "openRange": [1.9, 21.0], "typical": 20.0, "flag": not 0.0 <= b246 <= 30.0},
        "T4": {"worthPcm": worth_pcm, "worthStdPcm": worth_std, "betaEffPcm": beta * 1e5, "betaEffStdPcm": t1["betaEffStd"] * 1e5,
               "lambdaUs": t1["lambdaS"] * 1e6, "worthDollars": worth_pcm / (beta * 1e5),
               "tableDollars": T_WORTH_TABLE_PCM / TABLE_PCM_PER_DOLLAR, "freshDollars": 2694.0 / 737.0},
        "points": [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()],
    }
    a.out.write_bytes((json.dumps(rep, indent=1) + "\n").encode("utf-8"))
    print(f"B246 = {b246:.2f} +- {b246_std:.2f} MWd/kg (effective)")
    print(f"T1 core 242 critical state: rho = {rho1:+.0f} +- {rho_std(t1):.0f} pcm (bound 500) -> {'PASS' if rep['T1']['pass'] else 'FAIL'}")
    print(f"T2 slope {slope:.1f} +- {slope_std:.1f} vs {COEF_MEAS} +- {COEF_MEAS_STD} pcm/(MWd/kg), z = {z2:+.2f} -> "
          f"{'PASS' if rep['T2']['pass'] else 'FAIL'}")
    print(f"T3 B246 {b246:.1f} vs open 1.9-21.0 (typical ~20){'  FLAG' if rep['T3']['flag'] else ''}")
    print(f"T4 transient worth {worth_pcm:.0f} +- {worth_std:.0f} pcm = ${rep['T4']['worthDollars']:.2f} (beta_eff {beta*1e5:.0f} pcm); "
          f"table ${rep['T4']['tableDollars']:.2f}, fresh ${rep['T4']['freshDollars']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
