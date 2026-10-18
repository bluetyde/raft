"""
JSI TRIGA Mark II experimental pulse comparison and Milestone 1 validation module.

Executes prompt-critical pulse simulations across a reactivity sweep (1.05 to 2.50 $)
using `physics_ref.Engine` on the `libraries/triga-jsi` library.
Compares simulated peak power, pulse width (FWHM), total energy release, and fuel
temperature rise against:
  1. Classical adiabatic Nordheim-Fuchs theory.
  2. The empirical 757-pulse experimental catalog from the JSI TRIGA Mark II reactor.

Produces numbers for the Milestone 1 go/no-go discussion. It does NOT issue a verdict: the experimental bins
here pool 31 core configurations without screening or condition matching, so they can't decide validity
(docs/reviews/2026-09-26-m1-go-review.md). A go/no-go is proposed to the user from a condition-matched comparison.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from physics_ref import Engine, Library
from physics_ref.engine import IEP, IP, ITF
from validation.pulse_loader import (
    DEFAULT_CSV_PATH,
    PulseRecord,
    filter_pulses,
    load_pulse_summary,
)

DEFAULT_LIBRARY_PATH = Path(__file__).parents[1] / "libraries" / "triga-jsi"
DEFAULT_REPORT_PATH = Path(__file__).parent / "pulse_comparison_report.json"

# Standard reactivity sweep covering the TRIGA pulsing regime ($1.10 to $2.20)
DEFAULT_RHO_SWEEP = [1.10, 1.20, 1.30, 1.40, 1.50, 1.60, 1.70, 1.80, 1.90, 2.00, 2.20]


@dataclass
class SimulatedPulse:
    rho_dollars: float
    rho_prompt_dollars: float
    peak_power_mw: float
    peak_time_s: float
    fwhm_s: Optional[float]
    energy_mws: float
    delta_tf_c: float
    peak_tf_c: float
    nf_peak_power_mw: float
    nf_energy_mws: float
    nf_fwhm_s: float


@dataclass
class PulseComparisonPoint:
    rho_dollars: float
    rho_prompt_dollars: float
    sim_pmax_mw: float
    sim_energy_mws: float
    sim_fwhm_s: Optional[float]
    sim_delta_tf_c: float
    sim_peak_tf_c: float
    nf_pmax_mw: float
    nf_energy_mws: float
    nf_fwhm_s: float
    exp_count: int
    exp_pmax_median_mw: Optional[float] = None
    exp_pmax_mean_mw: Optional[float] = None
    exp_pmax_min_mw: Optional[float] = None
    exp_pmax_max_mw: Optional[float] = None
    exp_energy_median_mws: Optional[float] = None
    exp_fwhm_median_s: Optional[float] = None
    exp_t1_median_c: Optional[float] = None


@dataclass
class ComparisonSummary:
    library_id: str
    num_simulations: int
    total_experimental_pulses_matched: int
    pmax_scaling_exponent_sim: float
    pmax_scaling_exponent_exp: float
    energy_scaling_exponent_sim: float
    energy_scaling_exponent_exp: float
    verdict: Optional[str]
    note: str
    pmax_ratio_min: Optional[float]
    pmax_ratio_max: Optional[float]
    points: List[PulseComparisonPoint]


def simulate_pulse(
    library: Library,
    rho_dollars: float,
    initial_power: float = 10.0,
    max_t: float = 0.8,
    dt: float = 1e-3,
) -> SimulatedPulse:
    """
    Simulate a prompt-critical pulse transient using physics_ref.Engine.

    Calibrates initial state to critical equilibrium at reference ambient temperature,
    then steps reactivity by rho_dollars * beta_total via fault.reactivity.
    """
    # Make a detached copy of the library that was passed (not the default one) with zeroed shutdown offset for critical start
    lib_copy = copy.deepcopy(library)
    lib_copy.calibration = -lib_copy.ref_rho
    lib_copy.ext_source = 0.0
    lib_copy.mark_modified(f"pulse-{rho_dollars:.2f}")

    e = Engine(
        lib_copy,
        {"power": {"mode": "critical-equilibrium", "value": initial_power}},
        config={"outerDt": dt},
    )

    # Establish steady state for 10 ms before pulsing
    e.advance(0.01)

    # Prompt reactivity injection
    rho_total = rho_dollars * lib_copy.beta_total
    rho_prompt = (rho_dollars - 1.0) * lib_copy.beta_total
    e.submit({"type": "fault.reactivity", "deltaRho": rho_total})

    times: List[float] = []
    powers: List[float] = []
    t_start = e.t

    while e.t < max_t:
        if e.halted:  # a halted engine makes no progress (M1 review finding 3)
            raise RuntimeError(f"engine halted: {e.halted}")
        e.step()
        times.append(e.t)
        powers.append(e.y[IP])
        # Break early if power has safely dropped below 1% of peak post-peak
        if times[-1] > e.peak_time + 0.05 and powers[-1] < e.peak_power * 0.01:
            break

    peak_p_mw = e.peak_power / 1e6
    energy_mws = e.y[IEP] / 1e6
    delta_tf = e.y[ITF] - lib_copy.ref_tfuel
    peak_tf = e.y[ITF] - 273.15

    # Compute FWHM via linear interpolation of half-power crossings
    half = e.peak_power / 2.0
    crossings: List[float] = []
    for (t0, p0), (t1, p1) in zip(zip(times, powers), zip(times[1:], powers[1:])):
        if (p0 - half) * (p1 - half) <= 0 and p1 != p0:
            crossings.append(t0 + (half - p0) / (p1 - p0) * (t1 - t0))

    fwhm = (crossings[1] - crossings[0]) if len(crossings) >= 2 else None

    # Classical Nordheim-Fuchs theoretical values, with the library's own feedback linearised over this pulse:
    # gamma = -rho_fuel(T_ref + dT) / (m * integral of cp from T_ref to T_ref + dT), reactivity per joule.
    # (Was a hardcoded alpha = 1.05e-4 /K, which ignored the library; found in C2, 2026-09-27.)
    t_ref = lib_copy.ref_tfuel
    n_int = 200
    heat = 0.0
    for i in range(n_int):
        ta = t_ref + delta_tf * i / n_int
        tb = t_ref + delta_tf * (i + 1) / n_int
        heat += 0.5 * (lib_copy.fuel_cp(ta) + lib_copy.fuel_cp(tb)) * (tb - ta)
    heat *= lib_copy.fuel_mass
    k_nf = -lib_copy.fuel_temp(t_ref + delta_tf) / heat if heat > 0 else float("inf")
    gen_time = lib_copy.gen_time

    if rho_prompt > 0:
        nf_pmax = (rho_prompt ** 2 / (2.0 * k_nf * gen_time)) / 1e6
        nf_energy = (2.0 * rho_prompt / k_nf) / 1e6
        nf_fwhm = 3.52 * gen_time / rho_prompt
    else:
        nf_pmax = 0.0
        nf_energy = 0.0
        nf_fwhm = 0.0

    return SimulatedPulse(
        rho_dollars=rho_dollars,
        rho_prompt_dollars=rho_dollars - 1.0,
        peak_power_mw=peak_p_mw,
        peak_time_s=e.peak_time,
        fwhm_s=fwhm,
        energy_mws=energy_mws,
        delta_tf_c=delta_tf,
        peak_tf_c=peak_tf,
        nf_peak_power_mw=nf_pmax,
        nf_energy_mws=nf_energy,
        nf_fwhm_s=nf_fwhm,
    )


def _log_polyfit_slope(xs: List[float], ys: List[float]) -> float:
    """Fit power-law exponent y = a * x^b by linear regression on log(x), log(y)."""
    valid = [(x, y) for x, y in zip(xs, ys) if x > 0 and y > 0]
    if len(valid) < 2:
        return 0.0
    lx = [math.log(x) for x, y in valid]
    ly = [math.log(y) for x, y in valid]
    n = len(valid)
    mean_x = sum(lx) / n
    mean_y = sum(ly) / n
    ss_xx = sum((x - mean_x) ** 2 for x in lx)
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(lx, ly))
    return ss_xy / ss_xx if ss_xx != 0 else 0.0


def run_pulse_comparison(
    library_path: Path = DEFAULT_LIBRARY_PATH,
    pulses_data_path: Optional[Path] = None,
    rho_sweep: Optional[List[float]] = None,
    core: Optional[str] = None,
    window_dollars: float = 0.05,
) -> ComparisonSummary:
    """
    Run full pulse validation comparison against JSI TRIGA database.

    Args:
        library_path: Path to validated reactor library folder (e.g. libraries/triga-jsi).
        pulses_data_path: Optional custom path to pulses_summary.csv.
        rho_sweep: List of reactivity levels in dollars to simulate.
        core: Optional core designation filter (e.g. '253'). If None, matches across all cores.
        window_dollars: Matching tolerance for experimental pulse reactivity bins.

    Returns:
        ComparisonSummary containing all metrics, experimental statistics, and the ratio range (no verdict).
    """
    lib = Library(library_path)
    all_pulses = load_pulse_summary(pulses_data_path)
    if core is not None:
        experimental_pool = filter_pulses(all_pulses, core=core)
    else:
        experimental_pool = all_pulses

    sweep = rho_sweep or DEFAULT_RHO_SWEEP
    points: List[PulseComparisonPoint] = []
    matched_ids: set = set()   # a pulse in two overlapping windows counts once in the total

    for rho in sweep:
        sim = simulate_pulse(lib, rho)
        # Find matching experimental pulses within [rho - window, rho + window]
        matches = filter_pulses(
            experimental_pool,
            min_rho=rho - window_dollars,
            max_rho=rho + window_dollars,
            require_valid_pmax=True,
        )
        matched_ids.update(p.pulse_id for p in matches)

        powers = [p.peak_power_mw for p in matches if p.peak_power_mw and p.peak_power_mw > 0]
        energies = [
            e for e in ((p.energy_1000pts_mws or p.energy_1pct_mws or p.energy_tangent_mws) for p in matches) if e and e > 0
        ]
        fwhms = [p.fwhm_s for p in matches if p.fwhm_s and p.fwhm_s > 0]
        temps = [p.t1_max_c for p in matches if p.t1_max_c and p.t1_max_c > 0]

        def _median(vals: List[float]) -> Optional[float]:
            if not vals:
                return None
            s = sorted(vals)
            mid = len(s) // 2
            return (s[mid] if len(s) % 2 != 0 else (s[mid - 1] + s[mid]) / 2.0)

        point = PulseComparisonPoint(
            rho_dollars=rho,
            rho_prompt_dollars=sim.rho_prompt_dollars,
            sim_pmax_mw=round(sim.peak_power_mw, 2),
            sim_energy_mws=round(sim.energy_mws, 2),
            sim_fwhm_s=round(sim.fwhm_s, 4) if sim.fwhm_s else None,
            sim_delta_tf_c=round(sim.delta_tf_c, 1),
            sim_peak_tf_c=round(sim.peak_tf_c, 1),
            nf_pmax_mw=round(sim.nf_peak_power_mw, 2),
            nf_energy_mws=round(sim.nf_energy_mws, 2),
            nf_fwhm_s=round(sim.nf_fwhm_s, 4),
            exp_count=len(matches),
            exp_pmax_median_mw=round(_median(powers), 2) if powers else None,
            exp_pmax_mean_mw=round(sum(powers) / len(powers), 2) if powers else None,
            exp_pmax_min_mw=round(min(powers), 2) if powers else None,
            exp_pmax_max_mw=round(max(powers), 2) if powers else None,
            exp_energy_median_mws=round(_median(energies), 2) if energies else None,
            exp_fwhm_median_s=round(_median(fwhms), 4) if fwhms else None,
            exp_t1_median_c=round(_median(temps), 1) if temps else None,
        )
        points.append(point)

    # Scaling exponents across prompt critical regime (prompt rho >= 0.20 $)
    fit_points = [p for p in points if p.rho_prompt_dollars >= 0.15]
    sim_prompt_rhos = [p.rho_prompt_dollars for p in fit_points]
    sim_pmaxs = [p.sim_pmax_mw for p in fit_points]
    sim_energies = [p.sim_energy_mws for p in fit_points]

    exp_prompt_rhos = [p.rho_prompt_dollars for p in fit_points if p.exp_pmax_median_mw]
    exp_pmaxs = [p.exp_pmax_median_mw for p in fit_points if p.exp_pmax_median_mw]
    # energy fits use their own x values: a bin with peak power but no energy must not shift the pairing
    exp_e_rhos = [p.rho_prompt_dollars for p in fit_points if p.exp_energy_median_mws]
    exp_energies = [p.exp_energy_median_mws for p in fit_points if p.exp_energy_median_mws]

    sim_p_slope = _log_polyfit_slope(sim_prompt_rhos, sim_pmaxs)
    sim_e_slope = _log_polyfit_slope(sim_prompt_rhos, sim_energies)
    exp_p_slope = _log_polyfit_slope(exp_prompt_rhos, exp_pmaxs)
    exp_e_slope = _log_polyfit_slope(exp_e_rhos, exp_energies)

    # No automatic verdict (review 2026-09-26). Report the whole picture instead of one point.
    ratios = [p.sim_pmax_mw / p.exp_pmax_median_mw for p in points if p.exp_pmax_median_mw]
    note = ("No automatic verdict: experimental bins pool core configurations without screening or condition "
            "matching. Sim/exp median peak-power ratios span "
            + (f"{min(ratios):.2f}-{max(ratios):.2f}" if ratios else "n/a")
            + " across the sweep. See docs/reviews/2026-09-26-m1-go-review.md.")

    return ComparisonSummary(
        library_id=lib.id,
        num_simulations=len(points),
        total_experimental_pulses_matched=len(matched_ids),
        pmax_scaling_exponent_sim=round(sim_p_slope, 3),
        pmax_scaling_exponent_exp=round(exp_p_slope, 3),
        energy_scaling_exponent_sim=round(sim_e_slope, 3),
        energy_scaling_exponent_exp=round(exp_e_slope, 3),
        verdict=None,
        note=note,
        pmax_ratio_min=round(min(ratios), 3) if ratios else None,
        pmax_ratio_max=round(max(ratios), 3) if ratios else None,
        points=points,
    )


def format_comparison_table(summary: ComparisonSummary) -> str:
    """Format comparison summary into an aligned ASCII table."""
    lines = [
        f"==========================================================================================================================",
        f" JSI TRIGA Mark II Pulse Simulation vs Experimental Benchmark Comparison (Milestone 1)",
        f" Library: {summary.library_id} | Total Matched Pulses: {summary.total_experimental_pulses_matched} | Verdict: none (see note)",
        f"==========================================================================================================================",
        f" Rho($) | Prompt($) | Sim Pmax (MW) | Exp Pmax Med (MW) | Sim E (MWs) | Exp E Med (MWs) | Sim FWHM (ms) | Exp FWHM (ms) | Exp N",
        f"--------------------------------------------------------------------------------------------------------------------------",
    ]
    for p in summary.points:
        exp_p = f"{p.exp_pmax_median_mw:10.1f}" if p.exp_pmax_median_mw is not None else "       N/A"
        exp_e = f"{p.exp_energy_median_mws:10.2f}" if p.exp_energy_median_mws is not None else "       N/A"
        sim_f = f"{p.sim_fwhm_s*1000:8.1f}" if p.sim_fwhm_s else "     N/A"
        exp_f = f"{p.exp_fwhm_median_s*1000:8.1f}" if p.exp_fwhm_median_s else "     N/A"
        lines.append(
            f"  {p.rho_dollars:4.2f} |      {p.rho_prompt_dollars:4.2f} |    {p.sim_pmax_mw:10.2f} | {exp_p}        |  {p.sim_energy_mws:10.2f} | {exp_e}      |      {sim_f} |      {exp_f} | {p.exp_count:5d}"
        )
    lines.extend([
        f"--------------------------------------------------------------------------------------------------------------------------",
        f" Power Scaling: Simulated Pmax ~ (rho-1)^{summary.pmax_scaling_exponent_sim:.2f} | Experimental Pmax ~ (rho-1)^{summary.pmax_scaling_exponent_exp:.2f}",
        f" Energy Scaling: Simulated Energy ~ (rho-1)^{summary.energy_scaling_exponent_sim:.2f} | Experimental Energy ~ (rho-1)^{summary.energy_scaling_exponent_exp:.2f}",
        f" Note: {summary.note}",
        f"==========================================================================================================================",
    ])
    return "\n".join(lines)


def save_comparison_report(summary: ComparisonSummary, output_path: Path = DEFAULT_REPORT_PATH) -> None:
    """Save structured comparison summary as JSON."""
    data = asdict(summary)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run JSI TRIGA pulse comparison and M1 validation.")
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY_PATH, help="Path to reactor library directory")
    parser.add_argument("--core", type=str, default=None, help="Filter experimental pulses by core configuration (e.g. 253)")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH, help="Path to save output JSON report")
    args = parser.parse_args()

    summary = run_pulse_comparison(library_path=args.library, core=args.core)
    print(format_comparison_table(summary))
    save_comparison_report(summary, args.output)
    print(f"\nReport written to {args.output}")


if __name__ == "__main__":
    main()
