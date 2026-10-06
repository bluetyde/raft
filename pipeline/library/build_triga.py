"""
Build the experimental JSI TRIGA Mark II benchmark library.

Generates a fully valid library directory in `libraries/triga-jsi/`
conforming to `docs/library-format.md` (v0.1.0) and passing `pipeline.library.validate`.
Uses the verified physical, kinetic, and thermal parameters from
`validation/data/triga-jsi/parameters.json` with status "experimental".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "libraries" / "triga-jsi"

# Source labels (docs/library-format.md section 3). "cited:<id>" means the value was checked in that publication.
# None of the values below has been checked against the benchmark, Simnad or Svajger yet (review 2026-09-26,
# docs/reviews/2026-09-26-m1-go-review.md), so they are "assumed" until the parameter check (task C2) confirms them.
# The delayed-group decay constants are Keepin's standard U-235 thermal values and are cited as such.
# C2 (2026-09-27) checked the kinetics, fuel cp(T), fuel alpha(T) and pulse-rod ejection time against
# Vavtar & Snoj, EPJ Web Conf. 247, 08006 (2021) (CC-BY 4.0; JSI group), and cites them as "cited:vavtar2021".
# Everything else stays "assumed".
ASSUMED = "assumed"
CITED_KEEPIN = "cited:keepin1965"
CITED_VAVTAR = "cited:vavtar2021"
CITED_SVAJGER = "cited:svajger2024"

# Run-3 variants (docs/validation/m1-run3-protocol.md). Fuel mass 2.363 kg/element (svajger2024 Table 10, geometry check);
# element counts from the database core maps (58 and 64; first counted as 59 and 65, which included the map's date year). The fuel reactivity table is svajger2024 Table 2 (k-infinity of standard fuel,
# Serpent, ENDF/B-VII.0): delta-rho in pcm at 294..800 K, with 294 K used as the 293.15 K reference; beyond 800 K alpha is
# held at -9.81 pcm/K. The "paper" variant reproduces svajger2024 Table 10's inputs for the code-to-code check.
MASS_PER_ELEMENT = 2.363
TABLE2_T = [293.15, 400.0, 500.0, 600.0, 700.0, 800.0, 1200.0]
TABLE2_RHO_PCM = [0.0, -694.0, -1612.0, -2583.0, -3551.0, -4533.0, -4533.0 - 9.81 * 400.0]
VARIANTS = {
    "242": {"id": "triga-jsi-242", "name": "JSI TRIGA Mark II, core 242 (58 elements)", "mass": 58 * MASS_PER_ELEMENT, "fuel": "table2"},
    "246": {"id": "triga-jsi-246", "name": "JSI TRIGA Mark II, core 246 (64 elements)", "mass": 64 * MASS_PER_ELEMENT, "fuel": "table2"},
    "134": {"id": "triga-jsi-134", "name": "JSI TRIGA Mark II, core 134 (45 elements, fresh; 1994 benchmark)", "mass": 45 * MASS_PER_ELEMENT, "fuel": "table2"},
    "paper": {"id": "triga-jsi-paper", "name": "JSI TRIGA Mark II, svajger2024 Table 10 inputs", "mass": 59 * 2.36, "fuel": "paper"},
}

T_REF = 293.15  # K (20 °C)
PITCH = 4.3  # cm
CORE_H = 38.1  # cm, active fuel height
R_EXT = 28.0  # cm, extrapolated core radius
H_EXT = 25.0  # cm, extrapolated axial half-height
AXIAL_EDGES = [-19.05, -15.24, -11.43, -7.62, -3.81, 0.0, 3.81, 7.62, 11.43, 15.24, 19.05]
ROD_X = [i / 10.0 for i in range(11)]
TEMP_GRID = [T_REF, 350.0, 400.0, 500.0, 600.0, 800.0, 1000.0, 1200.0]

# JSI TRIGA Mark II rod configuration
# Rod ID: (Name, ring location, total worth in Delta k/k, pulseCapable, travelTime)
# 1 $ = 700 pcm = 0.0070 Delta k/k
ROD_SPECS = {
    "transient": ("Transient (Pulse) rod", "C1", 2.20 * 0.0070, True, 0.08),  # 2.20 $
    "safety": ("Safety rod", "C5", 3.10 * 0.0070, False, 0.35),               # 3.10 $
    "shim": ("Compensating (Shim) rod", "D8", 2.80 * 0.0070, False, 0.35),    # 2.80 $
    "regulating": ("Regulating rod", "E12", 0.85 * 0.0070, False, None),       # 0.85 $
}

# 6 delayed precursor groups. Betas: Vavtar & Snoj 2021, Table 1 (sum 0.00699891; beta_eff = 0.007 in the text).
GROUP_BETAS = [0.00023097, 0.00153278, 0.00137180, 0.00276451, 0.00080489, 0.00029396]
GROUP_LAMBDAS = [0.0124, 0.0305, 0.1110, 0.3010, 1.1400, 3.0100]


# Fuel specific heat, standard 12 wt% U element: C(T) = 333 + 0.678 (T[K] - 274.15) J/(kg K)
# (Vavtar & Snoj 2021, eq. 1.8, citing Simnad, GA E-177-833, 1980).
def fuel_cp(T: float) -> float:
    return 333.0 + 0.678 * (T - 274.15)


# |alpha_f| of fresh standard fuel, (T in K, 1e-5 per K), read by eye from Vavtar & Snoj 2021, Fig. 1
# (after PULSTRI, Ravnik et al.). Precision about +-0.5e-5 per K. Beyond the last point it is held constant.
ALPHA_FUEL_POINTS = [(293.15, 6.2), (373.15, 7.3), (473.15, 8.3), (573.15, 8.9), (673.15, 8.8),
                     (873.15, 8.4), (1073.15, 8.0), (1273.15, 7.7)]


def fuel_alpha(T: float) -> float:
    """alpha_f(T) in (Delta k/k)/K (negative), linear between the digitized points."""
    pts = ALPHA_FUEL_POINTS
    if T <= pts[0][0]:
        return -pts[0][1] * 1e-5
    for (t0, a0), (t1, a1) in zip(pts, pts[1:]):
        if T <= t1:
            return -(a0 + (a1 - a0) * (T - t0) / (t1 - t0)) * 1e-5
    return -pts[-1][1] * 1e-5


def fuel_rho(T: float, steps: int = 2000) -> float:
    """rho_fuel(T) = integral of alpha_f from T_REF to T (trapezoid rule, fine enough for a piecewise-linear alpha)."""
    h = (T - T_REF) / steps
    total = 0.0
    for i in range(steps):
        a, b = T_REF + i * h, T_REF + (i + 1) * h
        total += 0.5 * (fuel_alpha(a) + fuel_alpha(b)) * h
    return total


def S(value: float, source: str, **extra) -> dict:
    return {"value": value, "source": source, **extra}


def triga_hex_positions() -> Dict[str, Tuple[float, float]]:
    """Generate positions for hexagonal rings A, B, C, D, E."""
    pos = {"A1": (0.0, 0.0)}
    # Ring B: 6 positions
    for k in range(6):
        a = math.radians(60 * k)
        pos[f"B{k + 1}"] = (round(PITCH * math.cos(a), 4), round(PITCH * math.sin(a), 4))
    # Ring C: 12 positions
    for k in range(12):
        if k % 2 == 0:
            a, r = math.radians(30 * k), 2 * PITCH
        else:
            a, r = math.radians(30 * k), math.sqrt(3) * PITCH
        pos[f"C{k + 1}"] = (round(r * math.cos(a), 4), round(r * math.sin(a), 4))
    # Ring D: 18 positions
    for k in range(18):
        angle = math.radians(20 * k)
        r = 3.0 * PITCH
        pos[f"D{k + 1}"] = (round(r * math.cos(angle), 4), round(r * math.sin(angle), 4))
    # Ring E: 24 positions
    for k in range(24):
        angle = math.radians(15 * k)
        r = 4.0 * PITCH
        pos[f"E{k + 1}"] = (round(r * math.cos(angle), 4), round(r * math.sin(angle), 4))
    return pos


def rod_worth(total_worth: float, x: float) -> float:
    """Standard integral rod worth S-curve: W(x) = W_tot * (x - sin(2*pi*x)/(2*pi))."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return total_worth
    return total_worth * (x - math.sin(2.0 * math.pi * x) / (2.0 * math.pi))


def pack_f32(values: List[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def descriptor(file: str, data: bytes, shape: List[int]) -> dict:
    return {
        "file": file,
        "dtype": "float32",
        "byteOrder": "little",
        "shape": shape,
        "order": "C",
        "offset": 0,
        "byteLength": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def normalized(v: List[float]) -> List[float]:
    s = sum(v)
    return [a / s for a in v]


def raw_shape(elements: List[str], pos: Dict[str, Tuple[float, float]],
              rod_pos: Dict[str, str], rod_x: Dict[str, float], T: float,
              mids: List[float], widths: List[float]) -> List[float]:
    """Unnormalized 3D power shape: radial cosine x axial cosine with rod absorber depression."""
    flat = 1.0 - 0.12 * (T - T_REF) / (1200.0 - T_REF)
    out = []
    for e in elements:
        x, y = pos[e]
        r = math.hypot(x, y)
        radial = max(0.01, math.cos(math.pi * r / (2.0 * R_EXT)))
        for z, dz in zip(mids, widths):
            axial = max(0.01, math.cos(math.pi * z / (2.0 * H_EXT)))
            v = radial * axial
            for rid, rp in rod_pos.items():
                if rp in pos:
                    rx, ry = pos[rp]
                    d2 = (x - rx) ** 2 + (y - ry) ** 2
                    tip = AXIAL_EDGES[0] + CORE_H * rod_x[rid]
                    covered = 1.0 / (1.0 + math.exp(-(z - tip) / 2.0))
                    v *= 1.0 - 0.35 * math.exp(-d2 / 60.0) * covered
            out.append((v ** flat) * dz)
    return out


def build_library(out_dir: Path, variant: str | None = None) -> dict:
    """Build the complete JSI TRIGA library files in out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    arrays_dir = out_dir / "arrays"
    arrays_dir.mkdir(parents=True, exist_ok=True)

    pos = triga_hex_positions()
    rod_pos = {rid: spec[1] for rid, spec in ROD_SPECS.items()}
    elements = [e for e in sorted(pos.keys()) if e != "A1" and e not in rod_pos.values()]
    mids = [(a + b) / 2.0 for a, b in zip(AXIAL_EDGES, AXIAL_EDGES[1:])]
    widths = [b - a for a, b in zip(AXIAL_EDGES, AXIAL_EDGES[1:])]

    all_in = {rid: 0.0 for rid in ROD_SPECS}
    base = normalized(raw_shape(elements, pos, rod_pos, all_in, T_REF, mids, widths))

    rod_deltas = {}
    for rid in ROD_SPECS:
        slices = []
        for x in ROD_X:
            if x == 0.0:
                slices.extend([0.0] * len(base))
                continue
            state = dict(all_in, **{rid: x})
            sh = normalized(raw_shape(elements, pos, rod_pos, state, T_REF, mids, widths))
            slices.extend(a - b for a, b in zip(sh, base))
        rod_deltas[rid] = slices

    temp_deltas = []
    for T in TEMP_GRID:
        if T == T_REF:
            temp_deltas.extend([0.0] * len(base))
            continue
        sh = normalized(raw_shape(elements, pos, rod_pos, all_in, T, mids, widths))
        temp_deltas.extend(a - b for a, b in zip(sh, base))

    r_meat = 1.815  # cm, fuel meat radius (diameter 3.63 cm)
    volumes = [math.pi * (r_meat ** 2) * dz for _ in elements for dz in widths]
    base_unc = [0.01 + 0.015 * (1.0 - b / max(base)) for b in base]

    E, A = len(elements), len(AXIAL_EDGES) - 1

    # Pack binary arrays
    blobs: Dict[str, bytes] = {
        "arrays/base.f32": pack_f32(base),
        "arrays/base_unc.f32": pack_f32(base_unc),
        "arrays/volumes.f32": pack_f32(volumes),
        "arrays/temp_delta.f32": pack_f32(temp_deltas),
    }
    for rid in ROD_SPECS:
        blobs[f"arrays/rod_{rid}.f32"] = pack_f32(rod_deltas[rid])

    for rel_path, data in blobs.items():
        with open(out_dir / rel_path, "wb") as f:
            f.write(data)

    arrays = {
        "base": descriptor("arrays/base.f32", blobs["arrays/base.f32"], [E, A]),
        "baseUnc": descriptor("arrays/base_unc.f32", blobs["arrays/base_unc.f32"], [E, A]),
        "volumes": descriptor("arrays/volumes.f32", blobs["arrays/volumes.f32"], [E, A]),
        "tempDelta": descriptor("arrays/temp_delta.f32", blobs["arrays/temp_delta.f32"], [len(TEMP_GRID), E, A]),
    }
    for rid in ROD_SPECS:
        f = f"arrays/rod_{rid}.f32"
        arrays[f"rod_{rid}"] = descriptor(f, blobs[f], [len(ROD_X), E, A])

    # Rod objects
    rods = []
    for rid, (name, _, total, pulse_cap, travel_time) in ROD_SPECS.items():
        worth_pts = [round(rod_worth(total, x), 12) for x in ROD_X]
        rod_obj = {
            "id": rid,
            "name": name,
            "travelCm": CORE_H,
            "speed": 0.02,
            "pulseCapable": pulse_cap,
            "worth": {
                "x": ROD_X,
                "rho": worth_pts,
                "interp": "linear",
                "outOfRange": "clamp-and-flag",
                "source": ASSUMED,
            },
            "scram": {
                "t": [0.0, 0.05, 0.15, 0.25, 0.35],
                "x": [1.0, 0.95, 0.65, 0.20, 0.0],
                "source": ASSUMED,
            },
        }
        if pulse_cap:
            rod_obj["fireTime"] = travel_time or 0.08
        rods.append(rod_obj)

    cp_vals = [round(fuel_cp(T), 4) for T in TEMP_GRID]
    rho_fuel = [round(fuel_rho(T), 12) for T in TEMP_GRID]
    fuel_T, fuel_src, cp_src = TEMP_GRID, CITED_VAVTAR, CITED_VAVTAR
    mass = S(84.0, ASSUMED)
    v = VARIANTS[variant] if variant else None
    if v:
        mass = S(round(v["mass"], 4), CITED_SVAJGER)
        if v["fuel"] == "table2":
            fuel_T, fuel_src = TABLE2_T, CITED_SVAJGER
            rho_fuel = [round(r * 1e-5, 12) for r in TABLE2_RHO_PCM]
        else:  # "paper": alpha = -10 pcm/K constant, C = 341.6 J/(kg K) constant
            fuel_src = cp_src = CITED_SVAJGER
            rho_fuel = [round(-10e-5 * (T - T_REF), 12) for T in TEMP_GRID]
            cp_vals = [341.6 for _ in TEMP_GRID]

    # Geometry primitives
    geometry = [
        {"type": "cylinder", "center": [0, 0, 0], "radius": 100.0, "height": 625.0, "material": "water"},
        {"type": "annulus", "center": [0, 0, 0], "rInner": 22.0, "radius": 55.0, "height": 55.0, "material": "graphite"},
        {"type": "cylinder", "center": [0, 0, 0], "radius": 1.9, "height": CORE_H, "material": "aluminum"},
    ]
    for e in elements:
        x, y = pos[e]
        geometry.append({"type": "cylinder", "center": [x, y, 0.0], "radius": 1.815, "height": CORE_H, "material": "fuel", "element": e})
        geometry.append({"type": "annulus", "center": [x, y, 0.0], "rInner": 1.815, "radius": 1.866, "height": CORE_H, "material": "steel", "element": e})
    for rid, rp in rod_pos.items():
        if rp in pos:
            x, y = pos[rp]
            geometry.append({"type": "cylinder", "center": [x, y, 0.0], "radius": 1.6, "height": CORE_H, "material": "b4c", "rod": rid})

    manifest = {
        "schemaVersion": "0.1.0",
        "id": v["id"] if v else "triga-jsi",
        "name": v["name"] if v else "JSI TRIGA Mark II (Ljubljana) Benchmark Core",
        "status": "experimental",
        "capabilities": ["point-kinetics/lumped-thermal-v1"],
        "provenance": {
            "generator": "pipeline.library.build_triga",
            "created": "2026-09-26",
            "notes": ("Experimental TRIGA-like model. Kinetics (betas, generation time), fuel cp(T), fuel alpha(T) and the "
                      "pulse-rod ejection time are cited from Vavtar & Snoj 2021 (checked 2026-09-27, task C2); alpha(T) is "
                      "read from a figure (+-0.5e-5/K). Everything else is 'assumed'. Geometry and power shapes are "
                      "illustrative, not the benchmark core. See docs/reviews/2026-09-26-m1-go-review.md."),
            "sources": [
                {"id": "keepin1965", "cite": "G. R. Keepin, Physics of Nuclear Kinetics, Addison-Wesley (1965): U-235 thermal delayed-neutron groups"},
                {"id": "icsbep", "cite": "ICSBEP Benchmark IEU-COMP-THERM-003 (OECD-NEA, 2007)"},
                {"id": "vavtar2021", "cite": "I. Vavtar, L. Snoj, Evaluation of approximations in reactor pulse, EPJ Web of Conferences 247, 08006 (2021), doi:10.1051/epjconf/202124708006"},
                {"id": "svajger2024", "cite": "I. Švajger, D. Čalič, A. Pungerčič, A. Trkov, L. Snoj, Evaluation of reactor pulse experiments, Nuclear Engineering and Technology 56 (2024) 1165–1203, doi:10.1016/j.net.2023.11.021 (not yet checked)"},
            ],
        },
        "reference": {
            "rods": {rid: 0.0 for rid in ROD_SPECS},
            "Tfuel": S(T_REF, ASSUMED),
            "Tcoolant": S(T_REF, ASSUMED),
            "xenon": S(0.0, ASSUMED),
            "rho": S(-0.0450, ASSUMED),  # All rods inserted shutdown margin
            "calibration": None,
        },
        "kinetics": {
            "beta": {"values": GROUP_BETAS, "source": CITED_VAVTAR},
            "lambda": {"values": GROUP_LAMBDAS, "source": CITED_KEEPIN},
            "genTime": S(4.0e-5, CITED_VAVTAR),  # prompt neutron lifetime l = 4e-5 s; Lambda = l/k = l at critical
            "extSource": S(0.5, ASSUMED),
        },
        "reactivity": {
            "rods": rods,
            "fuelTemp": {
                "T": fuel_T,
                "rho": rho_fuel,
                "interp": "linear",
                "outOfRange": "clamp-and-flag",
                "source": fuel_src,
            },
            "coolantTemp": {
                "T": [283.15, T_REF, 313.15, 333.15, 353.15],
                "rho": [round(-3.5e-5 * (T - T_REF), 12) for T in [283.15, T_REF, 313.15, 333.15, 353.15]],
                "interp": "linear",
                "outOfRange": "clamp-and-flag",
                "source": ASSUMED,
            },
            "xenon": {
                "N": [0.0, 1.0e20, 2.0e20, 4.0e20],
                "rho": [0.0, -0.0015, -0.0030, -0.0060],
                "interp": "linear",
                "outOfRange": "extrapolate-and-flag",
                "source": ASSUMED,
            },
        },
        "thermal": {
            "fuel": {
                "mass": mass,
                "cp": {
                    "T": TEMP_GRID,
                    "c": cp_vals,
                    "interp": "linear",
                    "outOfRange": "clamp-and-flag",
                    "source": cp_src,
                },
            },
            "coolant": {"mass": S(20000.0, ASSUMED), "cp": S(4184.0, ASSUMED)},
            "hA": S(3000.0, ASSUMED),
            "heatExchanger": {"UA": S(10000.0, ASSUMED), "sinkTemp": S(T_REF, ASSUMED), "pump": "primary"},
            "deposition": {"fuelFraction": S(1.0, ASSUMED)},
        },
        "poisons": {
            "fluxPerWatt": S(4.0e10, ASSUMED),
            "sigmaF": S(5.0, ASSUMED),
            "gammaI": S(0.061, ASSUMED),
            "gammaXe": S(0.003, ASSUMED),
            "lambdaI": S(2.87e-5, ASSUMED),
            "lambdaXe": S(2.09e-5, ASSUMED),
            "sigmaXe": S(2.6e-22, ASSUMED),
        },
        "plant": {
            "modes": ["steady", "pulse"],
            "initialMode": "steady",
            "pumps": [{"id": "primary"}],
            "instruments": [
                {"id": "linear", "signal": "truth.power", "scale": "linear", "range": [0.0, 3.0e5], "lag": 0.05, "noise": 0.01},
                {"id": "log", "signal": "truth.power", "scale": "log", "range": [1.0e-4, 1.0e9], "lag": 0.005, "noise": 0.01},
                {"id": "fuel-t1", "signal": "truth.fuelTemp", "scale": "linear", "range": [273.15, 1273.15], "lag": 0.5, "noise": 0.002},
                {"id": "fuel-t2", "signal": "truth.fuelTemp", "scale": "linear", "range": [273.15, 1273.15], "lag": 0.5, "noise": 0.002},
                {"id": "pool-temp", "signal": "truth.coolantTemp", "scale": "linear", "range": [273.15, 373.15], "lag": 5.0, "noise": 0.001},
            ],
            "trips": [
                {"id": "power-high", "input": "indicated.linear", "predicate": {"op": "gt", "value": 2.75e5}, "modes": ["steady"], "latching": True},
                {"id": "fuel-temp-high", "input": "indicated.fuel-t1", "predicate": {"op": "gt", "value": 873.15}, "latching": True},
                {"id": "period-short", "input": "truth.period", "predicate": {"all": [{"op": "gt", "value": 0.0}, {"op": "lt", "value": 3.0}]}, "modes": ["steady"], "latching": True},
            ],
            "interlocks": [
                {"id": "fire-needs-pulse-mode", "when": {"signal": "truth.mode", "op": "ne", "value": "pulse"}, "blocks": ["rod.fire"], "reason": "The transient rod can only be fired in pulse mode."},
                {"id": "pulse-mode-low-power", "when": {"all": [{"signal": "truth.mode", "op": "eq", "value": "steady"}, {"signal": "indicated.linear", "op": "gt", "value": 1000.0}]}, "blocks": ["mode.set"], "reason": "Switching to pulse mode requires steady power below 1 kW."},
            ],
        },
        "shapes": {
            "bins": {"elements": elements, "axialEdgesCm": AXIAL_EDGES},
            "basis": "heating",
            "normalization": "fraction-of-total-power",
            "form": "separable",
            "base": "base",
            "baseUnc": "baseUnc",
            "volumes": "volumes",
            "rodDeltas": {rid: {"x": ROD_X, "array": f"rod_{rid}"} for rid in ROD_SPECS},
            "tempDelta": {"T": TEMP_GRID, "array": "tempDelta"},
        },
        "arrays": arrays,
        "geometry": {"units": "cm", "up": "z", "primitives": geometry},
        "domain": {
            "rods": {rid: [0.0, 1.0] for rid in ROD_SPECS},
            "Tfuel": [T_REF, 1200.0],
            "Tcoolant": [283.15, 353.15],
            "xenon": [0.0, 4.0e20],
            "jointChecked": [],
        },
    }

    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    return manifest


def main():
    parser = argparse.ArgumentParser(description="Build JSI TRIGA benchmark library.")
    parser.add_argument("--out", type=Path, default=None, help="Output library folder (default libraries/<id>)")
    parser.add_argument("--core", choices=sorted(VARIANTS), default=None,
                        help="Run-3 variant (docs/validation/m1-run3-protocol.md); default: the original triga-jsi library")
    args = parser.parse_args()
    out = args.out or (REPO_ROOT / "libraries" / VARIANTS[args.core]["id"] if args.core else DEFAULT_OUT)

    print(f"Building TRIGA-JSI library in {out}...")
    manifest = build_library(out, args.core)
    print(f"Built library '{manifest['id']}' (status: {manifest['status']}) successfully.")


if __name__ == "__main__":
    main()
