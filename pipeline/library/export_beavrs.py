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
from pipeline.library.validate import validate_library
from pipeline.openmc.beavrs_cases import BEAVRS_HEAD, near_cases, path_cases, shadow_cases, sweep_cases

REPO_ROOT = Path(__file__).resolve().parents[2]
SWEEP = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_sweep.jsonl"
CORE = REPO_ROOT / "pipeline" / "openmc" / "data" / "beavrs_core.json"
OUT = REPO_ROOT / "libraries" / "pwr-beavrs-hzp-openmc"
README = Path(__file__).with_name("beavrs_library_README.md")
REPORT = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_export_report.json"
PATH = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_path.jsonl"
SHADOW = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_shadow.jsonl"
NEAR = REPO_ROOT / "pipeline" / "openmc" / "results" / "beavrs_near.jsonl"

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
# A joint state goes into domain.jointChecked (where the summed tables count as checked) only if the summed model reproduces transport there
RHO_ERR_LIMIT = 1.0e-3        # 100 pcm, about four times a case's statistical error
SHAPE_ERR_LIMIT = 1.0         # in mean bins
ROD_INTERACTION_CAPABILITY = "point-kinetics/rod-interaction-v1"
ROD_SHADOW_CAPABILITY = "point-kinetics/rod-interaction-v2"
HELD_OUT_SEED = 1                                      # the seed of the path, shadow and near runs (the sweep's too)
SHADOW_KNOTS = (-0.01, -0.02, -0.03, -0.0385)          # the shadowing table's free knots (fractions): the protocol of the fifteenth fixes them; -3850 pcm is the deepest R among the fit cases
R_ABOVE = 1.0e-3                                       # +100 pcm: nothing above the reference is claimed (g held at 0 there)
FIT_CASES = ("J-W2", "J-W4", "J-W7")      # the combined states the rod interaction table is fitted to (and so never listed as checked)
S_ABOVE = 1.0e-3                          # +100 pcm: nothing above the reference is claimed (the table is zero there, assumed)
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

def build(rows: list[dict], core: dict, created: str | None = None, path_rows: list[dict] | None = None, model: str = "interaction",
          shadow_rows: list[dict] | None = None, shadow_knots: tuple[float, ...] = SHADOW_KNOTS) -> tuple[dict, dict[str, bytes], dict]:
    """model "interaction": the table of the fourteenth protocol (path_rows are held out). model "shadowing": the table of the fifteenth (path_rows are
    required and are fit data; shadow_rows are the held-out cases, or None for a library that says it was not checked)."""
    if model not in ("interaction", "shadowing"):
        raise ValueError(f"unknown model {model!r}")
    by = check_sweep(rows)
    if model == "shadowing":
        if path_rows is None:
            raise ValueError("the shadowing table is fitted to the nine path cases: path_rows are required")
        by_fit_path = check_path(path_rows)
        by_path = check_path(shadow_rows, {**shadow_cases(), **near_cases()}, "shadow", allow_subset=True) if shadow_rows is not None else {}
    else:
        if shadow_rows is not None:
            raise ValueError("shadow_rows belong to the shadowing model")
        by_fit_path = {}
        by_path = check_path(path_rows) if path_rows is not None else {}
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

    # the rod interaction table (docs/validation/m8-rod-interaction-protocol.md): a correction on the summed single-bank reactivities, fitted to the
    # combined transport cases and to nothing else
    def sum_rods(steps: dict) -> float:
        s = 0.0
        for b in BANKS:
            s += interp(rod_tables[b]["x"], rod_tables[b]["rho"], x_of(steps[b]))
        return s

    s_deepest = min(min(rod_tables[b]["rho"]) for b in BANKS)          # the deepest single-bank worth: one bank has nothing to interact with
    inter_pts = [{"a": 0.0, "rho": 0.0, "sigma": 0.0, "ref": True}, {"a": S_ABOVE, "rho": 0.0, "sigma": 0.0, "ref": False},
                 {"a": s_deepest, "rho": 0.0, "sigma": 0.0, "ref": False}]
    for c in FIT_CASES:
        d, s_ = rel(c)
        s_k = sum_rods(by[c]["steps"])
        inter_pts.append({"a": s_k, "rho": d - s_k, "sigma": s_, "ref": False, "case": c})
    inter_t = fit_correction(inter_pts) if model == "interaction" else None

    def worths_of(steps: dict) -> list[float]:
        return [interp(rod_tables[b]["x"], rod_tables[b]["rho"], x_of(steps[b])) for b in BANKS]

    shadow_t = None
    if model == "shadowing":
        fit_cases = []
        for c, row in [(c, by[c]) for c in FIT_CASES] + list(by_fit_path.items()):
            ws_c = worths_of(row["steps"])
            r_c, s_c = rho_of(row)
            fit_cases.append({"case": c, "ws": ws_c, "y": r_c - rho_ref - math.fsum(ws_c), "sigma": s_c})
        shadow_t = fit_shadowing(fit_cases, shadow_knots)

    def shadow_corr(steps: dict) -> float:
        ws_c = worths_of(steps)
        s_c = math.fsum(ws_c)
        return math.fsum(w * interp(shadow_t["a"], shadow_t["rho"], s_c - w) for w in ws_c if w != 0.0)

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

    def shape_of_row(row: dict) -> list[float]:
        return normalized(assembly_shape(row, core))

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
    tables = {"rods": {rid(b): rod_tables[b] for b in BANKS}, "fuel": fuel_t, "cool": cool_t, "boron": boron_t, **({"rodInteraction": inter_t} if model == "interaction" else {"rodShadowing": shadow_t})}

    def predict(row: dict, with_table: bool = True) -> tuple[float, list[float]]:
        rho = rho_ref
        shape = list(base_f32)
        for b in BANKS:
            x = x_of(row["steps"][b])
            t = rod_tables[b]
            rho += interp(t["x"], t["rho"], x)
            sl = interp_slice(t["x"], delta64[rid(b)], x)
            shape = [s + d for s, d in zip(shape, sl)]
        if with_table:
            rho += interp(inter_t["a"], inter_t["rho"], sum_rods(row["steps"])) if model == "interaction" else shadow_corr(row["steps"])
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
        check[r["case"]] = {"rhoCase": rho_c, "rhoPred": rho_p, "rhoErr": abs(rho_p - rho_c), "rhoSigma": sig_c, "maxShapeErr": err,
                            "negativeBins": sum(1 for v in shape_p if v < -1e-6), "minBin": min(shape_p),
                            "rhoPredNoTable": predict(r, with_table=False)[0], "sumRods": sum_rods(r["steps"]), "usedInFit": r["case"] in FIT_CASES}

    # the held-out path cases (not in the fit): label the library's error, and list the good ones as checked states
    joint, path_report = [], {}
    for cid, r in by_path.items():
        conv = path_convergence(r)
        if not conv["converged"]:
            path_report[cid] = {"computed": False, "reason": f"unconverged (drift z {conv['z']:.2f}); not labelled and not listed as checked"}
            continue
        rho_p, shape_p = predict(r)
        rho_c, sig_c = rho_of(r)
        lim = max(RHO_ERR_LIMIT, 3.0 * sig_c)
        diff = rho_p - rho_c
        label_ = "good" if abs(diff) <= lim else "plausible" if abs(diff) <= 2.0 * lim else "fails"
        path_report[cid] = {"computed": True, "driftZ": conv["z"], "rhoCase": rho_c, "rhoPred": rho_p, "difference": diff, "rhoSigma": sig_c, "limit": lim, "label": label_,
                            "differenceNoTable": predict(r, with_table=False)[0] - rho_c, "sumRods": sum_rods(r["steps"]),
                            "maxShapeErr": shape_err(shape_p, shape_of_row(r)), "negativeBins": sum(1 for v in shape_p if v < -1e-6)}
        if label_ == "good":
            joint.append({"rods": {rid(b): x_of(r["steps"][b]) for b in BANKS}, "maxShapeErr": path_report[cid]["maxShapeErr"], "rhoErr": abs(diff)})

    held_given = (path_rows is not None) if model == "interaction" else (shadow_rows is not None)
    if not held_given:
        checked_note = "NOT checked against held-out transport cases: none was given to the exporter, domain.jointChecked is empty."
    else:
        if model == "shadowing":                                 # a case the run did not deliver is reported as not computed, and enters no decision
            for cid in shadow_cases():
                path_report.setdefault(cid, {"computed": False, "reason": "missing: not in the held-out file"})
            if any(c in near_cases() for c in by_path):           # near cases were delivered: any planned one that is absent is reported, not dropped
                for cid in near_cases():
                    path_report.setdefault(cid, {"computed": False, "reason": "missing: not in the held-out file"})
        n_good = sum(1 for e in path_report.values() if e.get("label") == "good")
        n_comp = sum(1 for e in path_report.values() if e.get("computed"))
        at = sorted({r["boron"] for r in by_path.values() if r["boron"] != b_ref})
        boron_note = (f" The checks at {', '.join(f'{b:g}' for b in at)} ppm hold at that boron only (domain.jointChecked lists rod positions, not boron; "
                      "the boron x bank interaction is not in the model).") if at else ""
        checked_note = f"Checked against {n_comp} held-out cases: {n_good} within the limit (listed in domain.jointChecked)." + boron_note
    if model == "shadowing":
        rod_note = ("Several banks in: each bank's worth is scaled by 1 + g(the summed single-bank reactivity of the other banks) (reactivity.rodShadowing, capability rod-interaction-v2, "
                    "fitted to the three combined sweep cases and the nine path cases of the fourteenth protocol, and to nothing else); it sees only that sum, not which banks or where "
                    "in the core, so it is valid only along the states it was checked on (docs/validation/m8-rod-shadowing-protocol.md). ")
    else:
        rod_note = ("Several banks in: the single-bank worths are summed and a correction table on that sum (reactivity.rodInteraction, fitted to the transport cases with banks C and D, "
                    "A to D, and D to SC in, and to nothing else) accounts for the banks being worth more together; it is valid along the benchmark insertion order "
                    "(D, C, B, A, SE, SD, SC) and nowhere else claimed (docs/validation/m8-rod-interaction-protocol.md). ")

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
        "capabilities": ["point-kinetics/lumped-thermal-v1", "point-kinetics/boron-v1", ROD_INTERACTION_CAPABILITY if model == "interaction" else ROD_SHADOW_CAPABILITY],
        "provenance": {
            "generator": "pipeline.library.export_beavrs", "transportCode": f"OpenMC {ref.get('openmc', '')}".strip(),
            "nuclearData": "ENDF/B-VIII.0", "model": "BEAVRS 3D full core, hot zero power (mit-crpg/BEAVRS, MIT licence), 45 cases of pipeline/openmc/beavrs_cases.py",
            "created": created,
            "notes": ("Zero-power physics only. Reactivity tables, kinetics, shapes and boron worth come from the transport sweep; the plant (rod speed, scram, "
                      "thermal masses, heat transfer, instruments, trips) is assumed and labelled so. Isothermal temperature coefficient: the transport model is "
                      "1.6 to 2.0 pcm/F too negative against the benchmark measurement (docs/validation/m8-beavrs-hzp-results.md), so temperature feedback is NOT validated. "
                      "Xenon worth is zero (not computed); no decay heat; no pressure. The shape of the power does not depend on coolant temperature or boron. "
                      + rod_note + checked_note),
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
            **({"rodInteraction": {"S": inter_t["a"], "rho": inter_t["rho"], "unc": inter_t["unc"], "interp": "linear", "outOfRange": "clamp-and-flag", "source": "transport"}}
               if model == "interaction" else
               {"rodShadowing": {"R": shadow_t["a"], "g": shadow_t["rho"], "unc": shadow_t["unc"], "interp": "linear", "outOfRange": "clamp-and-flag", "source": "transport"}}),
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
        "pathCases": path_report if model == "interaction" else {}, "heldOutCases": path_report if model == "shadowing" else {}, "model": model,
        "negativeShapeBins": sum(1 for v in base_f32 if v <= 0),
        "limits": {"rhoErr": RHO_ERR_LIMIT, "maxShapeErr": SHAPE_ERR_LIMIT},
    }
    return m, blobs, report


def fit_correction(points: list[dict]) -> dict:
    """The rod interaction table: points a (S), rho (correction), sigma, ref. Weighted isotonic fit, non-decreasing in S (the more the rods are in, the more
    negative the correction), anchors (sigma 0) held at their value; exactly 0 at the reference point."""
    pts = sorted(points, key=lambda p: p["a"])
    xs = [p["a"] for p in pts]
    if any(b <= a for a, b in zip(xs, xs[1:])):
        raise ValueError(f"the rod interaction points are not distinct: {xs}")
    ws = [1e12 if p["sigma"] == 0.0 else 1.0 / (p["sigma"] ** 2) for p in pts]
    fit = isotonic(xs, [p["rho"] for p in pts], ws)
    out = [0.0 if p["sigma"] == 0.0 else v for p, v in zip(pts, fit)]
    if any(b < a - 1e-15 for a, b in zip(out, out[1:])):         # holding the anchors at zero must not undo the fit
        raise ValueError(f"the rod interaction table is not monotone after the anchors are held: {out}")
    return {"a": xs, "rho": out, "unc": [p["sigma"] for p in pts], "raw": [p["rho"] for p in pts]}


def fit_shadowing(cases: list[dict], knots: tuple[float, ...] = SHADOW_KNOTS) -> dict:
    """The rod shadowing table g(R) (docs/validation/m8-rod-shadowing-protocol.md): cases carry `ws` (the single-rod reactivities, fractions), `y` (the
    transport reactivity minus the reference minus the sum of ws) and `sigma`. Model y = sum_i w_i g(S - w_i), g piecewise linear on the axis
    SHADOW_KNOTS (free values) plus 0 and R_ABOVE (held at 0); weighted least squares, weights 1/sigma^2, unconstrained in sign."""
    axis = sorted([0.0, R_ABOVE] + list(knots))
    free = [k for k in axis if k < 0.0]
    n = len(free)

    def basis(r: float) -> list[float]:
        return [interp(axis, [1.0 if a == f else 0.0 for a in axis], r) for f in free]

    rows, ys, ws = [], [], []
    for c in cases:
        s = math.fsum(c["ws"])
        row = [0.0] * n
        for w in c["ws"]:
            if w != 0.0:
                row = [a + w * b for a, b in zip(row, basis(s - w))]
        rows.append(row)
        ys.append(c["y"])
        ws.append(1.0 / (c["sigma"] ** 2))
    ata = [[math.fsum(w * r[i] * r[j] for r, w in zip(rows, ws)) for j in range(n)] for i in range(n)]
    atb = [math.fsum(w * r[i] * y for r, y, w in zip(rows, ys, ws)) for i in range(n)]
    inv = _invert(ata)
    g = [math.fsum(inv[i][j] * atb[j] for j in range(n)) for i in range(n)]
    unc = [math.sqrt(inv[i][i]) for i in range(n)]
    gv = dict(zip(free, g))
    uv = dict(zip(free, unc))
    return {"a": axis, "rho": [gv.get(a, 0.0) for a in axis], "unc": [uv.get(a, 0.0) for a in axis],
            "residuals": [y - math.fsum(r[i] * g[i] for i in range(n)) for r, y in zip(rows, ys)], "fitCases": [c.get("case") for c in cases]}


def _invert(m: list[list[float]]) -> list[list[float]]:
    """Gauss-Jordan inverse with partial pivoting; refuses a singular matrix (the fit cases cannot determine every knot)."""
    n = len(m)
    a = [list(r) + [1.0 if i == j else 0.0 for j in range(n)] for i, r in enumerate(m)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-12 * max(abs(m[i][i]) for i in range(n)):
            raise ValueError("the shadowing fit is singular: the fit cases do not determine every knot")
        a[c], a[p] = a[p], a[c]
        piv = a[c][c]
        a[c] = [v / piv for v in a[c]]
        for r in range(n):
            if r != c and a[r][c] != 0.0:
                f = a[r][c]
                a[r] = [v - f * u for v, u in zip(a[r], a[c])]
    return [r[n:] for r in a]


def path_convergence(row: dict) -> dict:
    """The drift check of the protocols for a held-out path case (300 batches): the mean k of batches 101 to 200 and of 201 to 300 agree within 2 standard
    errors of their difference (batch values taken as independent)."""
    n = row["batches"]
    kb = row.get("kBatches")
    if n != 300 or not isinstance(kb, list) or len(kb) != n:
        raise ValueError(f"path case {row['case']}: the drift check needs 300 batches and one k per batch")

    def mean_se(xs):
        m = sum(xs) / len(xs)
        return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1) / len(xs))

    m1, s1 = mean_se(kb[100:200])
    m2, s2 = mean_se(kb[200:300])
    den = math.hypot(s1, s2)
    z = abs(m1 - m2) / den if den > 0 else (0.0 if m1 == m2 else math.inf)
    return {"z": z, "converged": z <= 2.0}


def check_path(rows: list[dict], plan: dict | None = None, name: str = "path", allow_subset: bool = False) -> dict[str, dict]:
    """The path rows must be exactly the cases of the plan (default: the nine of pipeline/openmc/beavrs_cases.path_cases()), once each, with the planned settings."""
    ids = [r["case"] for r in rows]
    dup = sorted({c for c in ids if ids.count(c) > 1})
    if dup:
        raise ValueError(f"duplicate {name} cases {dup}")
    plan = plan if plan is not None else path_cases()
    if set(ids) - set(plan) or (not allow_subset and set(ids) != set(plan)):
        raise ValueError(f"the {name} cases do not match the plan: missing {sorted(set(plan) - set(ids))}, unexpected {sorted(set(ids) - set(plan))}")
    for r in rows:
        want = plan[r["case"]]
        for key in ("steps", "boron", "tFuel", "tWater", "particles", "batches", "inactive", "ifp"):
            if r.get(key) != want[key]:
                raise ValueError(f"{name} case {r['case']}: {key} is {r.get(key)!r}, the plan says {want[key]!r}")
        if r.get("seed") != HELD_OUT_SEED:                      # the protocols fix seed 1 and the BEAVRS commit for these runs
            raise ValueError(f"{name} case {r['case']}: seed is {r.get('seed')!r}, the protocols fix {HELD_OUT_SEED}")
        if r.get("beavrsHead") != BEAVRS_HEAD:
            raise ValueError(f"{name} case {r['case']}: the BEAVRS commit is {r.get('beavrsHead')!r}, the protocols fix {BEAVRS_HEAD!r}")
    return {r["case"]: r for r in rows}


def check_sweep(rows: list[dict]) -> dict[str, dict]:
    """The rows must be exactly the plan of pipeline/openmc/beavrs_cases.py: unique case ids, and each case's recorded settings equal to the plan's."""
    ids = [r["case"] for r in rows]
    dup = sorted({c for c in ids if ids.count(c) > 1})
    if dup:
        raise ValueError(f"duplicate sweep cases {dup}")
    plan = sweep_cases()
    if set(ids) != set(plan):
        raise ValueError(f"the sweep does not match the plan: missing {sorted(set(plan) - set(ids))}, unexpected {sorted(set(ids) - set(plan))}")
    for r in rows:
        want = plan[r["case"]]
        for key in ("steps", "boron", "tFuel", "tWater", "particles", "batches", "inactive", "ifp"):
            if r.get(key) != want[key]:
                raise ValueError(f"case {r['case']}: {key} is {r.get(key)!r} in the sweep, the plan says {want[key]!r}")
    return {r["case"]: r for r in rows}


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


def write_library(folder: Path, m: dict, blobs: dict[str, bytes], validate: bool = False) -> None:
    """Write next to the target, validate if asked, then replace the target: a failed write or an invalid library leaves the old one in place."""
    stage = folder.with_name(folder.name + ".new")
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "arrays").mkdir(parents=True)
    try:
        for name, data in blobs.items():
            (stage / name).write_bytes(data)
        (stage / "manifest.json").write_bytes((json.dumps(m, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        if validate:
            issues = validate_library(stage)
            if issues:
                raise ValueError("the new library does not validate: " + "; ".join(f"{i.code} {i.path}" for i in issues[:5]))
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    backup = folder.with_name(folder.name + ".old")
    if backup.exists():
        shutil.rmtree(backup)
    if folder.exists():
        folder.rename(backup)
    try:
        stage.rename(folder)
    except BaseException:
        if backup.exists():
            backup.rename(folder)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sweep", type=Path, default=SWEEP)
    ap.add_argument("--core", type=Path, default=CORE)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--report", type=Path, default=REPORT)
    ap.add_argument("--model", choices=("shadowing", "interaction"), default="shadowing",
                    help="rod-interaction-v2 (the fifteenth protocol, default) or rod-interaction-v1 (the fourteenth)")
    ap.add_argument("--path", type=Path, default=PATH, help="the nine path cases (beavrs_path.jsonl): fit data for shadowing, held-out for interaction")
    ap.add_argument("--no-path", action="store_true", help="interaction only: export without held-out path cases (jointChecked stays empty and the notes say so)")
    ap.add_argument("--shadow", type=Path, default=SHADOW, help="shadowing only: the 13 held-out cases (beavrs_shadow.jsonl)")
    ap.add_argument("--near", type=Path, default=NEAR, help="shadowing only: the 7 near-critical held-out cases of the sixteenth protocol (beavrs_near.jsonl), used if the file exists")
    ap.add_argument("--no-shadow", action="store_true", help="shadowing only: export without the held-out cases (jointChecked stays empty and the notes say so)")
    args = ap.parse_args(argv)
    rows = [json.loads(line) for line in args.sweep.read_text(encoding="utf-8").splitlines() if line.strip()]
    core = json.loads(args.core.read_text(encoding="utf-8"))
    def read_rows(p: Path) -> list[dict]:
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    shadow_rows = None
    if args.model == "shadowing":
        if args.no_path:
            raise SystemExit("--no-path belongs to the interaction model: the shadowing table is fitted to the nine path cases")
        if not args.path.exists():
            raise SystemExit(f"the path file {args.path} does not exist: the shadowing table is fitted to it (beavrs_sweep --family path)")
        path_rows = read_rows(args.path)
        if not args.no_shadow:
            if not args.shadow.exists():
                raise SystemExit(f"the held-out file {args.shadow} does not exist: run the 13 cases (beavrs_sweep --family shadow) or pass --no-shadow")
            shadow_rows = read_rows(args.shadow)
            if args.near.exists():
                shadow_rows += read_rows(args.near)
    elif args.no_path:
        path_rows = None
    elif not args.path.exists():
        raise SystemExit(f"the held-out path file {args.path} does not exist: run the nine path cases (beavrs_sweep --family path) or pass --no-path")
    else:
        path_rows = read_rows(args.path)
    m, blobs, report = build(rows, core, path_rows=path_rows, model=args.model, shadow_rows=shadow_rows)
    blobs["README.md"] = README.read_bytes()          # the library folder is rebuilt from scratch, so its README is part of the export
    write_library(args.out, m, blobs, validate=True)
    args.report.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(m['shapes']['bins']['elements'])} assemblies, {len(m['reactivity']['rods'])} rods); report {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
