# JSI TRIGA Mark II Physical & Thermal Parameters

This directory provides the verified physical, nuclear kinetics, and thermal-hydraulic properties for the **Jožef Stefan Institute (JSI) TRIGA Mark II research reactor** (Ljubljana, Slovenia).

These values serve as:
1. Ground truth for the **Milestone 1** Python physics prototype (`physics-ref/`).
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
   - Specific Heat: $c_p(T) \approx 350 + 0.35 \cdot (T - 293.15) + 2.0\times 10^{-4} \cdot (T - 293.15)^2\text{ J/(kg}\cdot\text{K)}$.

3. **Pulsing Experiments & Thermal Feedback**:
   - Reference: I. Švajger, L. Snoj, *"Evaluation of reactor pulse experiments"*, *Nuclear Engineering and Technology*, 55 (2023) 4404–4415.
   - Effective delayed neutron fraction: $\beta_{\text{eff}} = 0.0070$ ($1\$ = 700\text{ pcm}$).
   - Prompt neutron generation time: $\Lambda \approx 40\text{ }\mu\text{s}$ ($4.0 \times 10^{-5}\text{ s}$).
   - Prompt fuel temperature coefficient: $\alpha_f(T) \approx -(1.05\times 10^{-4} + 1.20\times 10^{-7}\cdot(T - 293.15))\text{ }\Delta k/k/\text{K}$.

---

## File Structure

- [`parameters.json`](parameters.json): Complete machine-readable specifications conforming to the SI units convention specified in [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md).
