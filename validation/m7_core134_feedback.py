"""M7: why is the core 134 library's fuel temperature feedback weak? Nine new OpenMC runs of core 134, analysed.

Implements docs/validation/m7-core134-feedback-protocol.md exactly (seventh protocol, written before any run of it). Read it first: the runs, the
metrics D1-D5, the bands and the decision process are fixed there, and nothing here may change after results are seen (a change is a new dated
protocol).

Input: pipeline/openmc/results/core134_feedback.jsonl (one line per run of `python -m pipeline.openmc.core_model`, written by the nine commands of
the protocol), the library libraries/triga-jsi-134-openmc and Table IX (validation/data/jsi-core134/power_steps.json).

Run from the repo root:  python -m validation.m7_core134_feedback [--out PATH]
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
from types import SimpleNamespace

from physics_ref.library import Library, Table
from validation import m7_fuel_coefficient as fc
from validation import m7_power_ascension as base

REPO_ROOT = base.REPO_ROOT
RUNS = REPO_ROOT / "pipeline" / "openmc" / "results" / "core134_feedback.jsonl"
LIBRARY = REPO_ROOT / "libraries" / "triga-jsi-134-openmc"
OUT = REPO_ROOT / "validation" / "m7_core134_feedback_report.json"

PCM = base.PCM
TEMPS = (294.0, 330.0, 372.0, 400.0)
BEYOND_K = (500.0, 600.0, 800.0)                 # the library's own knots beyond the runs, for the what-if tables
D1_SIGMAS = 2.0
D2_BANDS = (0.85, 1.15)
D3_BANDS = (0.9, 1.1)


# ---------------------------------------------------------------- the runs

EXPECTED = {"core": "134", "rods": {"T": 0.0, "K": 200.0, "V": 200.0, "R": 727.3}, "particles": 100000, "batches": 150, "inactive": 50}
ALLOWED_OVERRIDES = {"tfuel", "fuel1994"}


def load_runs(path: Path) -> dict:
    """{(composition, tfuel): {rho, sigma, k, kStd, particles}} with composition "A" (default) or "B" (--fuel1994); A0 is (A, None).
    Every line must be a run of the protocol's configuration (core 134, the reference rods, 100000 particles x 150 batches, 50 inactive, only the
    tfuel and fuel1994 overrides) and no case may appear twice: anything else is refused, not silently used."""
    runs = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        r = json.loads(line)
        for key, want in EXPECTED.items():
            if r.get(key) != want:
                raise ValueError(f"{path.name} line {n}: {key} is {r.get(key)!r}, the protocol's runs have {want!r}")
        ov = r.get("overrides", {})
        if set(ov) - ALLOWED_OVERRIDES or r.get("prompt"):
            raise ValueError(f"{path.name} line {n}: unexpected overrides {sorted(ov)} (allowed: {sorted(ALLOWED_OVERRIDES)})")
        comp = "B" if ov.get("fuel1994") else "A"
        t = ov.get("tfuel")
        if (comp, t) in runs:
            raise ValueError(f"{path.name} line {n}: the case {comp}{'0' if t is None else int(t)} appears twice")
        k, sd = r["k"], r["kStd"]
        runs[(comp, t)] = {"rho": (k - 1.0) / k * PCM, "sigma": sd / k**2 * PCM, "k": k, "kStd": sd, "particles": r["particles"]}
    return runs


def diff(a: dict, b: dict) -> tuple[float, float]:
    """a - b in pcm and its standard error."""
    return a["rho"] - b["rho"], math.hypot(a["sigma"], b["sigma"])


def slope(runs: dict, comp: str, t: float) -> tuple[float, float]:
    d, s = diff(runs[(comp, t)], runs[(comp, 294.0)])
    return d / (t - 294.0), s / (t - 294.0)


def ratio(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    r = a[0] / b[0]
    return r, abs(r) * math.hypot(a[1] / a[0], b[1] / b[0])


def label_band(r: float, bands: tuple[float, float], below: str, above: str, middle: str) -> str:
    return below if r < bands[0] else above if r > bands[1] else middle


# ---------------------------------------------------------------- what-if tables

def whatif_library(lib, runs: dict, comp: str):
    """A library-like object whose fuel table has the knots 294, 330, 372, 400 K from the runs (loss relative to 294 K) and the library's own beyond."""
    xs = list(TEMPS) + list(BEYOND_K)
    ys = [0.0] + [(runs[(comp, t)]["rho"] - runs[(comp, 294.0)]["rho"]) / PCM for t in TEMPS[1:]] + [lib.fuel_temp(t) for t in BEYOND_K]
    return SimpleNamespace(fuel_temp=Table(xs, ys), cool_temp=lib.cool_temp)


def whatif_labels(lib_like, data: dict) -> dict:
    cases = []
    for (gkey, col), profile in itertools.product((("gammaB", 3), ("gammaA", 2)), ("linear", "none", "cumulative")):
        a = fc.feedback_cases(lib_like, data, gkey, col, profile)
        cases.append({"gamma": gkey, "profile": profile, "A": a["A"]})
    worst = [c["A"]["worst"] for c in cases]
    return {"primary": cases[0]["A"], "worst": base.worst(worst), "best": base.best(worst), "cases": cases}


# ---------------------------------------------------------------- the metrics

def analyse(lib, runs: dict, data: dict) -> dict:
    need = [("A", None)] + [(c, t) for c in "AB" for t in TEMPS]
    missing = [k for k in need if k not in runs]
    if missing:
        raise ValueError(f"missing runs: {missing}")
    d_method, s_method = diff(runs[("A", 294.0)], runs[("A", None)])
    d1 = {"deltaPcm": d_method, "sigmaPcm": s_method, "label": "no artefact" if abs(d_method) <= D1_SIGMAS * s_method else "artefact"}

    sa = {t: slope(runs, "A", t) for t in TEMPS[1:]}
    sb = {t: slope(runs, "B", t) for t in TEMPS[1:]}
    r372, r330 = ratio(sa[372.0], sa[400.0]), ratio(sa[330.0], sa[400.0])
    d2 = {"slopesA": sa, "ratio372to400": r372, "ratio330to400": r330,
          "label": label_band(r372[0], D2_BANDS, "convex", "concave", "linear")}
    c372, c400 = ratio(sb[372.0], sa[372.0]), ratio(sb[400.0], sa[400.0])
    d3 = {"slopesB": sb, "ratio372": c372, "ratio400": c400, "label": label_band(c372[0], D3_BANDS, "weaker", "stronger", "no effect")}

    d4 = {comp: whatif_labels(whatif_library(lib, runs, comp), data) for comp in "AB"}
    knot_diff, knot_sigma = diff(runs[("A", 400.0)], runs[("A", 294.0)])
    d5 = {"runs": {f"{c}{'0' if t is None else int(t)}": {"k": r["k"], "kStd": r["kStd"], "rhoPcm": r["rho"], "sigmaPcm": r["sigma"], "particles": r["particles"]} for (c, t), r in sorted(runs.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0))},
          "libraryKnot400Pcm": lib.fuel_temp(400.0) * PCM, "rerunKnot400Pcm": knot_diff, "rerunSigmaPcm": knot_sigma}
    return {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5, "decision": decide(d1, d2, d3, d4)}


def decide(d1: dict, d2: dict, d3: dict, d4: dict) -> dict:
    """The protocol's decision process; every applicable item is listed."""
    ok = ("good", "plausible")
    a_ok, b_ok = d4["A"]["primary"]["worst"] in ok, d4["B"]["primary"]["worst"] in ok
    items = []
    if d1["label"] == "artefact":
        items.append(f"1. method artefact of {d1['deltaPcm']:.0f} pcm in the reference: the table carries that offset; a corrected table needs its own protocol")
    if d2["label"] != "linear":
        items.append(f"2. first interval is {d2['label']}: a knot between 294 and 400 K is needed (own protocol)")
    if d3["label"] == "stronger" and b_ok and not a_ok:
        items.append("3. fuel hydrogen is a lever strong enough to explain the shortfall; not adopted (not established by these data)")
    if a_ok:
        items.append("4. with the new knots the default composition reproduces the measurement: resolution or statistics")
    if d1["label"] == "no artefact" and d2["label"] == "linear" and d3["label"] == "no effect" and not a_ok and not b_ok:
        items.append("5. none of the three explains it: the temperature conversion, the water warming or OpenMC's temperature treatment remain")
    if not items:
        items.append("none of the protocol's cases applies as written; read the metrics")
    return {"items": items, "libraryChanged": False}


# ---------------------------------------------------------------- the run

def run(lib, runs: dict, data: dict | None = None) -> dict:
    data = data or fc.load_steps()
    out = analyse(lib, runs, data)
    return {"protocol": "docs/validation/m7-core134-feedback-protocol.md", **out}


def print_summary(r: dict) -> None:
    print("protocol:", r["protocol"])
    for name, v in r["D5"]["runs"].items():
        print(f"  {name}: k {v['k']:.5f} +- {v['kStd']:.5f}  rho {v['rhoPcm']:.0f} +- {v['sigmaPcm']:.0f} pcm  ({v['particles']} particles)")
    d1 = r["D1"]
    print(f"  D1: method offset {d1['deltaPcm']:.0f} +- {d1['sigmaPcm']:.0f} pcm -> {d1['label']}")
    d2 = r["D2"]
    print("  D2: slopes A (pcm/K):", {int(t): (round(s[0], 2), round(s[1], 2)) for t, s in d2["slopesA"].items()}, f"ratio 372/400 {d2['ratio372to400'][0]:.2f} +- {d2['ratio372to400'][1]:.2f}  330/400 {d2['ratio330to400'][0]:.2f} -> {d2['label']}")
    d3 = r["D3"]
    print("  D3: slopes B (pcm/K):", {int(t): (round(s[0], 2), round(s[1], 2)) for t, s in d3["slopesB"].items()}, f"B/A at 372 {d3['ratio372'][0]:.2f} +- {d3['ratio372'][1]:.2f}, at 400 {d3['ratio400'][0]:.2f} -> {d3['label']}")
    for comp in "AB":
        d = r["D4"][comp]
        steps = "  ".join(f"{s['step']}:{s['modelPcm']:.0f}/{s['measuredPcm']:.0f}[{s['label'][0]}]" for s in d["primary"]["perStep"])
        print(f"  D4 {comp}: primary {d['primary']['worst']} worst {d['worst']} best {d['best']}   model/measured by step: {steps}")
    d5 = r["D5"]
    print(f"  D5: library knot at 400 K {d5['libraryKnot400Pcm']:.0f} pcm; rerun {d5['rerunKnot400Pcm']:.0f} +- {d5['rerunSigmaPcm']:.0f}")
    for item in r["decision"]["items"]:
        print("  decision:", item)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", type=Path, default=RUNS)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    report = run(Library(LIBRARY), load_runs(args.runs))
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
