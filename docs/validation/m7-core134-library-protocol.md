# M7 core 134 library: rod worths and fresh-fuel feedback against the 1994 benchmark (sixth protocol, written before any run of it, 2026-10-06)

It follows the five earlier M7 protocols, the core 134 gate (`core134-library-gate.md`) and the full sweep that built `libraries/triga-jsi-134-openmc` (fresh fuel, 41 OpenMC cases, status `experimental`). Its purpose is to check the new library against the measurements of **its own core** (Mele, Ravnik, Trkov, *Nucl. Technol.* 105 (1994), transcribed in `validation/data/jsi-core134/`), before any power ascension comparison is made on it. It adds no fitted number and changes nothing in the library. Nothing here has been run.

## The data

- **Table VI**, control rod worths by the rod-exchange method, pcm against cm inserted (0 = top of the active core) for the regulating (R), shim (C), safety (S) and transient (T) rods, and the worth of the rod completely inserted. The regulating rod's calibration is stated to be good to < 10 %; the others are not given an uncertainty. The regulating rod is the only one that moves in the power ascension.
- **Table IX**, the 14-step power ascension (cooling off, T0 21.6 °C, B-ring thermocouple temperatures, γ_B = 1.525, γ_A = 1.575, the reliable range to 100 °C average fuel temperature), as in the fifth protocol.
- Uncertainties as in the fifth protocol (reactivity ±5 pcm per step, power defect ±5 %, temperature ±1 °C below 50 °C, γ ±5 % each).

## Disclosure: what was seen before writing

This protocol is **not blind**.

- The gate: the library's model is 323 pcm above critical at the measured critical rods (the calibration offset in the library), and its regulating rod worth over the first 28.7 cm is 2170 pcm against the measured 2155 pcm (the difference of two OpenMC cases). Core 133 and core 134 reactivity errors of +364, +323 and +471 pcm.
- The fifth protocol's results for the burned libraries of cores 242 and 246 on the same Table IX (feedback A plausible: model 9–14 % low at 99 °C).
- **The library's feedback tables** (read when the library was exported): fuel temperature −657 pcm at 400 K, −1547 at 500 K, −2542 at 600 K, −4794 at 800 K relative to 294 K; coolant +259 pcm at 313.15 K and +440 at 333.15 K. So the fresh-fuel slope over 294–400 K is about −6.2 pcm/K, against −7.8 and −8.1 for the burned libraries. **Whether that agrees with Table IX has not been computed.** A first look suggests the fresh table is close to the first measured step (about −6.3 pcm per mean fuel kelvin) and weaker than the later ones (−7.3, −7.8, −8.3).
- The export's own joint-state checks: at one held-out joint state the separable model's reactivity error was 350 pcm (the export report lists six such states; not examined beyond that one).
- **Not seen:** the library's rod worth curves against Table VI (for any rod), the per-step comparison of the new feedback table with Table IX, the library's heat transfer (a constant assumed `hA` 3000 W/K, not fitted).

## The question

Does the core 134 library reproduce the measured control rod worth curves, above all the regulating rod's, and the measured reactivity loss with fuel temperature of the power ascension, within the benchmark's stated scale?

## Model quantities

- **Rod worth curve** of rod `r` inserted `d` cm: `W_r(d) = ρ_r(x_0) − ρ_r(x(d))` from the library's rod table (absolute reactivity, pcm = 1e5 ×), with `x(d) = 1 − d/38.1` for the fuel-followed rods (regulating, shim, safety) and `x(d) = (7/9)(1 − d/38.1)` for the transient rod, whose table also covers the travel above the core, with `x_0 = 1` for all four (fully withdrawn). The library's tables hold the other rods at the reference state (transient, shim and safety out, regulating 28.7 cm in), the measurement used another rod to compensate the excess reactivity; this difference is a stated limit of the comparison for the shim, safety and transient curves; it does not affect the regulating rod's own curve, where the other rods are out in both.
- **Measured completely inserted:** R 2550 pcm at 38 cm (the table prints 2252 for "completely inserted", a typographical error, see the data README; the 38 cm row is used), C 2430, S 3440, T 2270.
- **Reactivity loss at step i of Table IX** exactly as in the fifth protocol: mean fuel temperature `T̄_i = T0 + (T_B,i − T0)/γ_B`, water warming profile, the library's `fuelTemp` and `coolantTemp` tables.

## Metrics and bands (fixed now)

| # | Quantity | good | plausible | fails |
|---|---|---|---|---|
| **R1** | per rod: ratio of the model's total worth (at 38 cm, or the completely inserted value for C, S and T at 38 cm) to the measured one | 0.90–1.10 | 0.80–1.25 | outside |
| **R2** | per rod: the maximum difference over the rows 1–38 cm between the model's and the measured worth, each divided by its own total | ≤ 0.05 | ≤ 0.10 | above |
| **R3** | the regulating rod only: the difference between the model and the measured worth at 28.7 cm (the critical position; measured 2155 pcm by interpolation of Table VI), pcm | ≤ 108 pcm (5 %) | ≤ 215 pcm (10 %, the stated calibration error) | above |
| **A'** | reactivity loss of the library's tables at the measured mean fuel temperatures against the measured cumulative Δρ at the **reliable steps 1–7**; per step; the label is the worst over the steps (bands as metric A of the fifth protocol) | ≤ max(10 % of the measured, 10 pcm) | ≤ max(25 %, 25 pcm) | above |
| **F** | reported only: the cumulative loss at step 13 (measured 1276.3 pcm), the slopes of the fuel and coolant tables over the first interval, the library's constant `hA` and the mean fuel rise it gives at 45–250 kW against the measured one, the calibration offset | | | |

Labels in R1–R3 are given per rod; the **regulating rod's labels are the ones the decision uses**. A' is evaluated for the sensitivities TB with γ_B (primary) or TA with γ_A, and the three water warming profiles of the fifth protocol (linear in the step, none, proportional to the cumulative power); the label is the worst over them, with the best beside it and the primary line on its own.

## Decision process

1. **R1 to R3 good or plausible for the regulating rod, and A' good or plausible:** the library reproduces what the power ascension of its own core needs (the regulating rod's reactivity curve and the fuel feedback), within the stated scale. A seventh protocol may then compare the power ascension itself (heat transfer and defect), written before its run, with the heat transfer law as the thing to fit on part of the data and test on the rest.
2. **R1 to R3 fail for the regulating rod:** the library's rod curve is not usable for the power ascension; record the size and shape of the difference and stop.
3. **A' fails:** the fresh-fuel feedback table does not reproduce the measured loss; record it, and the fuel hydrogen content (the gate found about 200 pcm per 0.01 of H/Zr) and the temperature conversion are the first suspects. The seventh protocol is not written until this is understood.
4. **R1 or R2 fail for the shim, safety or transient rod only:** record it; those rods do not move in the power ascension, and nothing changes for it.
5. **In every case** nothing in the library is changed and its status stays `experimental`.
6. **Not tried after seeing the results:** other conversions of the rod positions, other water profiles or step ranges, a correction for the compensating rod of the rod-exchange method, any fit of the library to this data.

## Implementation (to be written after this protocol)

`validation/m7_core134_library.py` reusing `m7_fuel_coefficient` (the feedback comparison) and reading `validation/data/jsi-core134/rod_worths.csv`; a synthetic test (known linear rod tables, known worths); report `validation/m7_core134_library_report.json`; results note `docs/validation/m7-core134-library-results.md`. The script is run once.

## Limits, repeated

The library's rod tables are interpolated on a coarse position grid (8 points for the regulating, shim and safety rods, 6 for the transient rod); the rods' compensation in the measurement differs from the library's reference state; the temperature conversion and the water profile are assumptions; the library has an unexplained reactivity offset of 323 pcm (calibrated out) and an input uncertainty of about 500 pcm from the fuel composition (the 1994 paper's own estimate for 235U, and the hydrogen content); the benchmark core's burnup state is fresh while the 242 and 246 libraries are burned, so the comparison of A' with the fifth protocol's A is a comparison of two fuel states, not of two models of the same fuel.
