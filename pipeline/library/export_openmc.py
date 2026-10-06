"""Export an M2 OpenMC sweep summary to a reactor library folder.

Converts pipeline/openmc/results/sweep_<core>.json into a valid library directory
conforming to docs/library-format.md (v0.1.0) and passing pipeline.library.validate.
"""
from __future__ import annotations

import argparse
import bisect
import copy
import datetime
import hashlib
import json
import math
import shutil
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any

from pipeline.library import build_triga
from pipeline.openmc import core_model

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENMC_DATA = REPO_ROOT / "pipeline" / "openmc" / "data"

ROD_ID_MAP = {
    "T": "transient",
    "V": "safety",
    "K": "shim",
    "R": "regulating",
}

ROD_LETTER_MAP = {
    "transient": "T",
    "safety": "V",
    "shim": "K",
    "regulating": "R",
}

REQUIRED_FAMILIES = {"reference", "rod-worth", "fuel-temp", "coolant-temp", "holdout"}


def step_to_x(rod_letter: str, steps: float) -> float:
    """Convert indicator steps to position fraction withdrawn x in [0, 1].

    Fuel-followed rods (K, V, R): x = (900 - steps) / 700 (200 -> 1, 900 -> 0).
    Transient rod (T): x = (900 - steps) / 900 (0 -> 1, 900 -> 0).
    Returns x rounded to 12 decimal places.
    """
    letter = ROD_LETTER_MAP.get(rod_letter, rod_letter)
    if letter in ("K", "V", "R"):
        x = (900.0 - float(steps)) / 700.0
    elif letter == "T":
        x = (900.0 - float(steps)) / 900.0
    else:
        raise ValueError(f"Unknown rod identifier: {rod_letter}")
    return round(x, 12)


def isotonic(xs: list[float], ys: list[float] | None = None, ws: list[float] | None = None) -> list[float]:
    """Weighted isotonic regression (non-decreasing) using pool-adjacent-violators.

    Can be called as:
      isotonic(xs, ys, ws)
      isotonic(xs, ys)
      isotonic(ys)
    """
    if ys is None:
        ys = xs
        xs = list(range(len(ys)))
    if len(ys) == 0:
        return []
    if ws is None:
        ws = [1.0] * len(ys)

    indices = sorted(range(len(xs)), key=lambda i: xs[i])
    sorted_ys = [float(ys[i]) for i in indices]
    sorted_ws = [float(ws[i]) for i in indices]

    # Block: [weighted_sum, total_weight, count]
    blocks: list[list[float]] = []
    for y, w in zip(sorted_ys, sorted_ws):
        blocks.append([w * y, w, 1.0])
        while len(blocks) >= 2:
            prev = blocks[-2]
            curr = blocks[-1]
            prev_mean = prev[0] / prev[1]
            curr_mean = curr[0] / curr[1]
            if prev_mean > curr_mean:
                prev[0] += curr[0]
                prev[1] += curr[1]
                prev[2] += curr[2]
                blocks.pop()
            else:
                break

    sorted_fitted: list[float] = []
    for b_sum, b_weight, b_count in blocks:
        mean = b_sum / b_weight
        sorted_fitted.extend([mean] * int(round(b_count)))

    # Map back to original indices
    result = [0.0] * len(ys)
    for orig_idx, val in zip(indices, sorted_fitted):
        result[orig_idx] = val
    return result


# Heat transfer law hA(dT) = h0 (dT / 100 K)^n, fitted to the measured reactivity at two states of the IAEA/JSI power ascension
# (docs/validation/m7-heat-transfer-results.md, first sensitivity combination; one exercise, the measured core is not stated).
HEAT_TRANSFER_LAW = {"242": {"h0": 1288.7, "n": 0.2169}, "246": {"h0": 1382.5, "n": 0.2333}}
HEAT_TRANSFER_NOTE = (
    " Heat transfer: hA(dT) = h0 (dT / 100 K)^n with h0 = {h0} W/K and n = {n}, fitted to the measured power defect at 43.6 and 250 kW "
    "of the IAEA/JSI steady power ascension (one exercise, unknown core; docs/validation/m7-heat-transfer-results.md). It reproduces the "
    "held-out defect within 4 % and the shape of the fuel temperature rise within 0.03-0.05, but overshoots the defect at 2.9 kW "
    "(33-37 against 20.6 pcm). It is consistent with the measured hot-element temperature given a thermocouple peaking of {f_tc} "
    "from the pulse database (docs/validation/m7-hot-element-2-results.md); the library's own shape arrays give a larger peaking."
)
HEAT_TRANSFER_F_TC = {"242": "1.28", "246": "1.39"}


def _thermal_on_transport_grid(base_thermal, core=None):
    """The base library's thermal block, with the heat sink at the transport reference temperature.

    The base library assumes a 293.15 K sink, but the transport tables start at 294 K. The pool then cooled below the
    first data point within seconds, and the runtime reported `outOfDomain` (R_DOMAIN_TFUEL / R_DOMAIN_TCOOLANT) for a
    shift of under 1 K. The sink temperature is an assumption either way; 294 K keeps the state on the data.
    """
    thermal = copy.deepcopy(base_thermal)
    thermal["heatExchanger"]["sinkTemp"] = {"value": 294.0, "source": "assumed"}
    law = HEAT_TRANSFER_LAW.get(core)
    if law:
        thermal["hA"] = {"value": law["h0"], "source": "calibration", "exponent": law["n"], "dTRef": 100.0}
    return thermal


def interp(xs: list[float], ys: list[float], x: float) -> float:
    """Linear interpolation with clamping at the endpoints."""
    if not xs:
        raise ValueError("xs must not be empty")
    if len(xs) == 1 or x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_right(xs, x) - 1
    if i >= len(xs) - 1:
        return ys[-1]
    t = (x - xs[i]) / (xs[i + 1] - xs[i])
    return ys[i] + t * (ys[i + 1] - ys[i])


ROUNDING_TOL = 1e-6        # the most float32 rounding can shift a slice sum; anything larger is a real error, not rounding


def _pack_f32_slice_normalized(values: list[float], target_sum: float = 0.0) -> list[float]:
    """Cast float64 values to float32 so that sum(f32) equals target_sum within 1e-5 (library-format section 10). Only rounding
    is repaired: if the float64 values themselves miss the target by more than ROUNDING_TOL, that is an input error and raises.
    (Codex M2 review, finding 4: repairing any deficit manufactured a power spike in one bin.)"""
    vals = list(values)
    miss = target_sum - math.fsum(vals)
    if abs(miss) > ROUNDING_TOL:
        raise ValueError(f"slice sums to {target_sum - miss!r}, expected {target_sum} (off by {miss:.3e}, beyond rounding)")
    for _ in range(5):
        f32 = list(struct.unpack(f"<{len(vals)}f", struct.pack(f"<{len(vals)}f", *vals)))
        err = target_sum - math.fsum(f32)
        if abs(err) <= 1e-7:
            return f32
        idx = max(range(len(vals)), key=lambda i: abs(vals[i]))
        vals[idx] += err
    return f32


def _finite(x: Any, what: str) -> float:
    v = float(x)
    if not math.isfinite(v):
        raise ValueError(f"{what} is not finite: {x!r}")
    return v


def check_summary(summary: dict[str, Any]) -> None:
    """Refuse a summary that isn't exactly the planned sweep with consistent, finite results (Codex M2 review, findings 3, 5)."""
    from pipeline.openmc import sweep
    for field in ("core", "burnup", "cases"):
        if field not in summary:
            raise ValueError(f"summary has no {field!r}")
    if summary.get("complete") is not True:
        raise ValueError("summary complete is not true")
    core = str(summary["core"])
    if core not in sweep.REFERENCE_RODS:
        raise ValueError(f"unknown core {core!r}")
    cases = summary["cases"]
    names = [c.get("name") for c in cases]
    if len(names) != len(set(names)):
        raise ValueError("duplicate cases in the summary")
    planned = {c["name"]: c for c in sweep.plan(core)}
    missing, extra = sorted(set(planned) - set(names)), sorted(set(names) - set(planned))
    if missing or extra:
        raise ValueError(f"summary does not match the sweep plan: missing {missing[:5]}, unexpected {extra[:5]}")
    if not isinstance(summary.get("openmc"), dict) or "openmc" not in summary["openmc"]:
        raise ValueError("summary has no OpenMC version")
    for c in cases:
        for k in ("key", "dataDigest"):
            if not isinstance(c.get(k), str) or not c[k]:
                raise ValueError(f"case {c['name']!r} has no {k}")
    for c in cases:
        p = planned[c["name"]]
        for k in ("family", "rods", "tfuel", "tcool", "kinetics"):
            if c.get(k) != p[k]:
                raise ValueError(f"case {c['name']!r}: {k} is {c.get(k)!r}, the plan says {p[k]!r}")
    ref = next(c for c in cases if c["family"] == "reference")
    elements, edges = ref.get("elements"), ref.get("axialEdgesCm")
    if not elements or not edges or len(edges) < 2:
        raise ValueError("reference case missing elements or axial edges")
    E, A = len(elements), len(edges) - 1
    for c in cases:
        name = c["name"]
        if c.get("elements") != elements:
            raise ValueError(f"case {name!r}: elements differ from the reference")
        if c.get("axialEdgesCm") != edges:
            raise ValueError(f"case {name!r}: axial edges differ from the reference")
        if c.get("basis") != "fission" or c.get("normalization") != "fraction-of-total-power":
            raise ValueError(f"case {name!r}: shape basis/normalization {c.get('basis')!r}/{c.get('normalization')!r}")
        k, ks = _finite(c.get("k"), f"{name} k"), _finite(c.get("kStd"), f"{name} kStd")
        if k <= 0 or ks < 0:
            raise ValueError(f"case {name!r}: k {k}, kStd {ks}")
        base = c.get("base")
        if not isinstance(base, list) or len(base) != E or any(not isinstance(r, list) or len(r) != A for r in base):
            raise ValueError(f"case {name!r}: base is not [{E}][{A}]")
        unc = c.get("baseUnc")
        if not isinstance(unc, list) or len(unc) != E or any(not isinstance(r, list) or len(r) != A for r in unc):
            raise ValueError(f"case {name!r}: baseUnc is not [{E}][{A}]")
        for row in base:
            for v in row:
                if not math.isfinite(v) or v < 0:
                    raise ValueError(f"case {name!r}: base value {v!r}")
        for row in unc:
            for v in row:
                if math.isnan(v) or v < 0:
                    raise ValueError(f"case {name!r}: baseUnc value {v!r}")
    for k in ("betaGroups", "betaGroupsStd"):
        v = ref.get(k)
        if not isinstance(v, list) or len(v) != 6:
            raise ValueError(f"reference case {k} missing or not 6 groups")
        for x in v:
            _finite(x, f"reference {k}")
    _finite(ref.get("lambdaS"), "reference lambdaS")
    _finite(ref.get("lambdaStdS"), "reference lambdaStdS")


def export(summary: dict[str, Any], out_dir: Path | str, created: str | None = None) -> dict[str, Any]:
    """Turn an M2 sweep summary into a complete reactor library and return an output report dict.

    The library is built in a staging folder next to `out_dir`, validated (pipeline.library.validate), and only then swapped
    in; any failure before the swap leaves an existing library at `out_dir` untouched (Codex M2 review, finding 3)."""
    from pipeline.library.validate import validate_library
    check_summary(summary)
    out_dir = Path(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = out_dir.parent / f".{out_dir.name}.staging"
    backup = out_dir.parent / f".{out_dir.name}.old"
    for d in (staging, backup):
        if d.exists():
            shutil.rmtree(d)
    try:
        report = _write_library(summary, staging, created)
        issues = validate_library(staging)
        if issues:
            raise ValueError("exported library fails validation: " + "; ".join(f"{i.code} {i.path}" for i in issues[:10]))
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if out_dir.exists():
        out_dir.rename(backup)
    staging.rename(out_dir)
    if backup.exists():
        shutil.rmtree(backup)
    return report


def _write_library(summary: dict[str, Any], out_dir: Path, created: str | None) -> dict[str, Any]:
    cases = summary["cases"]
    ref_case = next(c for c in cases if c["family"] == "reference")
    elements = ref_case["elements"]
    core = str(summary["core"])
    burnup = summary["burnup"]
    created_date = created or datetime.date.today().isoformat()

    out_dir.mkdir(parents=True)
    arrays_dir = out_dir / "arrays"
    arrays_dir.mkdir()

    # Reference physics
    k_ref = float(ref_case["k"])
    k_std_ref = float(ref_case["kStd"])
    rho_ref = (k_ref - 1.0) / k_ref
    sigma_ref = k_std_ref / (k_ref ** 2)

    # Base library inheritance
    with tempfile.TemporaryDirectory() as tmpdir:
        base_manifest = build_triga.build_library(Path(tmpdir), core)

    # Worth curves and report points
    report_rods = {}
    reactivity_rods = []
    base_rods_by_id = {r["id"]: r for r in base_manifest["reactivity"]["rods"]}

    rod_letter_order = ["T", "V", "K", "R"]
    worth_tables: dict[str, dict[str, Any]] = {}

    for letter in rod_letter_order:
        rod_id = ROD_ID_MAP[letter]
        b_rod = base_rods_by_id[rod_id]
        ref_x = step_to_x(letter, ref_case["rods"][letter])

        raw_points = [{"x": ref_x, "rho": 0.0, "sigma": 0.0, "weight": 1e12, "is_ref": True}]
        for c in cases:
            if c.get("family") == "rod-worth" and c.get("rod") == letter:
                x = step_to_x(letter, c["rods"][letter])
                k_case = float(c["k"])
                k_std_case = float(c["kStd"])
                rho_case = (k_case - 1.0) / k_case
                sigma_case = k_std_case / (k_case ** 2)
                sigma = math.sqrt(sigma_case ** 2 + sigma_ref ** 2)
                w = 1.0 / (sigma ** 2) if sigma > 0 else 1e12
                raw_points.append({
                    "x": x,
                    "rho": rho_case - rho_ref,
                    "sigma": sigma,
                    "weight": w,
                    "is_ref": False,
                })

        raw_points.sort(key=lambda p: p["x"])
        xs = [p["x"] for p in raw_points]
        ys = [p["rho"] for p in raw_points]
        ws = [p["weight"] for p in raw_points]

        fitted = isotonic(xs, ys, ws)
        ref_idx = next(i for i, p in enumerate(raw_points) if p["is_ref"])
        ref_fitted = fitted[ref_idx]

        fitted_rhos = [y - ref_fitted for y in fitted]
        fitted_rhos[ref_idx] = 0.0
        uncs = [0.0 if i == ref_idx else raw_points[i]["sigma"] for i in range(len(raw_points))]

        worth_table = {
            "x": xs,
            "rho": fitted_rhos,
            "unc": uncs,
            "interp": "linear",
            "outOfRange": "clamp-and-flag",
            "source": "transport",
        }
        worth_tables[rod_id] = worth_table

        travel_cm = 900.0 * core_model.STEP_CM if rod_id == "transient" else 700.0 * core_model.STEP_CM
        rod_obj = {
            "id": rod_id,
            "name": b_rod["name"],
            "travelCm": travel_cm,
            "speed": b_rod["speed"],
            "pulseCapable": b_rod["pulseCapable"],
            "worth": worth_table,
            "scram": b_rod["scram"],
        }
        if b_rod["pulseCapable"]:
            rod_obj["fireTime"] = b_rod["fireTime"]
        reactivity_rods.append(rod_obj)

        report_rods[rod_id] = {
            "raw": [{"x": p["x"], "rho": p["rho"], "unc": p["sigma"]} for p in raw_points],
            "fitted": [{"x": x, "rho": r} for x, r in zip(xs, fitted_rhos)],
        }

    # Fuel temperature table
    ft_cases = [c for c in cases if c.get("family") == "fuel-temp"]
    ft_points = [{"T": 294.0, "rho": 0.0, "unc": 0.0}]
    for c in ft_cases:
        T = float(c["tfuel"])
        k_case = float(c["k"])
        k_std_case = float(c["kStd"])
        rho_case = (k_case - 1.0) / k_case
        sigma_case = k_std_case / (k_case ** 2)
        sigma = math.sqrt(sigma_case ** 2 + sigma_ref ** 2)
        ft_points.append({"T": T, "rho": rho_case - rho_ref, "unc": sigma})
    ft_points.sort(key=lambda p: p["T"])

    fuel_temp_table = {
        "T": [p["T"] for p in ft_points],
        "rho": [p["rho"] for p in ft_points],
        "unc": [p["unc"] for p in ft_points],
        "interp": "linear",
        "outOfRange": "extrapolate-and-flag",
        "source": "transport",
    }

    # Coolant temperature table
    ct_cases = [c for c in cases if c.get("family") == "coolant-temp"]
    ct_points = [{"T": 294.0, "rho": 0.0, "unc": 0.0}]
    for c in ct_cases:
        T = float(c["tcool"])
        k_case = float(c["k"])
        k_std_case = float(c["kStd"])
        rho_case = (k_case - 1.0) / k_case
        sigma_case = k_std_case / (k_case ** 2)
        sigma = math.sqrt(sigma_case ** 2 + sigma_ref ** 2)
        ct_points.append({"T": T, "rho": rho_case - rho_ref, "unc": sigma})
    ct_points.sort(key=lambda p: p["T"])

    coolant_temp_table = {
        "T": [p["T"] for p in ct_points],
        "rho": [p["rho"] for p in ct_points],
        "unc": [p["unc"] for p in ct_points],
        "interp": "linear",
        "outOfRange": "extrapolate-and-flag",
        "source": "transport",
    }

    # Shapes and binary arrays
    E = len(elements)
    axial_edges = ref_case["axialEdgesCm"]
    A = len(axial_edges) - 1

    # Base shape float64
    ref_base_f64 = [float(v) for row in ref_case["base"] for v in row]
    base_f32 = _pack_f32_slice_normalized(ref_base_f64, target_sum=1.0)
    data_base = build_triga.pack_f32(base_f32)
    (out_dir / "arrays" / "base.f32").write_bytes(data_base)

    # Base unc
    base_unc_f64 = []
    for row in ref_case["baseUnc"]:
        for v in row:
            if v is None or math.isnan(v) or math.isinf(v):
                base_unc_f64.append(1.0)
            else:
                base_unc_f64.append(float(v))
    data_base_unc = build_triga.pack_f32(base_unc_f64)
    (out_dir / "arrays" / "base_unc.f32").write_bytes(data_base_unc)

    # Volumes [E, A]
    fuel_data = json.loads((OPENMC_DATA / "jsi_standard_fuel.json").read_text(encoding="utf-8"))
    geo_data = json.loads((OPENMC_DATA / "jsi_core_geometry.json").read_text(encoding="utf-8"))
    follower_positions = {core_model.ROD_AT[r] for r in ("K", "V", "R")}
    r_zr = fuel_data["radiiCm"]["zrRod"]
    r_fuel_std = fuel_data["radiiCm"]["fuel"]
    r_fuel_follower = geo_data["controlRods"]["fueledFollower"]["absorber"]["diameterIn"] * 2.54 / 2.0

    widths = [axial_edges[j + 1] - axial_edges[j] for j in range(A)]
    volumes = []
    for e in elements:
        r_outer = r_fuel_follower if e in follower_positions else r_fuel_std
        area = math.pi * (r_outer ** 2 - r_zr ** 2)
        for dz in widths:
            volumes.append(area * dz)
    data_volumes = build_triga.pack_f32(volumes)
    (out_dir / "arrays" / "volumes.f32").write_bytes(data_volumes)

    # Rod deltas
    rod_delta_arrays: dict[str, list[list[float]]] = {}  # rod_id -> list of float64 slices
    rod_delta_f32_blobs: dict[str, bytes] = {}
    rod_delta_manifest: dict[str, dict[str, Any]] = {}

    for letter in rod_letter_order:
        rod_id = ROD_ID_MAP[letter]
        xs = worth_tables[rod_id]["x"]

        # Collect float64 cases for each x
        case_map: dict[float, list[float]] = {}
        for c in cases:
            if c.get("family") == "rod-worth" and c.get("rod") == letter:
                x = step_to_x(letter, c["rods"][letter])
                case_map[x] = [float(v) for row in c["base"] for v in row]

        slices_f64: list[list[float]] = []
        packed_slices: list[float] = []
        for x in xs:
            if x not in case_map:  # Reference point
                sl_f64 = [0.0] * (E * A)
                sl_f32 = [0.0] * (E * A)
            else:
                sl_f64 = [a - b for a, b in zip(case_map[x], ref_base_f64, strict=True)]
                sl_f32 = _pack_f32_slice_normalized(sl_f64, target_sum=0.0)
            slices_f64.append(sl_f32)           # holdout predictions use the values actually exported
            packed_slices.extend(sl_f32)

        rod_delta_arrays[rod_id] = slices_f64
        blob = build_triga.pack_f32(packed_slices)
        rod_delta_f32_blobs[rod_id] = blob
        (out_dir / "arrays" / f"rod_{rod_id}.f32").write_bytes(blob)
        rod_delta_manifest[rod_id] = {"x": xs, "array": f"rod_{rod_id}"}

    # Temperature delta
    temp_grid = fuel_temp_table["T"]
    temp_case_map: dict[float, list[float]] = {}
    for c in ft_cases:
        T = float(c["tfuel"])
        temp_case_map[T] = [float(v) for row in c["base"] for v in row]

    temp_slices_f64: list[list[float]] = []
    temp_packed_slices: list[float] = []
    for T in temp_grid:
        if T not in temp_case_map:  # Reference 294 K
            sl_f64 = [0.0] * (E * A)
            sl_f32 = [0.0] * (E * A)
        else:
            sl_f64 = [a - b for a, b in zip(temp_case_map[T], ref_base_f64, strict=True)]
            sl_f32 = _pack_f32_slice_normalized(sl_f64, target_sum=0.0)
        temp_slices_f64.append(sl_f32)          # holdout predictions use the values actually exported
        temp_packed_slices.extend(sl_f32)

    blob_temp = build_triga.pack_f32(temp_packed_slices)
    (out_dir / "arrays" / "temp_delta.f32").write_bytes(blob_temp)

    # Arrays dictionary in manifest
    arrays_dict = {
        "base": build_triga.descriptor("arrays/base.f32", data_base, [E, A]),
        "baseUnc": build_triga.descriptor("arrays/base_unc.f32", data_base_unc, [E, A]),
        "volumes": build_triga.descriptor("arrays/volumes.f32", data_volumes, [E, A]),
        "tempDelta": build_triga.descriptor("arrays/temp_delta.f32", blob_temp, [len(temp_grid), E, A]),
    }
    for rod_id, blob in rod_delta_f32_blobs.items():
        xs_len = len(worth_tables[rod_id]["x"])
        arrays_dict[f"rod_{rod_id}"] = build_triga.descriptor(f"arrays/rod_{rod_id}.f32", blob, [xs_len, E, A])

    # Holdout predictions and domain.jointChecked
    def interp_delta_slice(xs: list[float], slices: list[list[float]], x: float) -> list[float]:
        if x <= xs[0]:
            return list(slices[0])
        if x >= xs[-1]:
            return list(slices[-1])
        i = bisect.bisect_right(xs, x) - 1
        if i >= len(xs) - 1:
            return list(slices[-1])
        t = (x - xs[i]) / (xs[i + 1] - xs[i])
        return [(1.0 - t) * a + t * b for a, b in zip(slices[i], slices[i + 1])]

    holdout_cases = [c for c in cases if c.get("family") == "holdout"]
    joint_checked = []
    report_joint_checked = []

    for c in holdout_cases:
        h_rods_x = {ROD_ID_MAP[r]: step_to_x(r, c["rods"][r]) for r in ("T", "K", "V", "R")}
        h_tfuel = float(c["tfuel"])
        k_case = float(c["k"])
        rho_case = (k_case - 1.0) / k_case

        rho_pred = rho_ref + sum(
            interp(worth_tables[rid]["x"], worth_tables[rid]["rho"], h_rods_x[rid])
            for rid in worth_tables
        ) + interp(fuel_temp_table["T"], fuel_temp_table["rho"], h_tfuel)
        rho_err = abs(rho_pred - rho_case)

        # Shape prediction, from the exported (float32) arrays; strict zips, so a short or mismatched array is an error
        shape_pred = list(base_f32)
        for letter in rod_letter_order:
            rid = ROD_ID_MAP[letter]
            sl = interp_delta_slice(worth_tables[rid]["x"], rod_delta_arrays[rid], h_rods_x[rid])
            shape_pred = [sp + d for sp, d in zip(shape_pred, sl, strict=True)]
        sl_temp = interp_delta_slice(fuel_temp_table["T"], temp_slices_f64, h_tfuel)
        shape_pred = [sp + d for sp, d in zip(shape_pred, sl_temp, strict=True)]

        case_base_flat = [float(v) for row in c["base"] for v in row]
        diffs = [abs(sp - cb) for sp, cb in zip(shape_pred, case_base_flat, strict=True)]
        max_shape_err = _finite(max(diffs), f"holdout {c['name']} shape error") * (E * A)
        rho_err = _finite(rho_err, f"holdout {c['name']} rho error")

        joint_checked.append({
            "rods": h_rods_x,
            "Tfuel": h_tfuel,
            "rhoErr": rho_err,
            "maxShapeErr": max_shape_err,
        })
        report_joint_checked.append({
            "rods": h_rods_x,
            "Tfuel": h_tfuel,
            "rho_case": rho_case,
            "rho_pred": rho_pred,
            "rhoErr": rho_err,
            "maxShapeErr": max_shape_err,
        })

    # Geometry primitives
    ring_radii = geo_data["grid"]["ringRadiiCm"]
    reflector = geo_data["reflector"]
    r_gi = reflector["graphiteInnerDiameterIn"] * 2.54 / 2.0
    r_go = reflector["graphiteOuterDiameterIn"] * 2.54 / 2.0
    h_reflector = reflector["heightIn"] * 2.54

    geometry_primitives: list[dict[str, Any]] = [
        {"type": "cylinder", "center": [0.0, 0.0, 0.0], "radius": 100.0, "height": 625.0, "material": "water"},
        {"type": "annulus", "center": [0.0, 0.0, 0.0], "rInner": round(r_gi, 4), "radius": round(r_go, 4),
         "height": round(h_reflector, 4), "material": "graphite"},
    ]

    for e in elements:
        if e in follower_positions:
            continue
        x, y = core_model.position_xy(e, ring_radii)
        geometry_primitives.append({
            "type": "cylinder",
            "center": [round(x, 4), round(y, 4), 0.0],
            "radius": r_fuel_std,
            "height": 38.1,
            "material": "fuel",
            "element": e,
        })
        geometry_primitives.append({
            "type": "annulus",
            "center": [round(x, 4), round(y, 4), 0.0],
            "rInner": fuel_data["radiiCm"]["gap"],
            "radius": fuel_data["radiiCm"]["clad"],
            "height": 38.1,
            "material": "steel",
            "element": e,
        })

    ff_c = geo_data["controlRods"]["fueledFollower"]
    r_abs_ff = ff_c["absorber"]["diameterIn"] * 2.54 / 2.0
    h_abs_ff = ff_c["absorber"]["lengthIn"] * 2.54
    for letter in ("K", "V", "R"):
        rod_id = ROD_ID_MAP[letter]
        pos = core_model.ROD_AT[letter]
        x, y = core_model.position_xy(pos, ring_radii)
        # at x = 0 (fully in) the absorber's bottom is at the bottom of the fuel and the follower fuel hangs below it
        # (core_model.absorber_bottom); the viewer moves both up by x * travelCm
        geometry_primitives.append({
            "type": "cylinder",
            "center": [round(x, 4), round(y, 4), round(-core_model.HALF_FUEL + h_abs_ff / 2.0, 6)],
            "radius": r_abs_ff,
            "height": h_abs_ff,
            "material": "b4c",
            "rod": rod_id,
        })
        geometry_primitives.append({
            "type": "cylinder",
            "center": [round(x, 4), round(y, 4), round(-core_model.HALF_FUEL - h_abs_ff / 2.0, 6)],
            "radius": r_abs_ff,
            "height": h_abs_ff,
            "material": "fuel",
            "element": pos,
            "rod": rod_id,
        })

    t_c = geo_data["controlRods"]["transient"]
    r_abs_t = t_c["absorber"]["diameterIn"] * 2.54 / 2.0
    h_abs_t = t_c["absorber"]["lengthIn"] * 2.54
    pos_t = core_model.ROD_AT["T"]
    xt, yt = core_model.position_xy(pos_t, ring_radii)
    geometry_primitives.append({
        "type": "cylinder",
        "center": [round(xt, 4), round(yt, 4), round(-core_model.HALF_FUEL + h_abs_t / 2.0, 6)],
        "radius": r_abs_t,
        "height": h_abs_t,
        "material": "b4c",
        "rod": "transient",
    })

    # Sources list
    sources = [s for s in base_manifest["provenance"]["sources"] if s["id"] != "icsbep"]
    sources.append({
        "id": "pungercic2024",
        "cite": ("A. Pungerčič, A. Haghighat, L. Snoj, JSI TRIGA fuel rod reactivity worth experiments "
                 "for validation of Serpent-2 and RAPID fuel burnup calculations, "
                 "Nuclear Engineering and Technology 56 (2024) 3405-3424"),
    })

    # Provenance from the summary itself, not constants (Codex M2 review, finding 7): the code version the cases ran with, the
    # nuclear-data identity, and a digest of every case key (a key hashes a case's full inputs, data files and versions).
    openmc_version = summary["openmc"]["openmc"]
    data_digests = sorted({c["dataDigest"] for c in cases})
    xs_path = summary.get("nuclearData", {}).get("crossSections", "")
    model_id = hashlib.sha256("\n".join(sorted(c["key"] for c in cases)).encode()).hexdigest()
    notes = (
        f"Full-core OpenMC {openmc_version} transport at a uniform burnup ({burnup} MWd/kg), {len(cases)} cases "
        f"({summary.get('stats')}). Transport results: reference state rho, rod worth curves, fuel and coolant temperature "
        "reactivity feedback, kinetics (beta_eff and Lambda by IFP), and fission power shapes (fraction of all fuel fission; the "
        "lowest axial bin holds fuel-follower fuel below the core, zero for regular elements, whose volume there is nominal; "
        "its relative uncertainty is the region total's). Base library inputs: thermal properties, poisons, plant "
        "instrumentation/trips/interlocks, delayed group lambdas, external source, rod scram profiles, and xenon table."
    )
    law = HEAT_TRANSFER_LAW.get(core)
    if law:
        notes += HEAT_TRANSFER_NOTE.format(h0=law["h0"], n=law["n"], f_tc=HEAT_TRANSFER_F_TC[core])

    ref_rods_dict = {ROD_ID_MAP[r]: step_to_x(r, ref_case["rods"][r]) for r in ("T", "K", "V", "R")}

    manifest = {
        "schemaVersion": base_manifest["schemaVersion"],
        "id": f"triga-jsi-{core}-openmc",
        "name": f"{base_manifest['name']} — OpenMC (M2)",
        "status": "experimental",
        "capabilities": ["point-kinetics/lumped-thermal-v2"] if law else base_manifest["capabilities"],
        "provenance": {
            "generator": "pipeline.library.export_openmc",
            "transportCode": f"OpenMC {openmc_version}",
            "nuclearData": f"{xs_path} (data digests {', '.join(d[:12] for d in data_digests)})",
            "model": f"sha256 of the {len(cases)} sweep case keys: {model_id}",
            "created": created_date,
            "notes": notes,
            "sources": sources,
        },
        "reference": {
            "rods": ref_rods_dict,
            "Tfuel": {"value": 294.0, "source": "transport"},
            "Tcoolant": {"value": 294.0, "source": "transport"},
            "xenon": {"value": 0.0, "source": "transport"},
            "rho": {"value": rho_ref, "unc": sigma_ref, "source": "transport"},
            "calibration": {
                "deltaRho": -rho_ref,
                "reason": (f"Uniform-burnup model (B246 = {burnup} MWd/kg) is not exactly critical "
                           "at the measured critical rods; this offset makes the measured critical state critical. "
                           "docs/validation/m2-burnup-results.md"),
            },
        },
        "kinetics": {
            "beta": {
                "values": ref_case["betaGroups"],
                "unc": ref_case["betaGroupsStd"],
                "source": "transport",
            },
            "lambda": copy.deepcopy(base_manifest["kinetics"]["lambda"]),
            "genTime": {
                "value": ref_case["lambdaS"],
                "unc": ref_case["lambdaStdS"],
                "source": "transport",
            },
            "extSource": copy.deepcopy(base_manifest["kinetics"]["extSource"]),
        },
        "reactivity": {
            "rods": reactivity_rods,
            "fuelTemp": fuel_temp_table,
            "coolantTemp": coolant_temp_table,
            "xenon": copy.deepcopy(base_manifest["reactivity"]["xenon"]),
        },
        "thermal": _thermal_on_transport_grid(base_manifest["thermal"], core),
        "poisons": copy.deepcopy(base_manifest["poisons"]),
        "plant": copy.deepcopy(base_manifest["plant"]),
        "shapes": {
            "bins": {"elements": elements, "axialEdgesCm": axial_edges},
            "basis": "fission",
            "normalization": "fraction-of-total-power",
            "form": "separable",
            "base": "base",
            "baseUnc": "baseUnc",
            "volumes": "volumes",
            "rodDeltas": rod_delta_manifest,
            "tempDelta": {"T": temp_grid, "array": "tempDelta"},
        },
        "arrays": arrays_dict,
        "geometry": {"units": "cm", "up": "z", "primitives": geometry_primitives},
        "domain": {
            # where the tables have data (library-format section 13), not the nominal [0, 1] (Codex M2 review, finding 6)
            "rods": {rid: [min(worth_tables[rid]["x"]), max(worth_tables[rid]["x"])] for rid in ROD_ID_MAP.values()},
            "Tfuel": [min(p["T"] for p in ft_points), max(p["T"] for p in ft_points)],
            "Tcoolant": [min(p["T"] for p in ct_points), max(p["T"] for p in ct_points)],
            "xenon": copy.deepcopy(base_manifest["domain"]["xenon"]),
            "jointChecked": joint_checked,
        },
    }

    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2, allow_nan=False)      # NaN or Infinity is an error, not a manifest the validator rejects later
        f.write("\n")

    report = {
        "core": core,
        "model": model_id,
        "caseKeys": {c["name"]: c["key"] for c in cases},
        "rods": report_rods,
        "fuelTemp": {"points": ft_points},
        "coolantTemp": {"points": ct_points},
        "jointChecked": report_joint_checked,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--summary", type=Path, required=True, help="Path to input sweep summary JSON")
    parser.add_argument("--out", type=Path, default=None, help="Output library directory")
    parser.add_argument("--report", type=Path, default=None, help="Output report JSON file")
    parser.add_argument("--created", type=str, default=None, help="Created date (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    if "core" not in summary:
        raise ValueError(f"{args.summary}: summary has no 'core'")
    core = str(summary["core"])

    out_dir = args.out or (REPO_ROOT / "libraries" / f"triga-jsi-{core}-openmc")
    report_path = args.report or (REPO_ROOT / "pipeline" / "openmc" / "results" / f"export_{core}.json")

    report = export(summary, out_dir, created=args.created)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    print(f"Exported library to {out_dir}")
    print(f"Wrote report to {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
