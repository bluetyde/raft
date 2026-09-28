"""M2 regression: run 3 Part B (docs/validation/m1-run3-protocol.md) repeated with the M2 OpenMC libraries.

Same pulses, same criteria (B1-B4), same code (validation.m1_run3.part_b); only the library changes from triga-jsi-<core>
(M1: cited kinetics and fuel table, assumed rod worths) to triga-jsi-<core>-openmc (M2: OpenMC transport at the calibrated
burnup). Each library also re-derives the trace-inferred $ axis, since that inversion uses the library's own engine curve (Λ).
Not a new protocol: a regression check that M2 didn't break the M1 result, reported next to it.

Usage (from the repo root; needs the trace windows):  python -m validation.m2_run3b_regression
"""
from __future__ import annotations

import json
from pathlib import Path

from validation import m1_run3

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "validation" / "m2_run3b_regression_report.json"


def main() -> int:
    m1 = json.loads((REPO_ROOT / "validation" / "m1_run3_report_counts_corrected.json").read_text(encoding="utf-8"))
    report = {"basis": "validation.m1_run3.part_b with the M2 libraries", "cores": {}}
    for core in ("242", "246"):
        m1_run3.LIBS[core] = REPO_ROOT / "libraries" / f"triga-jsi-{core}-openmc"
        b = m1_run3.part_b(core)
        report["cores"][core] = {"m2": b, "m1": {k: m1["B"][core].get(k) for k in ("used", "metrics", "B1", "B2", "B3", "B4")}}
        m, o = b.get("metrics", {}), m1["B"][core].get("metrics", {})
        verdict = {k: b.get(k, {}).get("pass") for k in ("B1", "B2", "B3", "B4")}
        print(f"core {core}: used {b['used']} (M1 {m1['B'][core]['used']}); "
              f"rms {m.get('rms', float('nan')):.3f} (M1 {o.get('rms', float('nan')):.3f}), "
              f"bias {m.get('bias', float('nan')):+.3f} (M1 {o.get('bias', float('nan')):+.3f}), "
              f"slopes exp/sim {m.get('slope_exp', float('nan')):.2f}/{m.get('slope_sim', float('nan')):.2f} "
              f"(M1 {o.get('slope_exp', float('nan')):.2f}/{o.get('slope_sim', float('nan')):.2f}); {verdict}")
    OUT.write_bytes((json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
