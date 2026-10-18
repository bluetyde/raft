"""M8: the BEAVRS library as it is, against 7 new held-out transport cases at the states of a narrower bank-withdrawal lesson (D and C in, 900 ppm, C withdrawn).

Implements docs/validation/m8-near-critical-protocol.md exactly (sixteenth protocol, written before any code and before any run of the new cases). Read it
first: the library pin, the 7 cases, the labels, the critical-position rule and the decision process are fixed there, and nothing here may change after
the results are seen (a change is a new dated protocol).

  python -m validation.m8_near_critical

Run from the repo root. Needs the Python reference engine; no OpenMC. Reads libraries/pwr-beavrs-hzp-openmc and pipeline/openmc/results/beavrs_near.jsonl.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from pipeline.library import export_beavrs as xb
from pipeline.openmc.beavrs_cases import near_cases
from validation import m8_beavrs_hzp as t11
from validation import m8_beavrs_library as lb
from validation import m8_rod_shadowing as rs

REPO_ROOT = Path(__file__).resolve().parents[1]
NEAR = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_near.jsonl"
OUT = REPO_ROOT / "validation" / "m8_near_critical_report.json"

PCM = 1e5
STEPS = 228
BORON = 900.0
REACTIVITY_DIGEST = "91b18998173ddd54a16ac25ef2108a00938394ec6bb32454bc9d58471ed343bd"
BEYOND = 300.0                  # pcm: any case further off than this defeats the lesson
MIN_GOOD_OR_PLAUSIBLE = 6       # of the 7
CRIT_GOOD, CRIT_PLAUSIBLE = 15.0, 30.0       # steps


class PinError(RuntimeError):
    pass


def reactivity_digest(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest["reactivity"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check_pin(model: rs.ShadowModel, digest: str | None = REACTIVITY_DIGEST) -> None:
    got = reactivity_digest(model.m)
    if digest is not None and got != digest:
        raise PinError(f"the library's reactivity block has the digest {got}, the protocol fixes {digest}")


def load_near(path: Path) -> list[dict]:
    rows = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    for r in rows:
        if not isinstance(r.get("kBatches"), list) or len(r["kBatches"]) != r.get("batches"):
            raise ValueError(f"case {r.get('case')}: kBatches missing or not one value per batch")
    xb.check_path(rows, near_cases(), "near", allow_subset=True)
    return rows


def rods_of(steps: dict) -> dict[str, float]:
    return {b.lower(): s / STEPS for b, s in steps.items()}


def library_critical(model: rs.ShadowModel, boron: float = BORON) -> float | None:
    """Steps of C at which the library's reactivity (D in, other banks at reference) crosses zero, by bisection; None if it does not cross in 0 to 228."""
    base = near_cases()["N-C-0"]["steps"]

    def f(c: float) -> float:
        return model.rho(rods_of({**base, "C": c}), boron)
    lo, hi = 0.0, float(STEPS)
    if f(lo) >= 0.0 or f(hi) <= 0.0:
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if f(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def transport_critical(computed: dict[str, dict]) -> dict | None:
    """Zero of the straight line through the two neighbouring computed transport cases (in C) that bracket zero; None if no pair brackets it."""
    pts = sorted((e["C"], e["transportPcm"], e["transportSigmaPcm"]) for e in computed.values())
    for (c0, r0, s0), (c1, r1, s1) in zip(pts, pts[1:]):
        if r0 < 0.0 <= r1:
            c = c0 + (0.0 - r0) / (r1 - r0) * (c1 - c0)
            slope = (r1 - r0) / (c1 - c0)
            return {"steps": c, "between": [c0, c1], "sigmaSteps": max(s0, s1) / slope}
    return None


def part_p(model: rs.ShadowModel, rows: list[dict]) -> dict:
    by = {r["case"]: r for r in rows}
    out = {}
    for cid, plan in near_cases().items():
        if cid not in by:
            out[cid] = {"computed": False, "reason": "missing: not in the file"}
            continue
        r = by[cid]
        conv = t11.convergence(r)
        if not conv["converged"]:
            out[cid] = {"computed": False, "reason": f"unconverged (drift z {conv['z']:.2f})"}
            continue
        rho = model.rho(rods_of(r["steps"]), r["boron"])
        tr, sig = rs.rho_of(r)
        diff = rho - tr
        label, limit = rs.label_of(diff, sig)
        out[cid] = {"computed": True, "C": r["steps"]["C"], "libraryPcm": rho, "transportPcm": tr, "transportSigmaPcm": sig, "differencePcm": diff,
                    "limitPcm": limit, "label": label, "driftZ": conv["z"]}
    return out


def crit_label(d: float) -> str:
    return "good" if abs(d) <= CRIT_GOOD else "plausible" if abs(d) <= CRIT_PLAUSIBLE else "fails"


def critical_item(model: rs.ShadowModel, p: dict, boron: float = BORON) -> dict:
    lib_c = library_critical(model, boron)
    tr = transport_critical({c: e for c, e in p.items() if e["computed"]})
    if lib_c is None or tr is None:
        return {"computed": False, "libraryC": lib_c, "reason": "no bracketing pair of transport cases" if tr is None else "the library does not cross zero"}
    d = lib_c - tr["steps"]
    label = crit_label(d)
    return {"computed": True, "libraryC": lib_c, "transportC": tr["steps"], "transportCBetween": tr["between"], "transportCSigmaSteps": tr["sigmaSteps"],
            "differenceSteps": d, "label": label}


def decide(p: dict, crit: dict) -> list[str]:
    comp = {c: e for c, e in p.items() if e["computed"]}
    ok = [c for c, e in comp.items() if e["label"] in ("good", "plausible")]
    far = [c for c, e in comp.items() if abs(e["differencePcm"]) > BEYOND]
    missing = [c for c in p if c not in comp]
    crit_ok = crit["computed"] and crit["label"] in ("good", "plausible")
    items = []
    if len(ok) >= MIN_GOOD_OR_PLAUSIBLE and not far and crit_ok:
        worst = max(abs(e["differencePcm"]) for e in comp.values())
        items.append(f"Q1. the lesson may be built on the library: {len(ok)} of {len(p)} cases good or plausible, none beyond {BEYOND:.0f} pcm (worst {worst:.0f} pcm), "
                     f"critical C {crit['libraryC']:.1f} steps against transport {crit['transportC']:.1f} ({crit['differenceSteps']:+.1f}, {crit['label']}); the good cases enter jointChecked; "
                     "envelope: D and C in, every other bank at its benchmark position, boron near 900 ppm, C withdrawn")
    else:
        why = []
        if len(ok) < MIN_GOOD_OR_PLAUSIBLE:
            why.append(f"only {len(ok)} of {len(p)} cases good or plausible" + (f" ({len(missing)} not computed)" if missing else ""))
        if far:
            why.append(f"beyond {BEYOND:.0f} pcm: {', '.join(far)}")
        if not crit_ok:
            why.append("the critical position is not computed" if not crit["computed"] else f"critical C is {crit['differenceSteps']:+.1f} steps from transport ({crit['label']})")
        items.append("Q2. the lesson is not built on this library: " + "; ".join(why) + "; the rod-worth work stops here unless the user opens a new plan")
    if missing:
        items.append(f"Q3. not computed: {missing}; they enter no decision item")
    return items


def _rel(p: Path) -> str:
    """The library folder as a repo-relative path, so a report carries no machine path."""
    try:
        return Path(p).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(p).name


def analyse(model: rs.ShadowModel, rows: list[dict], digest: str | None = REACTIVITY_DIGEST, boron: float = BORON) -> dict:
    check_pin(model, digest)
    p = part_p(model, rows)
    crit = critical_item(model, p, boron)
    return {"library": {"folder": _rel(model.folder), "reactivityDigest": reactivity_digest(model.m)}, "P": p, "critical": crit, "decision": {"items": decide(p, crit)}}


def print_summary(r: dict) -> None:
    print("P: near-critical cases (library minus transport, pcm; limit = the larger of 100 and 3 sigma)")
    for c, e in r["P"].items():
        print(f"   {c}: " + (f"{e['libraryPcm']:+.0f} vs {e['transportPcm']:+.0f} (sigma {e['transportSigmaPcm']:.0f}), difference {e['differencePcm']:+.0f}, {e['label']}"
                             if e["computed"] else f"not computed ({e['reason']})"))
    c = r["critical"]
    print("critical C (steps): " + (f"library {c['libraryC']:.1f}, transport {c['transportC']:.1f} +- {c['transportCSigmaSteps']:.1f} (between {c['transportCBetween']}), "
                                   f"difference {c['differenceSteps']:+.1f}, {c['label']}" if c["computed"] else f"not computed ({c['reason']})"))
    for item in r["decision"]["items"]:
        print("  decision:", item)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--library", type=Path, default=lb.LIBRARY)
    ap.add_argument("--near", type=Path, default=NEAR)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    report = {"protocol": "docs/validation/m8-near-critical-protocol.md", **analyse(rs.ShadowModel(args.library), load_near(args.near))}
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
