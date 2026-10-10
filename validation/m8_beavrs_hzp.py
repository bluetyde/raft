"""M8: the BEAVRS full-core OpenMC model against the cycle 1 hot zero power physics tests.

Implements docs/validation/m8-beavrs-hzp-protocol.md exactly (eleventh protocol, written before any run of it). Read it first: the cases, the
quantities, the metrics A-E, the bands and the decision process are fixed there, and nothing here may change after results are seen (a change is
a new dated protocol).

  python -m validation.m8_beavrs_hzp --plan      prints the 20 cases (what pipeline/openmc/beavrs_run.py runs)
  python -m validation.m8_beavrs_hzp             analyses pipeline/openmc/results/beavrs_hzp.jsonl

Run from the repo root.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_hzp.jsonl"
OUT = REPO_ROOT / "validation" / "m8_beavrs_hzp_report.json"

PCM = 1e5
T_HZP = 566.483                      # K, 560 F
T_STEP = 30.0                        # K, the ITC cases are at T_HZP -/+ this
DELTA_F = 2 * T_STEP * 1.8           # 108 F between the two ITC temperatures
BOOT = 100.0                         # ppm, half-width of the boron worth pairs
BANKS = ["D", "C", "B", "A", "SE", "SD", "SC"]           # insertion order; state S_n has the first n of them in
STANDARD = {"particles": 60000, "batches": 300, "inactive": 100}
LONG = {"particles": 100000, "batches": 800, "inactive": 100}
# convergence windows (1-based batch numbers, inclusive), per settings
WINDOWS = {300: ((101, 200), (201, 300)), 800: ((101, 400), (401, 800))}
Z_GOOD, Z_PLAUSIBLE = 1.0, 2.0
CB_CRITERION_PPM = 50.0              # the licensing criterion cited in the UQ report

# measured, cycle 1 HZP (BEAVRS specification rev 3.0.2 Tables 21-22; UQ report Tables 1, 4, 6)
CB = OrderedDict([(0, (975.0, 22.0)), (1, (902.0, 22.0)), (2, (810.0, 22.0)), (4, (686.0, 22.0)), (7, (508.0, 22.0))])
WORTH = OrderedDict([("D", (788.0, 29.0)), ("C", (1203.0, 32.0)), ("B", (1171.0, 31.0)), ("A", (548.0, 26.0)),
                     ("SE", (461.0, 25.0)), ("SD", (772.0, 28.0)), ("SC", (1099.0, 31.0))])
ITC = OrderedDict([(0, (-1.75, 0.54)), (2, (-8.01, 0.54))])      # pcm/F, by state


def total_worth() -> tuple[float, float]:
    return sum(v for v, _ in WORTH.values()), math.sqrt(sum(s * s for _, s in WORTH.values()))


# ---------------------------------------------------------------- the cases

def cases() -> "OrderedDict[str, dict]":
    """case id -> {series, state (banks in = the first `state` of BANKS), boron, temperature, particles, batches, inactive}."""
    out: "OrderedDict[str, dict]" = OrderedDict()

    def add(cid, series, state, boron, temp=T_HZP, settings=STANDARD):
        out[cid] = {"series": series, "state": state, "boron": boron, "temperature": temp, **settings}

    for n in range(8):
        add(f"W{n}", "W", n, 975.0)
    for n in (1, 2, 4, 7):
        add(f"B{n}", "B", n, CB[n][0])
    add("K0a", "K", 0, 975.0 - BOOT)
    add("K0b", "K", 0, 975.0 + BOOT)
    add("K7a", "K", 7, CB[7][0] - BOOT)
    add("K7b", "K", 7, CB[7][0] + BOOT)
    for n in (0, 2):
        add(f"T{n}m", "T", n, CB[n][0], T_HZP - T_STEP, LONG)
        add(f"T{n}p", "T", n, CB[n][0], T_HZP + T_STEP, LONG)
    return out


def banks_in(state: int) -> list[str]:
    return BANKS[:state]


# ---------------------------------------------------------------- the runs

def load_runs(path: Path) -> dict:
    """{case id: line}: every line must be one of the protocol's cases with exactly its settings, once. Missing cases are allowed (not computed)."""
    plan = cases()
    runs: dict = {}
    for n, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not text.strip():
            continue
        r = json.loads(text)
        cid = r.get("case")
        if cid not in plan:
            raise ValueError(f"{path.name} line {n}: {cid!r} is not one of the protocol's cases")
        for key, want in plan[cid].items():
            if r.get(key) != want:
                raise ValueError(f"{path.name} line {n}: case {cid} has {key} {r.get(key)!r}, the protocol has {want!r}")
        if cid in runs:
            raise ValueError(f"{path.name} line {n}: the case {cid} appears twice")
        for key in ("k", "kStd", "kBatches"):
            if key not in r:
                raise ValueError(f"{path.name} line {n}: case {cid} has no {key}")
        if len(r["kBatches"]) != r["batches"]:
            raise ValueError(f"{path.name} line {n}: case {cid} has {len(r['kBatches'])} batch values for {r['batches']} batches")
        runs[cid] = r
    return runs


def rho(r: dict) -> tuple[float, float]:
    k, sd = r["k"], r["kStd"]
    return (k - 1.0) / k * PCM, sd / k ** 2 * PCM


def _mean_se(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(var / n)


def convergence(r: dict) -> dict:
    """The protocol's drift check: the mean k of the two windows agrees within 2 standard errors of their difference (batch values taken as independent)."""
    (a0, a1), (b0, b1) = WINDOWS[r["batches"]]
    m1, s1 = _mean_se(r["kBatches"][a0 - 1:a1])
    m2, s2 = _mean_se(r["kBatches"][b0 - 1:b1])
    z = abs(m1 - m2) / math.hypot(s1, s2)
    return {"windows": [[a0, a1], [b0, b1]], "z": z, "converged": z <= 2.0}


# ---------------------------------------------------------------- the metrics

def label(z: float) -> str:
    a = abs(z)
    return "good" if a <= Z_GOOD else "plausible" if a <= Z_PLAUSIBLE else "fails"


def _z(diff: float, sigma_meas: float, sigma_model: float) -> float:
    return diff / math.hypot(sigma_meas, sigma_model)


def analyse(runs: dict) -> dict:
    conv = {cid: convergence(r) for cid, r in runs.items()}
    usable = {cid: r for cid, r in runs.items() if conv[cid]["converged"]}
    rr = {cid: rho(r) for cid, r in usable.items()}

    def have(*ids):
        return all(i in rr for i in ids)

    def nc(why):
        return {"computed": False, "reason": why}

    # boron worth, pcm per ppm
    bw = {}
    for name, (lo, hi) in (("S0", ("K0a", "K0b")), ("S7", ("K7a", "K7b"))):
        if have(lo, hi):
            b = -(rr[hi][0] - rr[lo][0]) / (2 * BOOT)
            bw[name] = {"computed": True, "bw": b, "sigma": math.hypot(rr[lo][1], rr[hi][1]) / (2 * BOOT)}
        else:
            bw[name] = nc(f"needs {lo} and {hi} converged")
    d = {"S0": bw["S0"], "S7": bw["S7"]}
    if bw["S0"]["computed"] and bw["S7"]["computed"]:
        rel = (bw["S7"]["bw"] - bw["S0"]["bw"]) / bw["S0"]["bw"]
        d["relativeDifference"] = rel
        d["sensitive"] = abs(rel) > 0.05

    # A: critical boron
    case_of = {0: "W0", 1: "B1", 2: "B2", 4: "B4", 7: "B7"}
    a = OrderedDict()
    for s, (cm, sm) in CB.items():
        cid = case_of[s]
        if not (have(cid) and bw["S0"]["computed"]):
            a[s] = nc(f"needs {cid} and the boron worth at S0")
            continue
        r_, sr = rr[cid]
        b, sb = bw["S0"]["bw"], bw["S0"]["sigma"]
        err = r_ / b
        sig = math.sqrt((sr / b) ** 2 + (r_ * sb / b ** 2) ** 2)
        z = _z(err, sm, sig)
        entry = {"computed": True, "case": cid, "measuredPpm": cm, "errorPpm": err, "sigmaModelPpm": sig, "z": z, "label": label(z),
                 "within50ppm": abs(err) <= CB_CRITERION_PPM, "rhoPcm": r_}
        if bw["S7"]["computed"]:
            entry["errorPpmWithBwS7"] = r_ / bw["S7"]["bw"]
            if s in (4, 7):
                entry["sensitiveToConversion"] = bool(d.get("sensitive"))
        a[s] = entry
    errs = [v["errorPpm"] for v in a.values() if v["computed"]]
    agg = {"count": len(errs)}
    if len(errs) >= 4:
        m, se = _mean_se(errs)
        same = max(sum(e > 0 for e in errs), sum(e < 0 for e in errs))
        agg.update({"computed": True, "meanErrorPpm": m, "standardError": se, "sameSign": same,
                    "systematic": abs(m) > 2 * se and same >= 4,
                    "meanErrorPcm": m * bw["S0"]["bw"]})
    else:
        agg.update(nc("fewer than four of the five states computed"))

    # B: bank worths
    b_ = OrderedDict()
    for i, bank in enumerate(BANKS):
        lo, hi = f"W{i}", f"W{i + 1}"
        wm, sm = WORTH[bank]
        if not have(lo, hi):
            b_[bank] = nc(f"needs {lo} and {hi}")
            continue
        w = rr[lo][0] - rr[hi][0]
        sig = math.hypot(rr[lo][1], rr[hi][1])
        z = _z(w - wm, sm, sig)
        b_[bank] = {"computed": True, "measuredPcm": wm, "worthPcm": w, "sigmaModel": sig, "difference": w - wm, "relative": (w - wm) / wm, "z": z, "label": label(z)}
    if have("W0", "W7"):
        tm, ts = total_worth()
        w = rr["W0"][0] - rr["W7"][0]
        sig = math.hypot(rr["W0"][1], rr["W7"][1])
        z = _z(w - tm, ts, sig)
        total = {"computed": True, "measuredPcm": tm, "sigmaMeasured": ts, "worthPcm": w, "sigmaModel": sig, "difference": w - tm, "relative": (w - tm) / tm, "z": z, "label": label(z)}
    else:
        total = nc("needs W0 and W7")

    # C: ITC
    c = OrderedDict()
    for s, (im, sm) in ITC.items():
        lo, hi = f"T{s}m", f"T{s}p"
        if not have(lo, hi):
            c[s] = nc(f"needs {lo} and {hi}")
            continue
        v = (rr[hi][0] - rr[lo][0]) / DELTA_F
        sig = math.hypot(rr[lo][1], rr[hi][1]) / DELTA_F
        z = _z(v - im, sm, sig)
        c[s] = {"computed": True, "measuredPcmPerF": im, "itcPcmPerF": v, "sigmaModel": sig, "difference": v - im, "z": z, "label": label(z)}

    unconverged = sorted(cid for cid in runs if not conv[cid]["converged"])
    missing = sorted(set(cases()) - set(runs))
    out = {"A": {"states": a, "aggregate": agg}, "B": {"banks": b_, "total": total}, "C": c, "D": d,
           "E": {"convergence": conv, "unconverged": unconverged, "missing": missing}}
    out["decision"] = decide(out)
    return out


def _labels(entries) -> list[str]:
    return [e["label"] for e in entries if e.get("computed")]


def decide(m: dict) -> dict:
    items = []
    a_labels = _labels(m["A"]["states"].values())
    agg = m["A"]["aggregate"]
    ok = sum(1 for lab in a_labels if lab in ("good", "plausible"))
    if agg.get("computed") and agg["systematic"]:
        items.append(f"2. a systematic offset of the critical boron ({agg['meanErrorPpm']:+.1f} ppm, {agg['meanErrorPcm']:+.0f} pcm at the model's boron worth): recorded as a calibration offset of the library, not removed from the transport results")
    elif agg.get("computed") and ok >= 4:
        items.append("1. the transport model reproduces the critical boron (no systematic offset): the library of step 3 is built without a calibration offset")
    else:
        items.append("1/2. the critical boron cannot be decided (too few states computed, or fewer than four good or plausible without a systematic offset); read the metrics")
    failed = [b for b, e in m["B"]["banks"].items() if e.get("computed") and e["label"] == "fails"]
    if failed:
        items.append(f"3. bank worths that fail: {', '.join(failed)}; the library inherits them with a validity note, nothing is refitted")
    if m["B"]["total"].get("computed") and m["B"]["total"]["label"] == "fails":
        items.append("3. the total worth fails: the bank worth model is not validated for the shutdown banks")
    if any(e.get("computed") and e["label"] == "fails" for e in m["C"].values()):
        items.append("4. the isothermal temperature coefficient fails: the library's temperature feedback is marked not validated at HZP")
    nc_ = []
    for name, entries in (("A", m["A"]["states"]), ("B", m["B"]["banks"]), ("C", m["C"])):
        nc_ += [f"{name}:{k}" for k, e in entries.items() if not e.get("computed")]
    if m["B"]["total"].get("computed") is False:
        nc_.append("B:total")
    if m["E"]["unconverged"] or m["E"]["missing"] or nc_:
        items.append(f"5. cases unconverged: {m['E']['unconverged'] or 'none'}; cases missing: {m['E']['missing'] or 'none'}; metrics not computed: {nc_ or 'none'} (they enter no decision item)")
    items.append("6. the library status stays experimental and step 2 (the format fit check) goes ahead; this outcome changes what the library may claim")
    return {"items": items, "libraryChanged": False}


# ---------------------------------------------------------------- output

def print_summary(m: dict) -> None:
    print("A: critical boron (error = model needs more boron than measured when positive)")
    for s, e in m["A"]["states"].items():
        print(f"   S{s}: " + (f"{e['errorPpm']:+.1f} +- {e['sigmaModelPpm']:.1f} ppm vs {e['measuredPpm']:.0f}  z {e['z']:+.2f} ({e['label']})  within 50 ppm: {e['within50ppm']}" if e["computed"] else e["reason"]))
    g = m["A"]["aggregate"]
    print("   aggregate: " + (f"mean {g['meanErrorPpm']:+.1f} ppm, SE {g['standardError']:.1f}, same sign {g['sameSign']}/{g['count']}, systematic {g['systematic']}" if g.get("computed") else g["reason"]))
    print("B: bank worths")
    for b, e in m["B"]["banks"].items():
        print(f"   {b}: " + (f"{e['worthPcm']:.0f} vs {e['measuredPcm']:.0f} pcm ({e['relative']:+.1%}) z {e['z']:+.2f} ({e['label']})" if e["computed"] else e["reason"]))
    t = m["B"]["total"]
    print("   total: " + (f"{t['worthPcm']:.0f} vs {t['measuredPcm']:.0f} pcm ({t['relative']:+.1%}) z {t['z']:+.2f} ({t['label']})" if t["computed"] else t["reason"]))
    print("C: ITC")
    for s, e in m["C"].items():
        print(f"   S{s}: " + (f"{e['itcPcmPerF']:+.2f} vs {e['measuredPcmPerF']:+.2f} pcm/F z {e['z']:+.2f} ({e['label']})" if e["computed"] else e["reason"]))
    d = m["D"]
    print("D: boron worth " + ", ".join(f"{k} " + (f"{v['bw']:.2f} +- {v['sigma']:.2f} pcm/ppm" if v["computed"] else v["reason"]) for k, v in (("S0", d["S0"]), ("S7", d["S7"]))) + (f"; difference {d['relativeDifference']:+.1%}" if "relativeDifference" in d else ""))
    print(f"E: unconverged {m['E']['unconverged']}, missing {m['E']['missing']}")
    for item in m["decision"]["items"]:
        print("  decision:", item)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--runs", type=Path, default=RUNS)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    if args.plan:
        for cid, c in cases().items():
            print(cid, json.dumps({**c, "banksIn": banks_in(c["state"])}))
        return 0
    report = {"protocol": "docs/validation/m8-beavrs-hzp-protocol.md", **analyse(load_runs(args.runs))}
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
