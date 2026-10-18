# JSI TRIGA Mark II Physical & Thermal Parameters

This directory collects physical, nuclear kinetics, and thermal-hydraulic parameters for the **Jožef Stefan Institute (JSI) TRIGA Mark II research reactor** (Ljubljana, Slovenia).

> **Status: partly checked.** The values were first gathered by an agent; a second pass (2026-09-27, task C2) checked them against the publications named below, and `parameters.json` records for every value its source and, where one was corrected, the correction (the Švajger citation, for instance, was wrong and is fixed). Values read by eye from a figure carry their precision. Anything marked `assumed` in `parameters.json` has no source.
> Known correction: `poisons.fluxPerWatt` was 4.0e7 (1000x too low, disagreeing with the library); it is now 4.0e10, still unverified.
> The first review is in `docs/reviews/2026-09-26-m1-go-review.md`; where this README and `parameters.json` differ, `parameters.json` is right.

These values serve as:
1. Starting estimates for the **Milestone 1** Python physics prototype (`physics_ref/`).
2. Input benchmarks for verifying the **Milestone 2** OpenMC transport pipeline (`pipeline/models/triga_jsi.py`).
3. Physical constants for evaluating the JSI pulse experimental database (`validation/data/jsi-pulses/`).

---

## Benchmark Sources & Citations

1. **ICSBEP Benchmark**:
   - ID: `IEU-COMP-THERM-003`
   - Title: *"TRIGA Mark II Reactor: U(20)-Zirconium Hydride Fuel Rods in Water with Graphite Reflector"*
   - Configurations: Cores 132 and 133.
   - Reference: International Handbook of Evaluated Criticality Safety Benchmark Experiments (ICSBEP), OECD Nuclear Energy Agency (2007).

2. **Fuel Material and Heat Capacity**:
   - Reference: M. T. Simnad, *"The U-ZrHx Alloy: Its Properties and Use in TRIGA Fuel"*, General Atomics Report GA-A16377 (1981); NUREG-1282 (1987).
   - Fuel Type: $\text{U-ZrH}_{1.6}$ ($12\text{ wt\%}$ U, enriched to $19.75\text{ wt\%}$ $^{235}\text{U}$, $H/Zr = 1.60$).
   - Specific heat (standard 12 wt% U element): $c_p(T) = 333 + 0.678\,(T - 274.15)\text{ J/(kg}\cdot\text{K)}$, from Vavtar and Snoj (2021) eq. 1.8, which cites Simnad (GA E-177-833, 1980).

3. **Pulsing Experiments & Thermal Feedback**:
   - Reference: I. Švajger, D. Čalič, A. Pungerčič, A. Trkov, L. Snoj, *"Evaluation of reactor pulse experiments"*, *Nuclear Engineering and Technology* 56 (2024) 1165–1203, doi:10.1016/j.net.2023.11.021; and I. Vavtar, L. Snoj, *"Evaluation of approximations in reactor pulse"*, EPJ Web of Conferences 247, 08006 (2021), doi:10.1051/epjconf/202124708006 (CC BY 4.0).
   - Effective delayed neutron fraction: $\beta_{\text{eff}} = 0.0070$ ($1\$ = 700\text{ pcm}$).
   - Prompt neutron generation time: $\Lambda \approx 40\text{ }\mu\text{s}$ ($4.0 \times 10^{-5}\text{ s}$).
   - Prompt fuel temperature coefficient: a table of $|\alpha_f|$ between 6.2 and 8.9 $\times 10^{-5}$ (Δk/k)/K at eight temperatures from 293 to 1273 K, **read by eye from Fig. 1 of Vavtar and Snoj (2021)** (precision about ±0.5 $\times 10^{-5}$ per K), with a cross-check against Table 2 of Švajger et al. (2024). See `parameters.json`.

---

## File Structure

- [`parameters.json`](parameters.json): Complete machine-readable specifications conforming to the SI units convention specified in [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md).
