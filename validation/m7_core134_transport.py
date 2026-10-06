"""M7: the effective fuel temperature of core 134 in transport (per-element fuel temperatures against a uniform one).

Implements docs/validation/m7-core134-transport-protocol.md exactly (tenth protocol, written before any run of it). Read it first: the element
temperatures, the three runs, the metrics T1-T4 and the decision process are fixed there, and nothing here may change after results are seen
(a change is a new dated protocol).

  python -m validation.m7_core134_transport --write-temperatures    writes pipeline/openmc/results/core134_element_tfuel.json
  python -m validation.m7_core134_transport                         analyses pipeline/openmc/results/core134_transport.jsonl

Run from the repo root.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from validation import m7_core134_data as dm
from validation import m7_fuel_coefficient as fc
from validation import m7_power_ascension as base

REPO_ROOT = base.REPO_ROOT
RESULTS = REPO_ROOT / "pipeline" / "openmc" / "results"
TEMPS_FILE = RESULTS / "core134_element_tfuel.json"
RUNS = RESULTS / "core134_transport.jsonl"
LIBRARY = REPO_ROOT / "libraries" / "triga-jsi-134-openmc"
OUT = REPO_ROOT / "validation" / "m7_core134_transport_report.json"

BASE_K = 294.0
MEAN_RISE_K = 78.0
EXPONENT = 0.22
UNIFORM_K = BASE_K + MEAN_RISE_K                       # 372 K
KAPPA_LARGE, KAPPA_PARTIAL = 1.35, 1.05
EXPECTED = {"core": "134", "rods": {"T": 0.0, "K": 200.0, "V": 200.0, "R": 727.3}, "particles": 600000, "batches": 150, "inactive": 50}


# ---------------------------------------------------------------- the element temperatures

def element_temperatures(lib, mean_rise: float = MEAN_RISE_K, n: float = EXPONENT, base_k: float = BASE_K) -> tuple[dict, dict]:
    """({position: K}, {position: in-core fuel volume}) for the 48 fuel positions: rise proportional to the element's relative power density to the 1/(1+n), volume mean = mean_rise."""
    b = dm.bins_of(lib)
    f, v = {}, {}
    for e, a, fission, vol in b["cells"]:
        f[e] = f.get(e, 0.0) + fission
        v[e] = v.get(e, 0.0) + vol
    density = sum(f.values()) / sum(v.values())
    raw = {e: (f[e] / v[e] / density) ** (1.0 / (1.0 + n)) for e in f}
    norm = sum(raw[e] * v[e] for e in f) / sum(v.values())
    return {b["elements"][e]: base_k + mean_rise * raw[e] / norm for e in sorted(f)}, {b["elements"][e]: v[e] for e in f}


def temperature_report(temps: dict, volumes: dict) -> dict:
    mean = sum(t * volumes[p] for p, t in temps.items()) / sum(volumes.values())
    return {"min": min(temps.values()), "max": max(temps.values()), "volumeMeanK": mean, "count": len(temps)}


# ---------------------------------------------------------------- the runs

def load_runs(path: Path, temps: dict) -> dict:
    """{"R294", "U372", "NU372": {rho, sigma, k, kStd}}: every line must be one of the protocol's three runs, once each."""
    runs = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        r = json.loads(line)
        for key, want in EXPECTED.items():
            if r.get(key) != want:
                raise ValueError(f"{path.name} line {n}: {key} is {r.get(key)!r}, the protocol's runs have {want!r}")
        ov = r.get("overrides", {})
        if ov.get("tfuel") == BASE_K and set(ov) == {"tfuel"}:
            name = "R294"
        elif ov.get("tfuel") == UNIFORM_K and set(ov) == {"tfuel"}:
            name = "U372"
        elif set(ov) == {"elementTfuel"}:
            given = ov["elementTfuel"]
            if set(given) != set(temps) or any(abs(given[p] - temps[p]) > 1e-6 for p in temps):
                raise ValueError(f"{path.name} line {n}: the element temperatures are not the protocol's")
            name = "NU372"
        else:
            raise ValueError(f"{path.name} line {n}: unexpected overrides {ov if len(str(ov)) < 80 else sorted(ov)}")
        if name in runs:
            raise ValueError(f"{path.name} line {n}: the run {name} appears twice")
        k, sd = r["k"], r["kStd"]
        runs[name] = {"rho": (k - 1.0) / k * base.PCM, "sigma": sd / k ** 2 * base.PCM, "k": k, "kStd": sd}
    missing = [k for k in ("R294", "U372", "NU372") if k not in runs]
    if missing:
        raise ValueError(f"missing runs: {missing}")
    return runs


# ---------------------------------------------------------------- the metrics

def analyse(lib, runs: dict, data: dict, proxy_radial: float) -> dict:
    d_u = runs["U372"]["rho"] - runs["R294"]["rho"]
    d_n = runs["NU372"]["rho"] - runs["R294"]["rho"]
    s_u = (runs["U372"]["sigma"] ** 2 + runs["R294"]["sigma"] ** 2) ** 0.5
    s_n = (runs["NU372"]["sigma"] ** 2 + runs["R294"]["sigma"] ** 2) ** 0.5
    kappa = d_n / d_u
    s_k = _ratio_sigma(runs, d_n, d_u)
    label = "large" if kappa >= KAPPA_LARGE else "partial" if kappa >= KAPPA_PARTIAL else "none"
    agree = abs(kappa - proxy_radial) <= 2.0 * s_k
    t1 = {"kappa": kappa, "sigma": s_k, "label": label, "deltaUniformPcm": d_u, "deltaUniformSigma": s_u, "deltaElementsPcm": d_n, "deltaElementsSigma": s_n}
    t2 = {"proxyRadial": proxy_radial, "difference": kappa - proxy_radial, "agrees": agree, "direction": "agrees" if agree else ("higher" if kappa > proxy_radial else "lower")}
    t3 = dm.whatif(lib, data, kappa)
    return {"T1": t1, "T2": t2, "T3": t3, "decision": decide(t1, t2)}


def _ratio_sigma(runs: dict, d_n: float, d_u: float) -> float:
    """Standard error of (rho_NU - rho_R) / (rho_U - rho_R) from the three independent runs (partial derivatives)."""
    kappa = d_n / d_u
    s_nu, s_u, s_r = runs["NU372"]["sigma"], runs["U372"]["sigma"], runs["R294"]["sigma"]
    d_nu = 1.0 / d_u
    d_uu = -kappa / d_u
    d_r = (-1.0 + kappa) / d_u
    return ((d_nu * s_nu) ** 2 + (d_uu * s_u) ** 2 + (d_r * s_r) ** 2) ** 0.5


def decide(t1: dict, t2: dict) -> dict:
    items = []
    if t1["label"] in ("partial", "large") and t2["agrees"]:
        items.append("1. the radial part of the proxy is confirmed in transport: the effect is real and of the stated size; a library table referred to an effective temperature would need its own protocol")
    if t1["label"] == "none":
        items.append("2. the proxy overstates the effect in transport: the radial distribution of the fuel temperature is not an explanation")
    if not t2["agrees"]:
        items.append(f"3. the transport value ({t1['kappa']:.3f}) is {t2['direction']} than the radial proxy ({t2['proxyRadial']:.3f}): the transport value is the one to use; the axial part remains untested")
    if not items:
        items.append("none of the protocol's cases applies as written; read the metrics")
    return {"items": items, "libraryChanged": False}


def run(lib, temps: dict, volumes: dict, runs: dict, data: dict | None = None) -> dict:
    data = data or fc.load_steps()
    proxy = dm.kappa(dm.bins_of(lib)["cells"], 2.0, EXPONENT, "radial")
    out = analyse(lib, runs, data, proxy)
    out["T4"] = {"temperatures": temps, **temperature_report(temps, volumes), "reactivities": runs}
    return {"protocol": "docs/validation/m7-core134-transport-protocol.md", **out}


def print_summary(r: dict) -> None:
    print("protocol:", r["protocol"])
    t4 = r["T4"]
    print(f"  T4: {t4['count']} element temperatures, min {t4['min']:.1f} K max {t4['max']:.1f} K, volume mean {t4['volumeMeanK']:.2f} K")
    for name, v in t4["reactivities"].items():
        print(f"      {name}: k {v['k']:.5f} +- {v['kStd']:.5f}  rho {v['rho']:.0f} +- {v['sigma']:.0f} pcm")
    t1, t2 = r["T1"], r["T2"]
    print(f"  T1: uniform change {t1['deltaUniformPcm']:.0f} +- {t1['deltaUniformSigma']:.0f} pcm, per-element change {t1['deltaElementsPcm']:.0f} +- {t1['deltaElementsSigma']:.0f} pcm; kappa_T {t1['kappa']:.3f} +- {t1['sigma']:.3f} ({t1['label']})")
    print(f"  T2: radial proxy {t2['proxyRadial']:.3f}; difference {t2['difference']:+.3f}; {t2['direction']}")
    w = r["T3"]
    steps = "  ".join(f"{s['step']}:{s['modelPcm']:.0f}/{s['measuredPcm']:.0f}[{s['label'][0]}]" for s in w["labels"]["primary"]["perStep"])
    print(f"  T3: primary {w['labels']['primary']['worst']} worst {w['labels']['worst']} best {w['labels']['best']}; step 7 {w['step7Pcm']:.0f} pcm, shortfall removed {w['fractionOfShortfallRemoved']:.0%}   {steps}")
    for item in r["decision"]["items"]:
        print("  decision:", item)


def main(argv: list[str] | None = None) -> int:
    from physics_ref.library import Library

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write-temperatures", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    lib = Library(LIBRARY)
    temps, volumes = element_temperatures(lib)
    if args.write_temperatures:
        TEMPS_FILE.write_text(json.dumps({p: round(t, 6) for p, t in temps.items()}, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {TEMPS_FILE}: {temperature_report(temps, volumes)}")
        return 0
    temps = json.loads(TEMPS_FILE.read_text(encoding="utf-8"))          # the rounded values the runs used
    report = run(lib, temps, volumes, load_runs(RUNS, temps))
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
