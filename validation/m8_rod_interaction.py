"""M8: the BEAVRS library with a rod interaction table, against held-out transport cases (part P) and the cycle 1 physics tests (part M).

Implements docs/validation/m8-rod-interaction-protocol.md exactly (fourteenth protocol, written before any code and before any run of the held-out
cases). Read it first: the table the library must carry, the nine held-out cases, the labels, the decision process are fixed there, and nothing here
may change after the results are seen (a change is a new dated protocol).

  python -m validation.m8_rod_interaction

Run from the repo root. Needs the Python reference engine; no OpenMC. Reads libraries/pwr-beavrs-hzp-openmc, pipeline/openmc/results/beavrs_sweep.jsonl
and pipeline/openmc/results/beavrs_path.jsonl. Part M is the twelfth protocol's analysis (validation/m8_beavrs_library.py) on the new library.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from physics_ref.engine import Engine
from pipeline.library.export_beavrs import check_path
from pipeline.openmc.beavrs_cases import path_cases
from validation import m8_beavrs_hzp as t11
from validation import m8_beavrs_library as lb

REPO_ROOT = Path(__file__).resolve().parents[1]
PATH = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_path.jsonl"
OUT = REPO_ROOT / "validation" / "m8_rod_interaction_report.json"

PCM = 1e5
BORON_REF = lb.BORON_REF
STEPS = 228
# the protocol's table, (S, correction) in pcm: the library must carry it to within PIN_TOL pcm in both columns
PROTOCOL_TABLE = ((-4075.0, -1953.0), (-2632.0, -1107.0), (-1576.0, -420.0), (-827.0, 0.0), (0.0, 0.0), (100.0, 0.0))
PIN_TOL = 5.0
LIMIT_FLOOR = 100.0          # pcm, the larger of this and three times the transport error is the "good" limit
BEYOND = 400.0               # pcm: any held-out case further off than this fails the assumption
MIN_GOOD_OR_PLAUSIBLE = 7    # of the nine


class PinError(RuntimeError):
    pass


class RIModel(lb.Model):
    """The twelfth protocol's model, with the rod interaction table's own errors in the model error and a way to see the library without it."""

    def __init__(self, folder: Path):
        super().__init__(folder, expect_digest=None)
        if not self.lib.has_rod_interaction:
            raise PinError("the library has no rod interaction table")
        t = self.m["reactivity"]["rodInteraction"]
        self.ri_axis, self.ri_unc = t["S"], t.get("unc", [0.0] * len(t["S"]))

    def rod_sum(self, rods: dict[str, float]) -> float:
        s = 0.0
        for r in self.lib.rods:
            s += r.worth(rods[r.id])
        return s

    def correction(self, rods: dict[str, float]) -> float:
        return self.lib.rod_interaction(self.rod_sum(rods))

    def sigma(self, rods, boron, t_fuel=None, t_cool=None) -> float:
        base = super().sigma(rods, boron, t_fuel, t_cool)
        extra = lb._interp(self.ri_axis, self.ri_unc, self.rod_sum(rods)) * PCM
        return math.sqrt(base ** 2 + extra ** 2)

    def sigma_between(self, a: tuple, b: tuple) -> float:
        base = super().sigma_between(a, b)
        sa, sb = self.rod_sum(a[0]), self.rod_sum(b[0])
        if sa == sb:
            return base
        extra = math.hypot(lb._interp(self.ri_axis, self.ri_unc, sa), lb._interp(self.ri_axis, self.ri_unc, sb)) * PCM
        return math.sqrt(base ** 2 + extra ** 2)


def check_pin(model: RIModel, table=PROTOCOL_TABLE, tol: float = PIN_TOL) -> None:
    """The library's table must be the protocol's (to PIN_TOL pcm); a library with another table is not the one the protocol fixed."""
    t = model.m["reactivity"]["rodInteraction"]
    got = sorted(zip((s * PCM for s in t["S"]), (r * PCM for r in t["rho"])))
    want = sorted(table)
    if len(got) != len(want) or any(abs(a - b) > tol or abs(c - d) > tol for (a, c), (b, d) in zip(got, want)):
        raise PinError(f"the library's rod interaction table (pcm) is {[(round(s, 1), round(r, 1)) for s, r in got]}, the protocol fixes {list(want)}")


def load_path(path: Path) -> list[dict]:
    rows = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    for r in rows:
        if not isinstance(r.get("kBatches"), list) or len(r["kBatches"]) != r.get("batches"):
            raise ValueError(f"path case {r.get('case')}: kBatches missing or not one value per batch")
    check_path(rows)                       # exactly the nine cases, once, with the planned settings
    return rows


def rho_of(r: dict) -> tuple[float, float]:
    k, sd = r["k"], r["kStd"]
    return (k - 1.0) / k * PCM, sd / k ** 2 * PCM


def part_p(model: RIModel, path_rows: list[dict]) -> dict:
    by = {r["case"]: r for r in path_rows}
    out = {}
    for cid in path_cases():
        r = by[cid]
        conv = t11.convergence(r)
        if not conv["converged"]:
            out[cid] = {"computed": False, "reason": f"unconverged (drift z {conv['z']:.2f})"}
            continue
        rods = {b.lower(): s / STEPS for b, s in r["steps"].items()}
        lib_rho = model.rho(rods, BORON_REF)
        corr = model.correction(rods) * PCM
        tr, sig = rho_of(r)
        diff = lib_rho - tr
        limit = max(LIMIT_FLOOR, 3.0 * sig)
        label = "good" if abs(diff) <= limit else "plausible" if abs(diff) <= 2.0 * limit else "fails"
        out[cid] = {"computed": True, "libraryPcm": lib_rho, "transportPcm": tr, "transportSigmaPcm": sig, "differencePcm": diff, "limitPcm": limit,
                    "label": label, "correctionPcm": corr, "differenceWithoutTablePcm": diff - corr, "sumRodsPcm": model.rod_sum(rods) * PCM,
                    "improvesOnTheSum": abs(diff) < abs(diff - corr), "driftZ": conv["z"]}
    return out


def decide_p(p: dict) -> list[str]:
    items = []
    comp = {c: e for c, e in p.items() if e["computed"]}
    ok = [c for c, e in comp.items() if e["label"] in ("good", "plausible")]
    worst = max((abs(e["differencePcm"]) for e in comp.values()), default=0.0)
    far = [c for c, e in comp.items() if abs(e["differencePcm"]) > BEYOND]
    if len(comp) == len(p) and len(ok) >= MIN_GOOD_OR_PLAUSIBLE and not far:
        items.append(f"P1. {len(ok)} of {len(p)} held-out cases good or plausible, none beyond {BEYOND:.0f} pcm (worst {worst:.0f} pcm): the single-axis correction holds along the "
                     "benchmark path to the accuracy shown; the good cases enter jointChecked and the bank-withdrawal lesson may be built on it")
    elif len(comp) == len(p):
        bad = [f"{c} {e['differencePcm']:+.0f} pcm" for c, e in comp.items() if e["label"] == "fails" or c in far]
        items.append(f"P2. only {len(ok)} of {len(p)} held-out cases good or plausible" + (f", beyond {BEYOND:.0f} pcm: {', '.join(far)}" if far else "") +
                     f" (failing: {', '.join(bad) or 'none'}): the assumption fails; the lesson is not built on this table; the next candidate is pair terms")
        if any(not e["improvesOnTheSum"] for e in comp.values()):
            items.append("P2b. the table does not improve on the summed model at: " + ", ".join(c for c, e in comp.items() if not e["improvesOnTheSum"]) + " (not adopted unless it improves every case)")
    else:
        items.append(f"P4. not computed: {[c for c, e in p.items() if not e['computed']]}; they enter no decision item ({len(ok)} of {len(comp)} computed cases good or plausible)")
    return items


def analyse(model: RIModel, sweep_rows: list[dict], path_rows: list[dict], pin: tuple | None = PROTOCOL_TABLE) -> dict:
    if pin is not None:
        check_pin(model, pin)
    p = part_p(model, path_rows)
    m = lb.analyse(model, sweep_rows)
    states = {f"S{n}": model.rho(model.rods(n), BORON_REF) for n in (3, 5, 6)}
    return {"library": m["library"], "P": p, "M": {k: v for k, v in m.items() if k != "library"}, "libraryPcmAtS3S5S6": states,
            "decision": {"items": decide_p(p) + ["M: " + i for i in m["decision"]["items"]]}}


def print_summary(r: dict) -> None:
    print("P: held-out path cases (library minus transport, pcm; limit = the larger of 100 and 3 sigma)")
    for c, e in r["P"].items():
        print(f"   {c}: " + (f"{e['libraryPcm']:+.0f} vs {e['transportPcm']:+.0f} (sigma {e['transportSigmaPcm']:.0f}), difference {e['differencePcm']:+.0f}, "
                             f"without the table {e['differenceWithoutTablePcm']:+.0f}, {e['label']}" if e["computed"] else f"not computed ({e['reason']})"))
    print("M: the twelfth protocol's metrics on this library")
    m = {"A": r["M"]["A"], "B": r["M"]["B"], "C": r["M"]["C"], "F": r["M"]["F"], "decision": r["M"]["decision"]}
    lb.print_summary(m)
    print("library reactivity at S3, S5, S6 (pcm):", {k: round(v) for k, v in r["libraryPcmAtS3S5S6"].items()})
    for item in r["decision"]["items"]:
        print("  decision:", item)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--library", type=Path, default=lb.LIBRARY)
    ap.add_argument("--sweep", type=Path, default=lb.SWEEP)
    ap.add_argument("--path", type=Path, default=PATH)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    sweep = [json.loads(x) for x in args.sweep.read_text(encoding="utf-8").splitlines() if x.strip()]
    report = {"protocol": "docs/validation/m8-rod-interaction-protocol.md", **analyse(RIModel(args.library), sweep, load_path(args.path))}
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
