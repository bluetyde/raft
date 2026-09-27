"""M2: transient-rod worth curves from the calibrated model (uniform burnup B246, m2-burnup-results.md) against the measured tables.

- core 242 model vs s242 (measured on core 242, 19 Oct 2020);
- core 246 model vs s246, which is headed **core 244** (8 June 2021; no open map of core 244), so that comparison is indicative only.

Model points: validation/m2_scurve_points.jsonl (core_model --json, 20,000 x 150 per point) plus the T = 0 / 900 points of core 242
in validation/m2_burnup_report.json. Tables: the database's s242.txt / s246.txt (downloaded, gitignored). Worth W(s) = rho(T = 0) -
rho(T = s); dollars use the model's own beta_eff at B246 for the model and 700 pcm/$ for the tables (m2-core.md).

Run from the repo root (any Python):  python -m validation.m2_rod_curves
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRACES = REPO_ROOT / "validation" / "data" / "jsi-pulses" / "traces"
POINTS = REPO_ROOT / "validation" / "m2_scurve_points.jsonl"
BURNUP_REPORT = REPO_ROOT / "validation" / "m2_burnup_report.json"
OUT = REPO_ROOT / "validation" / "m2_rod_curves_report.json"
TABLE_PCM_PER_DOLLAR = 700.0


def parse_table(path: Path) -> tuple[str, dict[int, float]]:
    """Rows of (step, worth pcm, pcm/step) triples, three per line; returns (header line, {step: worth})."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    worth: dict[int, float] = {}
    num = re.compile(r"^-?\d+(\.\d+)?$")
    for line in lines:
        toks = line.replace(",", ".").split()             # s242 uses decimal commas, s246 points
        if len(toks) < 3 or len(toks) % 3 or not all(num.match(t) for t in toks):
            continue
        for i in range(0, len(toks), 3):
            worth[int(float(toks[i]))] = float(toks[i + 1])
    if not worth:
        raise ValueError(f"no table rows in {path}")
    return lines[0].strip(), worth


def rho(k: float) -> float:
    return (k - 1.0) / k * 1e5


def rho_std(k: float, s: float) -> float:
    return s / k ** 2 * 1e5


def model_points() -> dict[str, dict[float, tuple[float, float]]]:
    """{core: {T steps: (rho pcm, std)}} at B246."""
    pts: dict[str, dict[float, tuple[float, float]]] = {"242": {}, "246": {}}
    rep = json.loads(BURNUP_REPORT.read_text(encoding="utf-8"))
    for p in rep["points"]:
        if p["core"] == "242":
            pts["242"][p["rods"]["T"]] = (rho(p["k"]), rho_std(p["k"], p["kStd"]))
    if POINTS.exists():
        for line in POINTS.read_text(encoding="utf-8").splitlines():
            p = json.loads(line)
            pts[p["core"]][p["rods"]["T"]] = (rho(p["k"]), rho_std(p["k"], p["kStd"]))
    return pts


def main() -> int:
    rep = json.loads(BURNUP_REPORT.read_text(encoding="utf-8"))
    beta = rep["T4"]["betaEffPcm"]
    out = {"B246": rep["B246"], "betaEffPcm": beta, "tablePcmPerDollar": TABLE_PCM_PER_DOLLAR, "cores": {}}
    for core, table in (("242", "s242.txt"), ("246", "s246.txt")):
        header, meas = parse_table(TRACES / table)
        pts = model_points()[core]
        if 0.0 not in pts:
            print(f"core {core}: no T = 0 point yet")
            continue
        r0, s0 = pts[0.0]
        rows = []
        for s in sorted(pts):
            if s == 0.0:
                continue
            r, sd = pts[s]
            w, wsd = r0 - r, math.hypot(s0, sd)
            m = meas.get(int(s))
            rows.append({"steps": s, "modelPcm": w, "modelStdPcm": wsd, "measuredPcm": m,
                         "modelDollars": w / beta, "measuredDollars": None if m is None else m / TABLE_PCM_PER_DOLLAR,
                         "ratioDollars": None if not m else (w / beta) / (m / TABLE_PCM_PER_DOLLAR)})
        out["cores"][core] = {"table": table, "tableHeader": header, "rows": rows}
        print(f"core {core} vs {table} ({header[:60]})")
        print("  steps  model pcm        table pcm   model $  table $  ratio($)")
        for r in rows:
            m, ratio = r["measuredPcm"], r["ratioDollars"]
            m_pcm = "" if m is None else f"{m:.1f}"
            m_usd = "" if m is None else f"{m / TABLE_PCM_PER_DOLLAR:.2f}"
            rat = "" if ratio is None else f"{ratio:.2f}"
            print(f"  {r['steps']:5.0f}  {r['modelPcm']:7.0f} +- {r['modelStdPcm']:3.0f}  {m_pcm:>9}   "
                  f"{r['modelDollars']:6.2f}  {m_usd:>7}  {rat:>7}")
    OUT.write_bytes((json.dumps(out, indent=1) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
