"""Synthetic sweep summary generator for testing the OpenMC exporter.

Generates a complete, synthetic pipeline/openmc/results/sweep_<core>.json
matching the case plan of pipeline.openmc.sweep without requiring OpenMC.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pipeline.library import build_triga
from pipeline.library.export_openmc import interp, step_to_x
from pipeline.openmc import core_model, shapes, sweep

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENMC_DATA = REPO_ROOT / "pipeline" / "openmc" / "data"

W_TOT = {
    "T": 0.030,
    "K": 0.020,
    "V": 0.025,
    "R": 0.006,
}


def _w_raw(r: str, x: float) -> float:
    wtot = W_TOT[r]
    return wtot * (x - math.sin(2.0 * math.pi * x) / (2.0 * math.pi))


def synthetic_summary(core: str, noise: float = 0.0, seed: int = 1) -> dict[str, Any]:
    """Generate a synthetic sweep summary dict for `core` ('242' or '246')."""
    raw_cases = sweep.plan(core)

    occ = json.loads((OPENMC_DATA / "jsi_core_occupancy.json").read_text(encoding="utf-8"))
    fuel_keys = set(occ["cores"][core]["fuel"].keys())
    followers = {core_model.ROD_AT[r] for r in ("K", "V", "R")}
    elements = sorted(fuel_keys | followers, key=lambda s: (s[0], int(s[1:])))

    E = len(elements)
    A = shapes.AXIAL_BINS
    edges = shapes.axial_edges(A)

    geo = json.loads((OPENMC_DATA / "jsi_core_geometry.json").read_text(encoding="utf-8"))
    ring_radii = geo["grid"]["ringRadiiCm"]

    ref_rods = sweep.REFERENCE_RODS[core]
    ref_x = {r: step_to_x(r, ref_rods[r]) for r in ("T", "K", "V", "R")}

    def w_r(r: str, x: float) -> float:
        return _w_raw(r, x) - _w_raw(r, ref_x[r])

    # Find the rod grid points
    grid_xs: dict[str, list[float]] = {}
    grid_rhos: dict[str, list[float]] = {}
    for r in ("T", "K", "V", "R"):
        rod_cases = [c for c in raw_cases if c.get("family") == "rod-worth" and c.get("rod") == r]
        xs = sorted(set([ref_x[r]] + [step_to_x(r, c["rods"][r]) for c in rod_cases]))
        grid_xs[r] = xs
        grid_rhos[r] = [w_r(r, x) for x in xs]

    # Base shape [E, A]
    raw_base = []
    elem_coords = [core_model.position_xy(e, ring_radii) for e in elements]
    mid_z = [(edges[a] + edges[a + 1]) / 2.0 for a in range(A)]

    for ex, ey in elem_coords:
        r_dist = math.hypot(ex, ey)
        f_rad = max(0.2, math.cos(math.pi * r_dist / 50.0))
        for z in mid_z:
            f_ax = max(0.2, math.cos(math.pi * z / 50.0))
            raw_base.append(f_rad * f_ax)

    sum_b = sum(raw_base)
    base_flat = [v / sum_b for v in raw_base]
    min_b = min(base_flat)

    # Precompute zero-mean patterns for perturbation
    # Rod patterns P_r
    P_r: dict[str, list[float]] = {}
    for r in ("T", "K", "V", "R"):
        rx, ry = core_model.position_xy(core_model.ROD_AT[r], ring_radii)
        pat = []
        for ex, ey in elem_coords:
            d2 = (ex - rx) ** 2 + (ey - ry) ** 2
            g_d = math.exp(-d2 / 100.0)
            for z in mid_z:
                pat.append(g_d * (z / core_model.HALF_FUEL))
        # Zero-mean
        mean_p = sum(pat) / len(pat)
        pat = [p - mean_p for p in pat]
        max_p = max(abs(p) for p in pat) or 1.0
        scale = 0.05 * min_b / max_p
        P_r[r] = [p * scale for p in pat]

    # Fuel temperature pattern P_T
    pat_t = []
    for ex, ey in elem_coords:
        r_d = math.hypot(ex, ey)
        for z in mid_z:
            pat_t.append((z / core_model.HALF_FUEL) * (r_d / 20.0))
    mean_t = sum(pat_t) / len(pat_t)
    pat_t = [p - mean_t for p in pat_t]
    max_t = max(abs(p) for p in pat_t) or 1.0
    scale_t = (0.05 * min_b / max_t) / 600.0
    P_T = [p * scale_t for p in pat_t]

    def delta_rod(r: str, x: float) -> list[float]:
        factor = x - ref_x[r]
        return [factor * p for p in P_r[r]]

    def delta_temp(tfuel: float) -> list[float]:
        factor = tfuel - 294.0
        return [factor * p for p in P_T]

    rho_ref = -0.003
    k_std = 7e-4

    cases_out = []
    for c in raw_cases:
        c_out = dict(c)
        family = c["family"]

        if family == "reference":
            rho = rho_ref
            shape_flat = list(base_flat)
        elif family == "rod-worth":
            r = c["rod"]
            x = step_to_x(r, c["rods"][r])
            rho = rho_ref + w_r(r, x)
            d = delta_rod(r, x)
            shape_flat = [b + di for b, di in zip(base_flat, d)]
        elif family == "fuel-temp":
            tfuel = float(c["tfuel"])
            rho = rho_ref - 1e-4 * (tfuel - 294.0)
            d = delta_temp(tfuel)
            shape_flat = [b + di for b, di in zip(base_flat, d)]
        elif family == "coolant-temp":
            tcool = float(c["tcool"])
            rho = rho_ref - 2e-5 * (tcool - 294.0)
            shape_flat = list(base_flat)
        elif family == "holdout":
            h_rods_x = {r: step_to_x(r, c["rods"][r]) for r in ("T", "K", "V", "R")}
            tfuel = float(c["tfuel"])
            rho_interp_sum = sum(interp(grid_xs[r], grid_rhos[r], h_rods_x[r]) for r in ("T", "K", "V", "R"))
            rho = rho_ref + rho_interp_sum - 1e-4 * (tfuel - 294.0) + noise
            # Separable shape delta
            h_delta = [0.0] * (E * A)
            for r in ("T", "K", "V", "R"):
                dr = delta_rod(r, h_rods_x[r])
                h_delta = [h + d for h, d in zip(h_delta, dr)]
            dt = delta_temp(tfuel)
            h_delta = [h + d for h, d in zip(h_delta, dt)]
            shape_flat = [b + d for b, d in zip(base_flat, h_delta)]
        else:
            raise ValueError(f"Unknown family: {family}")

        k = 1.0 / (1.0 - rho)
        c_out["k"] = k
        c_out["kStd"] = k_std
        c_out["key"] = f"key_{c['name']}"
        c_out["basis"] = "fission"
        c_out["elements"] = elements
        c_out["axialEdgesCm"] = edges

        # 2D base array [E][A]
        base_2d = [shape_flat[e * A: (e + 1) * A] for e in range(E)]
        c_out["base"] = base_2d

        # 2D baseUnc [E][A]
        base_unc_2d = [[0.015 for _ in range(A)] for _ in range(E)]
        c_out["baseUnc"] = base_unc_2d

        c_out["outsideFraction"] = 0.012
        c_out["maxRelUnc"] = 0.04
        c_out["medianRelUnc"] = 0.015

        if family == "reference":
            c_out["betaGroups"] = list(build_triga.GROUP_BETAS)
            c_out["betaGroupsStd"] = [b * 0.01 for b in build_triga.GROUP_BETAS]
            c_out["lambdaS"] = 4.5e-5
            c_out["lambdaStdS"] = 1.0e-7

        cases_out.append(c_out)

    return {
        "core": core,
        "burnup": sweep.B246,
        "stats": dict(sweep.STANDARD),
        "openmc": {"openmc": "0.15.3", "numpy": "2.4.0"},
        "complete": True,
        "cases": cases_out,
    }
