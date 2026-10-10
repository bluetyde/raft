"""M8: the BEAVRS library (summed single-bank tables) against the cycle 1 hot zero power physics tests.

Implements docs/validation/m8-beavrs-library-protocol.md exactly (twelfth protocol, written before any run of it). Read it first: the library is
fixed by its manifest digest, the metrics A, B, C and F, the bands and the decision process are fixed there, and nothing here may change after the
results are seen (a change is a new dated protocol).

  python -m validation.m8_beavrs_library

Run from the repo root. Needs the Python reference engine (physics_ref); no OpenMC.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path

from physics_ref.engine import ENGINE_VERSION, Engine
from physics_ref.library import Library
from validation import m8_beavrs_hzp as t11

REPO_ROOT = Path(__file__).resolve().parents[1]
LIBRARY = REPO_ROOT / "libraries" / "pwr-beavrs-hzp-openmc"
SWEEP = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_sweep.jsonl"
OUT = REPO_ROOT / "validation" / "m8_beavrs_library_report.json"
DIGEST = "e9103694b658ebf986c9c6b6d66fec625d64efcce4dd823ba87d290a1123ae35"      # the protocol's manifest SHA-256

PCM = 1e5
BORON_REF = 975.0
BORON_BOUNDS = (300.0, 1600.0)       # the library's boron domain
F_FLOOR_PCM = 100.0                  # protocol decision item 4: the larger of this and three times the transport error
# the six sweep cases that match a state (protocol metric F): case id -> (state, boron)
F_CASES = {"R-D-0": (1, BORON_REF), "J-W2": (2, BORON_REF), "J-W4": (4, BORON_REF), "J-W7": (7, BORON_REF), "J-B4": (4, 686.0), "J-B7": (7, 508.0)}


class DigestError(RuntimeError):
    pass


def _interp(xs: list[float], ys: list[float], x: float) -> float:
    """Linear interpolation, ends held constant (the table's clamp)."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_right(xs, x) - 1
    t = (x - xs[i]) / (xs[i + 1] - xs[i])
    return ys[i] + t * (ys[i + 1] - ys[i])


class Model:
    """The library, read by the Python engine, with the statistical errors of its tables."""

    def __init__(self, folder: Path, expect_digest: str | None = DIGEST):
        self.folder = Path(folder)
        raw = (self.folder / "manifest.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        if expect_digest is not None and self.digest != expect_digest:
            raise DigestError(f"the manifest hash is {self.digest}, the protocol fixes {expect_digest}")
        self.lib = Library(self.folder)
        self.m = json.loads(raw)
        r = self.m["reactivity"]
        self.unc_rods = {x["id"]: (x["worth"]["x"], x["worth"]["unc"]) for x in r["rods"]}
        self.unc_fuel = (r["fuelTemp"]["T"], r["fuelTemp"]["unc"])
        self.unc_cool = (r["coolantTemp"]["T"], r["coolantTemp"]["unc"])
        self.unc_boron = (r["boron"]["C"], r["boron"]["unc"])
        self.boron_axis, self.boron_rho = r["boron"]["C"], r["boron"]["rho"]
        self.t_ref = self.m["reference"]["Tfuel"]["value"]

    def rods(self, state: int) -> dict[str, float]:
        out = dict(self.lib.ref_rods)
        for b in t11.banks_in(state):
            out[b.lower()] = 0.0
        return out

    def rho(self, rods: dict[str, float], boron: float, t_fuel: float | None = None, t_cool: float | None = None) -> float:
        """pcm: the engine's total reactivity at the state, from a fresh engine at zero power."""
        init = {"rods": rods, "boron": boron, "Tfuel": t_fuel if t_fuel is not None else self.t_ref,
                "Tcoolant": t_cool if t_cool is not None else self.t_ref, "power": {"mode": "given", "value": 1e-3}, "poisons": {"mode": "zero"}}
        e = Engine(self.lib, init)
        return e.reactivity(0.0, e.y)["total"] * PCM

    def sigma(self, rods: dict[str, float], boron: float, t_fuel: float | None = None, t_cool: float | None = None) -> float:
        """pcm: the quadrature of the tables' own statistical errors at their interpolated points (the reference ρ's error is not included, as in the protocol)."""
        parts = [_interp(*self.unc_rods[rid], x) for rid, x in rods.items()]
        parts.append(_interp(*self.unc_fuel, t_fuel if t_fuel is not None else self.t_ref))
        parts.append(_interp(*self.unc_cool, t_cool if t_cool is not None else self.t_ref))
        parts.append(_interp(*self.unc_boron, boron))
        return math.sqrt(sum((p * PCM) ** 2 for p in parts))

    def boron_worth(self, boron: float) -> float:
        """pcm/ppm, positive: minus the slope of the boron table at `boron`."""
        ax, rho = self.boron_axis, self.boron_rho
        i = min(max(bisect.bisect_right(ax, boron) - 1, 0), len(ax) - 2)
        return -(rho[i + 1] - rho[i]) / (ax[i + 1] - ax[i]) * PCM


def label(z: float) -> str:
    return t11.label(z)


def critical_boron(model: Model, state: int, bounds: tuple[float, float]) -> float | None:
    lo, hi = bounds
    rods = model.rods(state)
    f_lo, f_hi = model.rho(rods, lo), model.rho(rods, hi)
    if not (f_lo > 0.0 > f_hi):
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if model.rho(rods, mid) > 0.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 0.005:
            break
    return 0.5 * (lo + hi)


def analyse(model: Model, sweep_rows: list[dict], bounds: tuple[float, float] = BORON_BOUNDS) -> dict:
    out: dict = {"library": {"digest": model.digest, "id": model.m["id"], "engineVersion": ENGINE_VERSION}}

    # A: critical boron
    A = {}
    for s, (meas, sig_meas) in t11.CB.items():
        cb = critical_boron(model, s, bounds)
        if cb is None:
            A[s] = {"computed": False, "reason": f"no sign change of the reactivity inside {bounds[0]:.0f} to {bounds[1]:.0f} ppm"}
            continue
        rods = model.rods(s)
        bw = model.boron_worth(cb)
        sig_ppm = model.sigma(rods, cb) / bw
        err = cb - meas
        z = err / math.hypot(sig_meas, sig_ppm)
        A[s] = {"computed": True, "criticalPpm": cb, "measuredPpm": meas, "errorPpm": err, "sigmaModelPpm": sig_ppm, "z": z, "label": label(z),
                "within50ppm": abs(err) <= t11.CB_CRITERION_PPM, "boronWorthPcmPerPpm": bw}
    out["A"] = A

    # B: sequential bank worths at the reference boron and temperature
    rho_s = {n: model.rho(model.rods(n), BORON_REF) for n in range(8)}
    sig_s = {n: model.sigma(model.rods(n), BORON_REF) for n in range(8)}
    banks = {}
    for i, b in enumerate(t11.BANKS):
        meas, sig_meas = t11.WORTH[b]
        w, sig = rho_s[i] - rho_s[i + 1], math.hypot(sig_s[i], sig_s[i + 1])
        z = (w - meas) / math.hypot(sig_meas, sig)
        banks[b] = {"computed": True, "worthPcm": w, "measuredPcm": meas, "difference": w - meas, "relative": (w - meas) / meas, "sigmaModelPcm": sig, "z": z, "label": label(z)}
    tw, tsig = rho_s[0] - rho_s[7], math.hypot(sig_s[0], sig_s[7])
    tm, tsm = t11.total_worth()
    z = (tw - tm) / math.hypot(tsm, tsig)
    out["B"] = {"banks": banks, "total": {"computed": True, "worthPcm": tw, "measuredPcm": tm, "difference": tw - tm, "relative": (tw - tm) / tm, "sigmaModelPcm": tsig, "z": z, "label": label(z)}}

    # C: ITC with fuel and coolant shifted together
    C = {}
    for s, (meas, sig_meas) in t11.ITC.items():
        rods = model.rods(s)
        tp, tm_ = model.t_ref + t11.T_STEP, model.t_ref - t11.T_STEP
        itc = (model.rho(rods, BORON_REF, tp, tp) - model.rho(rods, BORON_REF, tm_, tm_)) / t11.DELTA_F
        sig = math.hypot(model.sigma(rods, BORON_REF, tp, tp), model.sigma(rods, BORON_REF, tm_, tm_)) / t11.DELTA_F
        z = (itc - meas) / math.hypot(sig_meas, sig)
        C[s] = {"computed": True, "itcPcmPerF": itc, "measuredPcmPerF": meas, "sigmaModelPcmPerF": sig, "z": z, "label": label(z)}
    out["C"] = C

    # F: the library minus its transport source
    by = {r["case"]: r for r in sweep_rows}
    F = {}
    for cid, (s, b) in F_CASES.items():
        if cid not in by:
            F[cid] = {"computed": False, "reason": "the case is not in the sweep"}
            continue
        k, sd = by[cid]["k"], by[cid]["kStd"]
        tr, tr_sig = (k - 1.0) / k * PCM, sd / k ** 2 * PCM
        lib_rho = model.rho(model.rods(s), b)
        diff = lib_rho - tr
        F[cid] = {"computed": True, "state": s, "boronPpm": b, "libraryPcm": lib_rho, "transportPcm": tr, "transportSigmaPcm": tr_sig, "differencePcm": diff,
                  "exceeds": abs(diff) > max(F_FLOOR_PCM, 3.0 * tr_sig)}
    out["F"] = F
    out["decision"] = decide(out)
    return out


def decide(m: dict) -> dict:
    items = []
    a = [(s, e) for s, e in m["A"].items() if e["computed"]]
    ok = [s for s, e in a if e["label"] in ("good", "plausible")]
    if len(a) == 5 and len(ok) >= 4:
        items.append(f"1. the library reproduces the critical boron at {len(ok)} of 5 states ({', '.join('S' + str(s) for s in ok)}): its rod-combination claim may be widened to those states, with the numbers shown")
    else:
        items.append(f"1. the library reproduces the critical boron at {len(ok)} of {len(a)} computed states ({', '.join('S' + str(s) for s in ok) or 'none'}); its claim stays at the reference configuration plus those states, and the README and supported-envelope get the measured differences")
    failed = [b for b, e in m["B"]["banks"].items() if e["label"] == "fails"]
    if failed:
        items.append(f"2. bank worths that fail: {', '.join(failed)} (sign and size in the table); nothing is refitted")
    if m["B"]["total"]["label"] == "fails":
        items.append("2. the total fails: the library's rod worth model is not validated for combined insertion")
    fc = [s for s, e in m["C"].items() if e["label"] == "fails"]
    if fc:
        items.append(f"3. the temperature coefficient fails at {', '.join('S' + str(s) for s in fc)}: the temperature feedback stays not validated" + ("; a failure at S2 comes with the library having no rod dependence of its temperature tables" if 2 in fc else ""))
    ex = [c for c, e in m["F"].items() if e["computed"] and e["exceeds"]]
    if ex:
        items.append(f"4. the summed tables differ from their transport source by more than the limit at {', '.join(ex)}: the results note names the smallest format change that would remove it (not built here; a separate decision)")
    else:
        items.append("4. no difference from the transport source exceeds the limit")
    nc_ = [f"A:S{s}" for s, e in m["A"].items() if not e["computed"]] + [f"F:{c}" for c, e in m["F"].items() if not e["computed"]]
    if nc_:
        items.append(f"5. not computed: {nc_} (they enter no decision item)")
    items.append("6. the library status stays experimental; nothing is refitted")
    return {"items": items, "libraryChanged": False}


def print_summary(m: dict) -> None:
    print("A: critical boron (library minus measured; positive = the library needs more boron)")
    for s, e in m["A"].items():
        print(f"   S{s}: " + (f"{e['criticalPpm']:.1f} vs {e['measuredPpm']:.0f} ppm, error {e['errorPpm']:+.1f} +- {e['sigmaModelPpm']:.1f}, z {e['z']:+.2f} ({e['label']}), within 50 ppm: {e['within50ppm']}" if e["computed"] else e["reason"]))
    print("B: sequential bank worths")
    for b, e in m["B"]["banks"].items():
        print(f"   {b}: {e['worthPcm']:.0f} vs {e['measuredPcm']:.0f} pcm ({e['relative']:+.1%}) z {e['z']:+.2f} ({e['label']})")
    t = m["B"]["total"]
    print(f"   total: {t['worthPcm']:.0f} vs {t['measuredPcm']:.0f} pcm ({t['relative']:+.1%}) z {t['z']:+.2f} ({t['label']})")
    print("C: ITC")
    for s, e in m["C"].items():
        print(f"   S{s}: {e['itcPcmPerF']:+.2f} vs {e['measuredPcmPerF']:+.2f} pcm/F z {e['z']:+.2f} ({e['label']})")
    print("F: library minus transport")
    for c, e in m["F"].items():
        print(f"   {c}: " + (f"{e['libraryPcm']:+.0f} vs {e['transportPcm']:+.0f} pcm, difference {e['differencePcm']:+.0f} (transport sigma {e['transportSigmaPcm']:.0f}), exceeds {e['exceeds']}" if e["computed"] else e["reason"]))
    for item in m["decision"]["items"]:
        print("  decision:", item)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--library", type=Path, default=LIBRARY)
    ap.add_argument("--sweep", type=Path, default=SWEEP)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    rows = [json.loads(line) for line in args.sweep.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = {"protocol": "docs/validation/m8-beavrs-library-protocol.md", **analyse(Model(args.library), rows)}
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
