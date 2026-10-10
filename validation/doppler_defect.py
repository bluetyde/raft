"""Doppler defect: OpenMC with ENDF/B-VIII.0 against Mosteller's 16 pin-cell Doppler coefficients (LA-UR-07-0922, ENDF/B-VII.0 column).

Implements docs/validation/doppler-defect-protocol.md (thirteenth protocol, written before any run of it). Read it first: the quantities, the
metrics A-D, the bands and the decision process are fixed there, and nothing here may change after the results are seen (a change is a new
dated protocol).

  python -m validation.doppler_defect [--runs PATH] [--reference PATH] [--out PATH]

Run from the repo root. Standard library only; no OpenMC. The result rows are written by pipeline/openmc/doppler_run.py.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS = REPO_ROOT / "pipeline" / "openmc" / "results" / "doppler_defect.jsonl"
REFERENCE = REPO_ROOT / "validation" / "data" / "mosteller-doppler" / "reference.json"
OUT = REPO_ROOT / "validation" / "doppler_defect_report.json"
PROTOCOL = "docs/validation/doppler-defect-protocol.md"

PCM = 1e5
DELTA_T = 300.0                                  # K, HFP minus HZP
EXPECTED = {"particles": 20000, "batches": 600, "inactive": 100}
SEED = {"hzp": 1, "hfp": 2}
FUEL_K = {"hzp": 600, "hfp": 900}
STATES = ("hzp", "hfp")
SUBSETS = ("uo2", "reactor-mox", "weapons-mox")
LIBRARIES = ("endfb5", "endfb6", "endfb7")
WINDOWS = ((101, 350), (351, 600))               # 1-based batch numbers, inclusive
Z_GOOD, Z_PLAUSIBLE = 1.0, 2.0
WITHIN = 0.10                                    # the benchmark's own acceptance
CONVERGENCE_Z = 2.0
MIN_N_SUBSET = 3
SYSTEMATIC_SHARE = 0.75
ITEM1_MIN = 12


# ---------------------------------------------------------------- the runs

def load_runs(path: Path, reference: dict) -> dict:
    """{(case id, state): row}: every row must be one of the reference cases with exactly the protocol's settings, once. Missing rows are allowed (not computed)."""
    path = Path(path)
    ids = {c["id"] for c in reference["cases"]}
    runs: dict = {}
    for n, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not text.strip():
            continue
        where = f"{path.name} line {n}"
        r = json.loads(text)
        cid = r.get("case")
        if cid not in ids:
            raise ValueError(f"{where}: {cid!r} is not one of the protocol's reference cases")
        state = r.get("state")
        if state not in STATES:
            raise ValueError(f"{where}: case {cid} has state {state!r}, the protocol has hzp or hfp")
        for key, want in EXPECTED.items():
            if r.get(key) != want:
                raise ValueError(f"{where}: case {cid} {state} has {key} {r.get(key)!r}, the protocol has {want!r}")
        if r.get("seed") != SEED[state]:
            raise ValueError(f"{where}: case {cid} {state} has seed {r.get('seed')!r}, the protocol has {SEED[state]}")
        if r.get("fuelK") != FUEL_K[state]:
            raise ValueError(f"{where}: case {cid} {state} has fuelK {r.get('fuelK')!r}, the protocol has {FUEL_K[state]}")
        if (cid, state) in runs:
            raise ValueError(f"{where}: the case {cid} {state} appears twice")
        for key in ("k", "kStd", "kBatches"):
            if key not in r:
                raise ValueError(f"{where}: case {cid} {state} has no {key}")
        if not isinstance(r["kBatches"], list) or len(r["kBatches"]) != r["batches"]:
            raise ValueError(f"{where}: case {cid} {state} has {len(r['kBatches'])} batch values for {r['batches']} batches")
        runs[(cid, state)] = r
    return runs


def _mean_se(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(var / n)


def convergence(row: dict) -> dict:
    """Metric D: the mean k of batches 101-350 and 351-600 agree within 2 standard errors of their difference (batches taken as independent)."""
    (a0, a1), (b0, b1) = WINDOWS
    m1, s1 = _mean_se(row["kBatches"][a0 - 1:a1])
    m2, s2 = _mean_se(row["kBatches"][b0 - 1:b1])
    denom = math.hypot(s1, s2)
    z = abs(m1 - m2) / denom if denom > 0 else (0.0 if m1 == m2 else math.inf)
    return {"windows": [[a0, a1], [b0, b1]], "mean1": m1, "mean2": m2, "z": z, "converged": z <= CONVERGENCE_Z}


# ---------------------------------------------------------------- the metrics

def label(z: float) -> str:
    a = abs(z)
    return "good" if a <= Z_GOOD else "plausible" if a <= Z_PLAUSIBLE else "fails"


def _dc(hzp: dict, hfp: dict) -> tuple[float, float]:
    """Doppler coefficient (pcm/K) of a pair and its standard error from the two k errors (independent cases)."""
    kh, kf = hzp["k"], hfp["k"]
    sh, sf = hzp["kStd"], hfp["kStd"]
    drho = 1.0 / kh - 1.0 / kf
    sigma_drho = math.sqrt((sh / kh ** 2) ** 2 + (sf / kf ** 2) ** 2)
    return drho * PCM / DELTA_T, sigma_drho * PCM / DELTA_T


def analyse(runs: dict, reference: dict) -> dict:
    cases = OrderedDict((c["id"], c) for c in reference["cases"])
    conv = {key: convergence(r) for key, r in runs.items()}

    # D: convergence, every row
    d_rows = {f"{c}/{s}": conv[(c, s)] for (c, s) in sorted(runs)}
    unconverged = sorted(f"{c}/{s}" for (c, s), v in conv.items() if not v["converged"])
    missing = [f"{c}/{s}" for c in cases for s in STATES if (c, s) not in runs]
    d = {"rows": d_rows, "unconverged": unconverged, "missing": missing}

    # A: the Doppler coefficient, per case
    a = OrderedDict()
    for cid, case in cases.items():
        absent = [s for s in STATES if (cid, s) not in runs]
        bad = [s for s in STATES if (cid, s) in runs and not conv[(cid, s)]["converged"]]
        if absent or bad:
            reasons = ([f"missing row: {', '.join(absent)}"] if absent else []) + ([f"unconverged row: {', '.join(bad)}"] if bad else [])
            a[cid] = {"computed": False, "reason": "; ".join(reasons)}
            continue
        dc, sdc = _dc(runs[(cid, "hzp")], runs[(cid, "hfp")])
        ref = case["endfb7"]
        z = (dc - ref["dc"]) / math.hypot(ref["dcStd"], sdc)
        rel = (dc - ref["dc"]) / abs(ref["dc"])
        dcs = [case[lib]["dc"] for lib in LIBRARIES]
        a[cid] = {"computed": True, "subset": case["subset"], "content": case["content"], "dc": dc, "sigmaDc": sdc,
                  "refDc": ref["dc"], "refSigma": ref["dcStd"], "z": z, "label": label(z), "relative": rel,
                  "within10": abs(rel) <= WITHIN, "spread": max(dcs) - min(dcs)}

    # B: k_HZP offset, per case wherever the HZP row exists (a check of the transcription and the model, reported, not labelled)
    b = OrderedDict()
    for cid, case in cases.items():
        if (cid, "hzp") not in runs:
            b[cid] = {"computed": False, "reason": "missing row: hzp"}
            continue
        hz = runs[(cid, "hzp")]
        b[cid] = {"computed": True, "offsetPcm": (hz["k"] - case["endfb7"]["kHZP"]) * PCM, "sigmaPcm": hz["kStd"] * PCM,
                  "converged": conv[(cid, "hzp")]["converged"]}

    # C: families
    c = OrderedDict()
    for sub in SUBSETS:
        rows = [(cid, e) for cid, e in a.items() if e["computed"] and e["subset"] == sub]
        n = len(rows)
        if n < MIN_N_SUBSET:
            c[sub] = {"computed": False, "n": n, "reason": f"{n} computed cases, needs at least {MIN_N_SUBSET}",
                      "systematicDeficit": False, "systematicExcess": False}
            continue
        rels = [e["relative"] for _, e in rows]
        m_rel, se = _mean_se(rels)
        npos = sum(1 for x in rels if x > 0)
        nneg = sum(1 for x in rels if x < 0)
        c[sub] = {"computed": True, "n": n, "cases": [cid for cid, _ in rows],
                  "meanZ": sum(e["z"] for _, e in rows) / n, "meanRelative": m_rel, "standardError": se,
                  "countPositive": npos, "countNegative": nneg,
                  "systematicDeficit": bool(m_rel > 0 and abs(m_rel) > 2 * se and npos / n >= SYSTEMATIC_SHARE),
                  "systematicExcess": bool(m_rel < 0 and abs(m_rel) > 2 * se and nneg / n >= SYSTEMATIC_SHARE)}

    out = {"summary": {"computed": sum(1 for e in a.values() if e["computed"]),
                       "goodOrPlausible": sum(1 for e in a.values() if e["computed"] and e["label"] in ("good", "plausible"))},
           "A": {"cases": a}, "B": {"cases": b}, "C": c, "D": d}
    out["decision"] = decide(out)
    return out


def decide(m: dict) -> dict:
    items = []
    computed = [(cid, e) for cid, e in m["A"]["cases"].items() if e["computed"]]
    n_computed = len(computed)
    good = sum(1 for _, e in computed if e["label"] in ("good", "plausible"))
    biased = [s for s, e in m["C"].items() if e["systematicDeficit"] or e["systematicExcess"]]

    if good >= ITEM1_MIN and not biased:
        items.append(f"1. the transport tool chain reproduces the benchmark's fuel Doppler response at the pin-cell level ({good} of {n_computed} "
                     f"computed cases good or plausible, no subset bias); the fuel Doppler treatment is not a candidate cause of the BEAVRS coefficient error")
    for sub, e in m["C"].items():
        if e["systematicDeficit"]:
            items.append(f"2. systematic deficit in {sub}: mean relative difference {e['meanRelative'] * 100:+.1f} % (n={e['n']}); recorded, nothing refitted")
    for sub, e in m["C"].items():
        if e["systematicExcess"]:
            items.append(f"3. systematic excess in {sub}: mean relative difference {e['meanRelative'] * 100:+.1f} % (n={e['n']}); recorded, nothing refitted")
    if good < ITEM1_MIN and not biased:
        failing = [f"{cid} {e['relative'] * 100:+.1f} %" for cid, e in computed if e["label"] == "fails"]
        items.append(f"4. mixed outcome: {', '.join(failing) or 'no computed case labelled fails'}; no cause is claimed")
    if m["D"]["unconverged"] or m["D"]["missing"]:
        items.append(f"5. unconverged rows: {', '.join(m['D']['unconverged']) or 'none'}; missing rows: {', '.join(m['D']['missing']) or 'none'}; "
                     "the cases they belong to are not computed and enter no decision item")
    items.append("6. this changes what is known about the tool chain, not what any library claims")
    return {"items": items}


# ---------------------------------------------------------------- output

def print_summary(m: dict) -> None:
    print("A: Doppler coefficient (pcm/K), model vs ENDF/B-VII.0")
    for cid, e in m["A"]["cases"].items():
        if e["computed"]:
            print(f"   {cid}: {e['dc']:+.3f} +- {e['sigmaDc']:.3f} vs {e['refDc']:+.2f} +- {e['refSigma']:.2f}  z {e['z']:+.2f} ({e['label']})  "
                  f"rel {e['relative'] * 100:+.1f} %  within 10 %: {e['within10']}  spread {e['spread']:.2f}")
        else:
            print(f"   {cid}: not computed ({e['reason']})")
    print("B: k_HZP offset (pcm) vs ENDF/B-VII.0")
    for cid, e in m["B"]["cases"].items():
        print(f"   {cid}: " + (f"{e['offsetPcm']:+.0f} +- {e['sigmaPcm']:.0f}" if e["computed"] else f"not computed ({e['reason']})"))
    print("C: families")
    for sub, e in m["C"].items():
        if e["computed"]:
            print(f"   {sub}: n {e['n']}, mean z {e['meanZ']:+.2f}, mean rel {e['meanRelative'] * 100:+.2f} % +- {e['standardError'] * 100:.2f} %, "
                  f"positive {e['countPositive']}, negative {e['countNegative']}, deficit {e['systematicDeficit']}, excess {e['systematicExcess']}")
        else:
            print(f"   {sub}: not computed ({e['reason']})")
    print(f"D: unconverged {m['D']['unconverged']}, missing {m['D']['missing']}")
    print(f"summary: computed {m['summary']['computed']}, good or plausible {m['summary']['goodOrPlausible']}")
    for item in m["decision"]["items"]:
        print("  decision:", item)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", type=Path, default=RUNS)
    ap.add_argument("--reference", type=Path, default=REFERENCE)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    report = {"protocol": PROTOCOL, **analyse(load_runs(args.runs, reference), reference)}
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
