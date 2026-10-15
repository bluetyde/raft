"""M8: the BEAVRS library with a rod shadowing table, against 13 new held-out transport cases (part P) and the cycle 1 physics tests (part M).

Implements docs/validation/m8-rod-shadowing-protocol.md exactly (fifteenth protocol, written before any code and before any run of the new cases).
Read it first: the model, the table the library must carry, the 13 held-out cases, the labels and the decision process are fixed there, and nothing
here may change after the results are seen (a change is a new dated protocol).

  python -m validation.m8_rod_shadowing

Run from the repo root. Needs the Python reference engine; no OpenMC. Reads libraries/pwr-beavrs-hzp-openmc, pipeline/openmc/results/beavrs_sweep.jsonl,
beavrs_path.jsonl (the nine fit cases, to rebuild the fourteenth protocol's table for the comparison) and beavrs_shadow.jsonl (the 13 held-out cases).
Part M is the twelfth protocol's analysis (validation/m8_beavrs_library.py) on the new library; the model's own error adds the table's uncertainty as the
linear sum of |w_i| times the uncertainty of g at R_i (the errors of g at neighbouring knots are correlated, so the sum is the conservative choice).
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

from pipeline.library import export_beavrs as xb
from pipeline.openmc.beavrs_cases import shadow_cases
from validation import m8_beavrs_hzp as t11
from validation import m8_beavrs_library as lb
from validation import m8_rod_interaction as ri

REPO_ROOT = Path(__file__).resolve().parents[1]
SHADOW = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_shadow.jsonl"
OUT = REPO_ROOT / "validation" / "m8_rod_shadowing_report.json"

PCM = 1e5
STEPS = 228
# the protocol's table: g at the four free knots (R in pcm as a fraction); the library must carry it to within PIN_TOL
PROTOCOL_KNOTS = ((-0.0385, 0.618), (-0.03, 0.328), (-0.02, 0.392), (-0.01, 0.272))
PIN_TOL = 0.02
LIMIT_FLOOR = 100.0            # pcm: the larger of this and three times the transport error is the "good" limit
BEYOND = 400.0                 # pcm: any held-out case further off than this defeats the library
BEYOND_LESSON = 300.0          # pcm: and the lesson's own states (group L) must stay within this
MIN_OVERALL = 10               # of the 13, good or plausible
MIN_LESSON = 4                 # of the five L cases, good or plausible
MIN_ORDER = 3                  # of the four O cases, for the order claim
GROUPS = {"L": ("L-C-0", "L-C-40", "L-C-83", "L-C-120", "L-C-160"), "R": ("L-ARO-860",), "O": ("O-S3", "O-S5", "O-S6", "O-D-76"), "X": ("X-5", "X-6", "X-9")}


class PinError(RuntimeError):
    pass


class ShadowModel(lb.Model):
    """The twelfth protocol's model, with the shadowing table's errors in the model error and a way to see the library without the table."""

    def __init__(self, folder: Path):
        super().__init__(folder, expect_digest=None)
        if not self.lib.has_rod_shadow:
            raise PinError("the library has no rod shadowing table")
        t = self.m["reactivity"]["rodShadowing"]
        self.g_axis, self.g_unc = t["R"], t.get("unc", [0.0] * len(t["R"]))

    def worths(self, rods: dict[str, float]) -> list[float]:
        return [r.worth(rods[r.id]) for r in self.lib.rods]

    def correction(self, rods: dict[str, float]) -> float:
        """Sum of w_i * g(S - w_i), the engine's own formula, in the engine's unit (a fraction)."""
        ws = self.worths(rods)
        s = math.fsum(ws)
        return math.fsum(w * self.lib.rod_shadow(s - w) for w in ws if w != 0.0)

    def rod_sum(self, rods: dict[str, float]) -> float:
        return math.fsum(self.worths(rods))

    def extra(self, rods: dict[str, float]) -> float:
        ws = self.worths(rods)
        s = math.fsum(ws)
        return math.fsum(abs(w) * lb._interp(self.g_axis, self.g_unc, s - w) for w in ws if w != 0.0) * PCM

    def sigma(self, rods, boron, t_fuel=None, t_cool=None) -> float:
        return math.sqrt(super().sigma(rods, boron, t_fuel, t_cool) ** 2 + self.extra(rods) ** 2)

    def sigma_between(self, a: tuple, b: tuple) -> float:
        base = super().sigma_between(a, b)
        return math.sqrt(base ** 2 + self.extra(a[0]) ** 2 + self.extra(b[0]) ** 2)


def check_pin(model: ShadowModel, knots=PROTOCOL_KNOTS, tol: float = PIN_TOL) -> None:
    """The library's g must be the protocol's at the four free knots (within PIN_TOL), 0 at R = 0 and above, with those knots in its axis."""
    t = model.m["reactivity"]["rodShadowing"]
    got = dict(zip(t["R"], t["g"]))
    for r, g in knots:
        if not any(abs(r - a) < 1e-9 for a in got):
            raise PinError(f"the library's shadowing axis {t['R']} has no knot at R = {r}")
        have = next(v for a, v in got.items() if abs(r - a) < 1e-9)
        if abs(have - g) > tol:
            raise PinError(f"the library's g at R = {r} is {have:.3f}, the protocol fixes {g:.3f} (within {tol})")
    if any(a >= 0.0 and abs(v) > 1e-12 for a, v in got.items()):
        raise PinError("the library's g is not zero at and above R = 0")
    if len(t["R"]) != len(knots) + 2:
        raise PinError(f"the library's shadowing axis has {len(t['R'])} points, the protocol fixes {len(knots) + 2}")


def load_shadow(path: Path) -> list[dict]:
    rows = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    for r in rows:
        if not isinstance(r.get("kBatches"), list) or len(r["kBatches"]) != r.get("batches"):
            raise ValueError(f"case {r.get('case')}: kBatches missing or not one value per batch")
    xb.check_path(rows, shadow_cases(), "shadow")            # exactly the 13 cases, once, with the planned settings (boron included)
    return rows


def rho_of(r: dict) -> tuple[float, float]:
    k, sd = r["k"], r["kStd"]
    return (k - 1.0) / k * PCM, sd / k ** 2 * PCM


def label_of(diff: float, sig: float) -> tuple[str, float]:
    limit = max(LIMIT_FLOOR, 3.0 * sig)
    return ("good" if abs(diff) <= limit else "plausible" if abs(diff) <= 2.0 * limit else "fails"), limit


def part_p(model: ShadowModel, held: list[dict], v1: "ri.RIModel | None" = None) -> dict:
    by = {r["case"]: r for r in held}
    out = {}
    for cid in shadow_cases():
        r = by[cid]
        conv = t11.convergence(r)
        if not conv["converged"]:
            out[cid] = {"computed": False, "reason": f"unconverged (drift z {conv['z']:.2f})"}
            continue
        rods = {b.lower(): s / STEPS for b, s in r["steps"].items()}
        lib_rho = model.rho(rods, r["boron"])
        corr = model.correction(rods) * PCM
        tr, sig = rho_of(r)
        diff = lib_rho - tr
        label, limit = label_of(diff, sig)
        e = {"computed": True, "libraryPcm": lib_rho, "transportPcm": tr, "transportSigmaPcm": sig, "differencePcm": diff, "limitPcm": limit, "label": label,
             "correctionPcm": corr, "differenceWithoutTablePcm": diff - corr, "sumRodsPcm": model.rod_sum(rods) * PCM,
             "improvesOnTheSum": abs(diff) < abs(diff - corr), "driftZ": conv["z"]}
        if v1 is not None:
            e["differenceFourteenthPcm"] = v1.rho(rods, r["boron"]) - tr
        out[cid] = e
    return out


def decide_p(p: dict) -> list[str]:
    items = []
    comp = {c: e for c, e in p.items() if e["computed"]}
    ok = {c for c, e in comp.items() if e["label"] in ("good", "plausible")}
    far = [c for c, e in comp.items() if abs(e["differencePcm"]) > BEYOND]
    worst = max((abs(e["differencePcm"]) for e in comp.values()), default=0.0)
    missing = [c for c in p if c not in comp]
    lesson = GROUPS["L"]
    l_ok = [c for c in lesson if c in ok]
    l_far = [c for c in lesson if c in comp and abs(comp[c]["differencePcm"]) > BEYOND_LESSON]
    r_ok = GROUPS["R"][0] in ok
    l_miss = [c for c in lesson if c not in comp]
    r_miss = GROUPS["R"][0] not in comp
    # the thresholds count a case that was not computed as neither passed nor failed
    met = len(l_ok) >= MIN_LESSON and not l_far and r_ok and len(ok) >= MIN_OVERALL and not far
    possible = (not l_far and not far and len(l_ok) + len(l_miss) >= MIN_LESSON and (r_ok or r_miss) and len(ok) + len(missing) >= MIN_OVERALL)
    if met:
        items.append(f"P1. the lesson may be built on the library: {len(l_ok)} of 5 lesson cases good or plausible, none beyond {BEYOND_LESSON:.0f} pcm, L-ARO-860 {comp['L-ARO-860']['label']}; "
                     f"{len(ok)} of {len(p)} overall, none beyond {BEYOND:.0f} pcm (worst {worst:.0f} pcm); the good cases enter jointChecked; envelope: seven banks in, C withdrawn, boron near 860 ppm")
    elif not possible:
        why = []
        if len(l_ok) + len(l_miss) < MIN_LESSON:
            why.append(f"only {len(l_ok)} of 5 lesson cases good or plausible")
        if l_far:
            why.append(f"lesson cases beyond {BEYOND_LESSON:.0f} pcm: {', '.join(l_far)}")
        if not r_ok and not r_miss:
            why.append("L-ARO-860 is not good or plausible: the boron table, not the rods, is the cause")
        if len(ok) + len(missing) < MIN_OVERALL:
            why.append(f"only {len(ok)} of {len(p)} good or plausible overall")
        if far:
            why.append(f"beyond {BEYOND:.0f} pcm: {', '.join(far)}")
        items.append("P2. the lesson is not built on this model: " + "; ".join(why) +
                     "; the user chooses a narrower lesson or stops, and there is no further modelling without a new plan")
        if any(not e["improvesOnTheSum"] for e in comp.values()):
            items.append("P2b. the shadowing table does not improve on the summed model at: " + ", ".join(c for c, e in comp.items() if not e["improvesOnTheSum"]))
    else:
        items.append(f"P4. not decided: the thresholds are met only if the not-computed cases {missing} pass; they enter no decision item")
    if missing and (met or not possible):
        items.append(f"P4. not computed: {missing}; they enter no decision item ({len(ok)} of {len(comp)} computed cases good or plausible)")
    o_ok = [c for c in GROUPS["O"] if c in ok]
    o_n = len([c for c in GROUPS["O"] if c in comp])
    items.append(f"P3. the order claim: {len(o_ok)} of {len(GROUPS['O'])} other-order cases good or plausible" + (f" ({o_n} computed)" if o_n < len(GROUPS["O"]) else "") +
                 (": the library may state the correction for other insertion orders" if len(o_ok) >= MIN_ORDER else ": the notes say it is valid along the benchmark order and the lesson's path only"))
    x_ok = [c for c in GROUPS["X"] if c in ok]
    items.append(f"P5. SA and SB: checked states good or plausible: {x_ok or 'none'}; the others are claimed nowhere (the engine flags what lies beyond the axis)")
    return items


def analyse(model: ShadowModel, sweep_rows: list[dict], held_rows: list[dict], pin: tuple | None = PROTOCOL_KNOTS, v1: "ri.RIModel | None" = None) -> dict:
    if pin is not None:
        check_pin(model, pin)
    p = part_p(model, held_rows, v1)
    m = lb.analyse(model, sweep_rows)
    states = {f"S{n}": model.rho(model.rods(n), lb.BORON_REF) for n in (3, 5, 6)}
    return {"library": m["library"], "P": p, "M": {k: v for k, v in m.items() if k != "library"}, "libraryPcmAtS3S5S6": states,
            "decision": {"items": decide_p(p) + ["M: " + i for i in m["decision"]["items"]]}}


def print_summary(r: dict) -> None:
    print("P: held-out cases (library minus transport, pcm; limit = the larger of 100 and 3 sigma)")
    for c, e in r["P"].items():
        print(f"   {c}: " + (f"{e['libraryPcm']:+.0f} vs {e['transportPcm']:+.0f} (sigma {e['transportSigmaPcm']:.0f}), difference {e['differencePcm']:+.0f}, "
                             f"without the table {e['differenceWithoutTablePcm']:+.0f}, {e['label']}" if e["computed"] else f"not computed ({e['reason']})"))
    print("M: the twelfth protocol's metrics on this library")
    m = {"A": r["M"]["A"], "B": r["M"]["B"], "C": r["M"]["C"], "F": r["M"]["F"], "decision": r["M"]["decision"]}
    lb.print_summary(m)
    print("library reactivity at S3, S5, S6 (pcm):", {k: round(v) for k, v in r["libraryPcmAtS3S5S6"].items()})
    for item in r["decision"]["items"]:
        print("  decision:", item)


def fourteenth_model(sweep_path: Path, path_path: Path, tmp: Path) -> "ri.RIModel":
    """The fourteenth protocol's library rebuilt from the committed exporter (a comparison only)."""
    rows = [json.loads(x) for x in sweep_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    path_rows = [json.loads(x) for x in path_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    core = json.loads(xb.CORE.read_text(encoding="utf-8"))
    m, blobs, _ = xb.build(rows, core, path_rows=path_rows, model="interaction")
    xb.write_library(tmp / "v1", m, blobs)
    return ri.RIModel(tmp / "v1")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--library", type=Path, default=lb.LIBRARY)
    ap.add_argument("--sweep", type=Path, default=lb.SWEEP)
    ap.add_argument("--path", type=Path, default=ri.PATH)
    ap.add_argument("--shadow", type=Path, default=SHADOW)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    sweep = [json.loads(x) for x in args.sweep.read_text(encoding="utf-8").splitlines() if x.strip()]
    with tempfile.TemporaryDirectory() as d:
        v1 = fourteenth_model(args.sweep, args.path, Path(d))
        report = {"protocol": "docs/validation/m8-rod-shadowing-protocol.md", **analyse(ShadowModel(args.library), sweep, load_shadow(args.shadow), v1=v1)}
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
