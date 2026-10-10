"""Export the BEAVRS hot-zero-power sweep (pipeline/openmc/results/beavrs_sweep.jsonl) to the library libraries/pwr-beavrs-hzp-openmc.

    python -m pipeline.library.export_beavrs [--sweep PATH] [--core PATH] [--out DIR] [--report PATH]

Plan: docs/m8-beavrs-exporter-plan.md. The sweep gives every reactivity table and shape; the plant (instruments, trips, thermal masses, rod
speed) is assumed and labelled so. Soluble boron needs the capability point-kinetics/boron-v1 (library-format section 15).
Standard library only (it reuses the table fit and float32 helpers of export_openmc and synthetic).
"""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import math
import shutil
import sys
from pathlib import Path

from pipeline.library.export_openmc import _pack_f32_slice_normalized, interp, isotonic
from pipeline.library.synthetic import descriptor, pack

REPO_ROOT = Path(__file__).resolve().parents[2]
SWEEP = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_sweep.jsonl"
CORE = REPO_ROOT / "pipeline" / "openmc" / "data" / "beavrs_core.json"
OUT = REPO_ROOT / "libraries" / "pwr-beavrs-hzp-openmc"
REPORT = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_export_report.json"

LIB_ID = "pwr-beavrs-hzp-openmc"
BANKS = ["A", "B", "C", "D", "SA", "SB", "SC", "SD", "SE"]
STEPS = 228
BITE = 213
N_AXIAL = 10
LATTICE = 19
T_REF_ROUND = 6                 # decimals kept on the reference temperature
TF_CASES = {"TF-500": 500.0, "TF-700": 700.0, "TF-900": 900.0}
TC_CASES = {"TC-500": 500.0, "TC-540": 540.0, "TC-600": 600.0, "TC-620": 620.0}
B_CASES = {"B-300": 300.0, "B-600": 600.0, "B-1300": 1300.0, "B-1600": 1600.0}
JOINT_RHO = ("J-W2", "J-W4", "J-W7")
JOINT_BORON = ("J-B4", "J-B7")
FUEL_DENSITY = 10.3             # g/cm3: BEAVRS fuel densities by enrichment run from 10.29 to 10.36
# U-235 delayed-neutron decay constants of ENDF/B-VIII.0 (read from neutron/U235.h5, reaction 18, 2026-10-10); the TRIGA libraries use Keepin's
LAMBDA_ENDF = [0.01334, 0.03274, 0.12078, 0.30278, 0.84949, 2.853]


def rid(bank: str) -> str:
    return bank.lower()


def rho_of(row: dict) -> tuple[float, float]:
    k, s = float(row["k"]), float(row["kStd"])
    return (k - 1.0) / k, s / (k * k)


def x_of(steps: float) -> float:
    return round(float(steps) / STEPS, 12)


def S(value: float, source: str = "assumed", **extra) -> dict:
    return {"value": value, "source": source, **extra}


# ---------------------------------------------------------------- fitting

def fit_rod(points: list[dict]) -> dict:
    """points: dicts x, rho (relative to the reference), sigma, ref. Weighted isotonic (non-decreasing) fit, forced to 0 at the reference."""
    pts = sorted(points, key=lambda p: p["x"])
    xs = [p["x"] for p in pts]
    ws = [1e12 if p["ref"] else 1.0 / (p["sigma"] ** 2) for p in pts]
    fit = isotonic(xs, [p["rho"] for p in pts], ws)
    i = next(i for i, p in enumerate(pts) if p["ref"])
    fit = [y - fit[i] for y in fit]
    fit[i] = 0.0
    return {"x": xs, "rho": fit, "unc": [0.0 if p["ref"] else p["sigma"] for p in pts], "raw": [p["rho"] for p in pts]}


def fit_decreasing(points: list[dict], monotone: bool) -> dict:
    pts = sorted(points, key=lambda p: p["a"])
    xs = [p["a"] for p in pts]
    ys = [p["rho"] for p in pts]
    i = next(i for i, p in enumerate(pts) if p["ref"])
    if monotone:
        ws = [1e12 if p["ref"] else 1.0 / (p["sigma"] ** 2) for p in pts]
        ys2 = [-v for v in isotonic(xs, [-y for y in ys], ws)]
        ys2 = [y - ys2[i] for y in ys2]
        ys2[i] = 0.0
    else:
        ys2 = list(ys)
    return {"a": xs, "rho": ys2, "unc": [0.0 if p["ref"] else p["sigma"] for p in pts], "raw": ys}


# ---------------------------------------------------------------- shapes

def assembly_shape(row: dict, core: dict, key: str = "fission") -> list[float]:
    """The mesh tally (z, y, x; x fastest, y up) reduced to the fuel assemblies: [element][axial], flattened, element-major."""
    vec = row[key]
    nxy = LATTICE * LATTICE
    if len(vec) != N_AXIAL * nxy:
        raise ValueError(f"case {row['case']}: expected {N_AXIAL * nxy} mesh values, got {len(vec)}")
    return [vec[z * nxy + a["y"] * LATTICE + a["x"]] for a in core["assemblies"] for z in range(N_AXIAL)]


def normalized(v: list[float]) -> list[float]:
    s = math.fsum(v)
    if not s > 0:
        raise ValueError("a shape sums to zero")
    return [a / s for a in v]


# ---------------------------------------------------------------- build

def build(rows: list[dict], core: dict, created: str | None = None) -> tuple[dict, dict[str, bytes], dict]:
    by = {r["case"]: r for r in rows}
    for need in ["REF", "R-D-228", *TF_CASES, *TC_CASES, *B_CASES, *JOINT_RHO, *JOINT_BORON] + [f"R-{b}-{n}" for b in BANKS for n in (0, 76, 152)]:
        if need not in by:
            raise ValueError(f"the sweep has no case {need}")
    ref = by["REF"]
    rho_ref, sig_ref = rho_of(ref)
    for b in BANKS:
        if ref["steps"][b] != (BITE if b == "D" else STEPS):
            raise ValueError(f"REF has bank {b} at {ref['steps'][b]} steps, not the benchmark configuration")
    t_ref = round(float(core.get("hzpTemperatureK", 566.483)), T_REF_ROUND)
    b_ref = float(ref["boron"])

    def rel(case: str) -> tuple[float, float]:
        r, s = rho_of(by[case])
        return r - rho_ref, math.hypot(s, sig_ref)

    # rods
    rod_tables = {}
    for b in BANKS:
        ref_steps = ref["steps"][b]
        pts = [{"x": x_of(ref_steps), "rho": 0.0, "sigma": 0.0, "ref": True}]
        names = [f"R-{b}-{n}" for n in (0, 76, 152)] + (["R-D-228"] if b == "D" else [])
        for c in names:
            steps = by[c]["steps"][b]
            d, s = rel(c)
            pts.append({"x": x_of(steps), "rho": d, "sigma": s, "ref": False})
        rod_tables[b] = fit_rod(pts)

    def curve(cases: dict[str, float], ref_a: float, key_t: str | None, monotone: bool) -> dict:
        pts = [{"a": ref_a, "rho": 0.0, "sigma": 0.0, "ref": True}]
        for c, a in cases.items():
            d, s = rel(c)
            pts.append({"a": a, "rho": d, "sigma": s, "ref": False})
        return fit_decreasing(pts, monotone)

    fuel_t = curve(TF_CASES, t_ref, None, True)
    cool_t = curve(TC_CASES, t_ref, None, False)
    boron_t = curve(B_CASES, b_ref, None, True)

    # shapes: normalized to 1 over the 193 assemblies in every case
    elements = [a["label"] for a in core["assemblies"]]
    E, A = len(elements), N_AXIAL
    n = E * A
    base64 = normalized(assembly_shape(ref, core))
    base_unc = [s / math.fsum(assembly_shape(ref, core)) for s in assembly_shape(ref, core, "fissionStd")]
    blobs: dict[str, bytes] = {}
    arrays: dict[str, dict] = {}

    def add(name: str, values: list[float], shape: list[int]) -> None:
        blobs[f"arrays/{name}.f32"] = pack(values)
        arrays[name] = descriptor(f"arrays/{name}.f32", blobs[f"arrays/{name}.f32"], shape)

    base_f32 = _pack_f32_slice_normalized(base64, 1.0)
    add("base", base_f32, [E, A])
    add("baseUnc", base_unc, [E, A])
    height = (core["activeFuelTopCm"] - core["activeFuelBotCm"]) / N_AXIAL
    pin_area = math.pi * core["pelletRadiusCm"] ** 2
    add("volumes", [core["fuelPinsPerAssembly"] * pin_area * height] * n, [E, A])

    def shape_of(case: str) -> list[float]:
        return normalized(assembly_shape(by[case], core))

    def delta_slices(grid_cases: list[tuple[float, str | None]]) -> tuple[list[list[float]], list[list[float]]]:
        f64, f32 = [], []
        for _, case in grid_cases:
            d = [0.0] * n if case is None else [a - b for a, b in zip(shape_of(case), base64)]
            f64.append(d)
            f32.append(_pack_f32_slice_normalized(d, 0.0))
        return f64, f32

    delta64: dict[str, list[list[float]]] = {}
    rod_delta_manifest = {}
    for b in BANKS:
        t = rod_tables[b]
        case_at = {x_of(by[c]["steps"][b]): c for c in [f"R-{b}-{k}" for k in (0, 76, 152)] + (["R-D-228"] if b == "D" else [])}
        grid = [(x, case_at.get(x)) for x in t["x"]]
        f64, f32 = delta_slices(grid)
        delta64[rid(b)] = f64
        add(f"rod_{rid(b)}", [v for sl in f32 for v in sl], [len(grid), E, A])
        rod_delta_manifest[rid(b)] = {"x": t["x"], "array": f"rod_{rid(b)}"}
    t_grid = fuel_t["a"]
    f64, f32 = delta_slices([(T, None if T == t_ref else next(c for c, tt in TF_CASES.items() if tt == T)) for T in t_grid])
    delta64["_fuelTemp"] = f64
    add("tempDelta", [v for sl in f32 for v in sl], [len(t_grid), E, A])

    # reactivity tables and the self-check
    tables = {"rods": {rid(b): rod_tables[b] for b in BANKS}, "fuel": fuel_t, "cool": cool_t, "boron": boron_t}

    def predict(row: dict) -> tuple[float, list[float]]:
        rho = rho_ref
        shape = list(base_f32)
        for b in BANKS:
            x = x_of(row["steps"][b])
            t = rod_tables[b]
            rho += interp(t["x"], t["rho"], x)
            sl = interp_slice(t["x"], delta64[rid(b)], x)
            shape = [s + d for s, d in zip(shape, sl)]
        if row.get("tFuel") is not None:
            rho += interp(fuel_t["a"], fuel_t["rho"], float(row["tFuel"]))
            shape = [s + d for s, d in zip(shape, interp_slice(fuel_t["a"], delta64["_fuelTemp"], float(row["tFuel"])))]
        if row.get("tWater") is not None:
            rho += interp(cool_t["a"], cool_t["rho"], float(row["tWater"]))
        rho += interp(boron_t["a"], boron_t["rho"], float(row["boron"]))
        return rho, shape

    check = {}
    for r in rows:
        rho_p, shape_p = predict(r)
        rho_c, sig_c = rho_of(r)
        err = shape_err(shape_p, shape_of(r["case"]))
        check[r["case"]] = {"rhoCase": rho_c, "rhoPred": rho_p, "rhoErr": abs(rho_p - rho_c), "rhoSigma": sig_c, "maxShapeErr": err}
    joint = []
    for c in JOINT_RHO:
        r = by[c]
        joint.append({"rods": {rid(b): x_of(r["steps"][b]) for b in BANKS}, "maxShapeErr": check[c]["maxShapeErr"], "rhoErr": check[c]["rhoErr"]})

    # manifest
    thermal_mass_kg = core["fuelPinsPerAssembly"] * len(core["assemblies"]) * pin_area * (core["activeFuelTopCm"] - core["activeFuelBotCm"]) * FUEL_DENSITY / 1000.0
    half = (core["activeFuelTopCm"] + core["activeFuelBotCm"]) / 2.0
    edges = [round(core["activeFuelBotCm"] - half + k * height, 6) for k in range(N_AXIAL + 1)]
    pitch = core["latticePitchCm"]
    absorber_len = core["rcca"]["stepWidthCm"] * STEPS
    rod_mid = round(core["activeFuelTopCm"] - half - absorber_len / 2.0, 6)       # fully inserted: the absorber's top is the top of the active fuel

    rods = []
    for b in BANKS:
        t = rod_tables[b]
        rods.append({
            "id": rid(b), "name": f"{'Shutdown' if b.startswith('S') else 'Control'} bank {b[1:] if b.startswith('S') else b}",
            "travelCm": round(absorber_len, 4), "speed": round(72.0 / 60.0 / STEPS, 9), "pulseCapable": False,
            "worth": {"x": t["x"], "rho": t["rho"], "unc": t["unc"], "interp": "linear", "outOfRange": "clamp-and-flag", "source": "transport"},
            "scram": {"t": [0.0, 0.2, 0.6, 1.0, 1.5, 2.0], "x": [1.0, 0.97, 0.8, 0.5, 0.15, 0.0], "source": "assumed"},
        })

    geometry = [
        {"type": "annulus", "center": [0, 0, 0], "rInner": core["vesselCm"]["barrelIR"], "radius": core["vesselCm"]["barrelOR"], "height": 420.0, "material": "steel"},
    ]
    box = 17 * core["pinPitchCm"]
    for a in core["assemblies"]:
        cx, cy = round((a["x"] - 9) * pitch, 4), round((a["y"] - 9) * pitch, 4)
        geometry.append({"type": "box", "center": [cx, cy, 0.0], "size": [round(box, 4), round(box, 4), round(core["activeFuelTopCm"] - core["activeFuelBotCm"], 4)],
                         "material": "fuel", "element": a["label"]})
        if a["bank"]:
            geometry.append({"type": "cylinder", "center": [cx, cy, rod_mid], "radius": 6.0, "height": round(absorber_len, 4), "material": "b4c", "rod": rid(a["bank"])})

    domain_rods = {rid(b): [min(rod_tables[b]["x"]), max(rod_tables[b]["x"])] for b in BANKS}
    created = created or datetime.date.today().isoformat()
    m = {
        "schemaVersion": "0.1.0",
        "id": LIB_ID,
        "name": "PWR (BEAVRS cycle 1) at hot zero power, built with OpenMC",
        "status": "experimental",
        "capabilities": ["point-kinetics/lumped-thermal-v1", "point-kinetics/boron-v1"],
        "provenance": {
            "generator": "pipeline.library.export_beavrs", "transportCode": f"OpenMC {ref.get('openmc', '')}".strip(),
            "nuclearData": "ENDF/B-VIII.0", "model": "BEAVRS 3D full core, hot zero power (mit-crpg/BEAVRS, MIT licence), 45 cases of pipeline/openmc/beavrs_cases.py",
            "created": created,
            "notes": ("Zero-power physics only. Reactivity tables, kinetics, shapes and boron worth come from the transport sweep; the plant (rod speed, scram, "
                      "thermal masses, heat transfer, instruments, trips) is assumed and labelled so. Isothermal temperature coefficient: the transport model is "
                      "1.6 to 2.0 pcm/F too negative against the benchmark measurement (docs/validation/m8-beavrs-hzp-results.md), so temperature feedback is NOT validated. "
                      "Xenon worth is zero (not computed); no decay heat; no pressure. The shape of the power does not depend on coolant temperature or boron."),
            "sources": [
                {"id": "beavrs", "cite": "N. Horelik, B. Herman, B. Forget, K. Smith, Benchmark for Evaluation And Validation of Reactor Simulations (BEAVRS), v2.0.2, MIT Computational Reactor Physics Group, github.com/mit-crpg/BEAVRS (MIT licence)"},
                {"id": "endfbviii0-u235", "cite": "ENDF/B-VIII.0 (Brown et al., Nucl. Data Sheets 148 (2018) 1): U-235 delayed-neutron group decay constants as read from the HDF5 library"},
            ],
        },
        "reference": {
            "rods": {rid(b): x_of(ref["steps"][b]) for b in BANKS},
            "Tfuel": S(t_ref, "transport"), "Tcoolant": S(t_ref, "transport"), "xenon": S(0.0, "transport"), "boron": S(b_ref, "transport"),
            "rho": S(rho_ref, "transport", unc=sig_ref), "calibration": None,
        },
        "kinetics": {
            "beta": {"values": ref["betaGroups"], "unc": ref["betaGroupsStd"], "source": "transport"},
            "lambda": {"values": LAMBDA_ENDF, "source": "cited:endfbviii0-u235"},
            "genTime": S(ref["lambdaS"], "transport", unc=ref["lambdaStdS"]),
            "extSource": S(2.0),
        },
        "reactivity": {
            "rods": rods,
            "fuelTemp": {"T": fuel_t["a"], "rho": fuel_t["rho"], "unc": fuel_t["unc"], "interp": "linear", "outOfRange": "clamp-and-flag", "source": "transport"},
            "coolantTemp": {"T": cool_t["a"], "rho": cool_t["rho"], "unc": cool_t["unc"], "interp": "linear", "outOfRange": "clamp-and-flag", "source": "transport"},
            "xenon": {"N": [0.0, 1e20, 2e20, 4e20], "rho": [0.0, 0.0, 0.0, 0.0], "interp": "linear", "outOfRange": "extrapolate-and-flag", "source": "assumed"},
            "boron": {"C": boron_t["a"], "rho": boron_t["rho"], "unc": boron_t["unc"], "interp": "linear", "outOfRange": "clamp-and-flag", "source": "transport"},
        },
        "thermal": {
            "fuel": {"mass": S(round(thermal_mass_kg, 1), "cited:beavrs"),
                     "cp": {"T": [300.0, 500.0, 700.0, 900.0, 1200.0], "c": [235.0, 285.0, 310.0, 325.0, 345.0], "interp": "linear", "outOfRange": "clamp-and-flag", "source": "assumed"}},
            "coolant": {"mass": S(2.6e5), "cp": S(5600.0)},
            "hA": S(8.5e6),
            "heatExchanger": {"UA": S(1.7e8), "sinkTemp": S(t_ref), "pump": "rcp"},
            "deposition": {"fuelFraction": S(0.974)},
        },
        "poisons": {"fluxPerWatt": S(8.8e7), "sigmaF": S(5.0), "gammaI": S(0.061), "gammaXe": S(0.003), "lambdaI": S(2.87e-5), "lambdaXe": S(2.09e-5), "sigmaXe": S(2.6e-22)},
        "plant": {
            "modes": ["steady"], "initialMode": "steady", "pumps": [{"id": "rcp"}],
            "instruments": [
                {"id": "linear", "signal": "truth.power", "scale": "linear", "range": [0.0, 4.1e9], "lag": 0.5, "noise": 0.01},
                {"id": "log", "signal": "truth.power", "scale": "log", "range": [1e-8, 4.1e9], "lag": 0.05, "noise": 0.02},
                {"id": "fuel-tc", "signal": "truth.fuelTemp", "scale": "linear", "range": [273.15, 1273.15], "lag": 2.0, "noise": 0.002},
                {"id": "tavg", "signal": "truth.coolantTemp", "scale": "linear", "range": [473.15, 673.15], "lag": 5.0, "noise": 0.001},
            ],
            "trips": [
                {"id": "power-high", "input": "indicated.linear", "predicate": {"op": "gt", "value": 3.718e9}, "modes": ["steady"], "latching": True},
                {"id": "zero-power-limit", "input": "indicated.log", "predicate": {"op": "gt", "value": 1.7e6}, "modes": ["steady"], "latching": True},
                {"id": "period-short", "input": "truth.period", "predicate": {"all": [{"op": "gt", "value": 0.0}, {"op": "lt", "value": 10.0}]}, "modes": ["steady"], "latching": True},
            ],
            "interlocks": [],
            "boron": {"range": [0.0, 2000.0], "maxRatePpmPerS": 0.1},
        },
        "shapes": {
            "bins": {"elements": elements, "axialEdgesCm": edges},
            "basis": "fission", "normalization": "fraction-of-total-power", "form": "separable",
            "base": "base", "baseUnc": "baseUnc", "volumes": "volumes",
            "rodDeltas": rod_delta_manifest,
            "tempDelta": {"T": t_grid, "array": "tempDelta"},
        },
        "arrays": arrays,
        "geometry": {"units": "cm", "up": "z", "primitives": geometry},
        "domain": {
            "rods": domain_rods, "Tfuel": [min(fuel_t["a"]), max(fuel_t["a"])], "Tcoolant": [min(cool_t["a"]), max(cool_t["a"])],
            "xenon": [0.0, 4e20], "boron": [min(boron_t["a"]), max(boron_t["a"])], "jointChecked": joint,
        },
    }
    report = {
        "created": created, "rhoRef": rho_ref, "rhoRefSigma": sig_ref, "tables": {k: v for k, v in tables.items() if k != "rods"},
        "rodTables": {b: rod_tables[b] for b in BANKS}, "cases": check,
        "boronSeparability": {c: check[c] for c in JOINT_BORON},
        "negativeShapeBins": sum(1 for v in base_f32 if v <= 0),
    }
    return m, blobs, report


def interp_slice(xs: list[float], slices: list[list[float]], x: float) -> list[float]:
    if x <= xs[0]:
        return list(slices[0])
    if x >= xs[-1]:
        return list(slices[-1])
    import bisect
    i = bisect.bisect_right(xs, x) - 1
    t = (x - xs[i]) / (xs[i + 1] - xs[i])
    return [(1.0 - t) * a + t * b for a, b in zip(slices[i], slices[i + 1])]


def shape_err(pred: list[float], case: list[float]) -> float:
    """Largest bin difference as a multiple of the mean bin (the unit the TRIGA libraries report)."""
    if len(pred) != len(case):
        raise ValueError("shape length mismatch")
    return max(abs(a - b) for a, b in zip(pred, case)) * len(pred)


def write_library(folder: Path, m: dict, blobs: dict[str, bytes]) -> None:
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "arrays").mkdir(parents=True)
    for name, data in blobs.items():
        (folder / name).write_bytes(data)
    (folder / "manifest.json").write_bytes((json.dumps(m, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sweep", type=Path, default=SWEEP)
    ap.add_argument("--core", type=Path, default=CORE)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--report", type=Path, default=REPORT)
    args = ap.parse_args(argv)
    rows = [json.loads(line) for line in args.sweep.read_text(encoding="utf-8").splitlines() if line.strip()]
    core = json.loads(args.core.read_text(encoding="utf-8"))
    m, blobs, report = build(rows, core)
    write_library(args.out, m, blobs)
    args.report.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(m['shapes']['bins']['elements'])} assemblies, {len(m['reactivity']['rods'])} rods); report {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
