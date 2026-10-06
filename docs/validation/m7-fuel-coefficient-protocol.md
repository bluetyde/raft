# M7 fuel temperature feedback and heat transfer on core 134: comparison protocol (fifth protocol, written before any run of it, 2026-10-06; amended the same day before any run)

It follows the four earlier M7 protocols and their results. Those compared the library with one power ascension (core not stated) and fitted the heat transfer law to it. This protocol uses a **second, independent set of measurements with stated uncertainties**, from the 1994 JSI benchmark (core 134) and a 2002 isothermal measurement (core 176), to check the library's **temperature feedback** and the **transferability of the heat transfer law**. It adds no fitted number and changes nothing in the library. Nothing here has been run.

**Amendment, 2026-10-06, before any run.** The first version of this protocol used only the 2002 paper, and converted the thermocouple temperature with a ratio from the earlier hot-element chain (about 1.3). The 1994 paper (obtained afterwards) gives its own conversion (1.5–1.6) and a full 14-step power ascension with uncertainties, so the protocol is rebuilt around it: the 1994 table becomes the primary data (metrics A, D, E), and the 2002 values become secondary (B, C) with the 1994 conversion. The disclosure section lists what was seen between the two versions.

## The data (the only measured values used)

**Primary: Mele, Ravnik, Trkov, *Nucl. Technol.* 105 (1994) 37–51, Table IX and Section III.F** (core 134: a fresh core of 45 fuel elements and three fuelled followers; local transcription `validation/data/jsi-core134/power_steps.json`). Fourteen power steps from 0 to 250 kW by withdrawing the regulating rod in steps of about 50 pcm, with the cooling system **off**, initial fuel and water temperature 21.6 °C, the pool warming by about 8 °C in total (no times given). Fuel temperature is read at the midplane of an element in the A ring (TA) and in the B ring (TB). The paper gives the conversion to the volume-averaged fuel temperature as `ΔT_i = γ_i ΔT̄`, with `γ = γ_r γ_z`, **γ_A = 1.26 × 1.25 = 1.575 and γ_B = 1.22 × 1.25 = 1.525**, and its uncertainties: reactivity ±5 pcm per step (about ±10 % of a step, ±1 % of the total), power ±3 %, power defect ±5 %, temperature ±1 °C below 50 °C and ±4 °C at 100 °C (absolute calibration ±3 °C), γ_r and γ_z ±5 % each, and a relative error on the fuel coefficient of **±25 % at low temperature and ±40 % at 100 °C**. The results are reliable only up to **100 °C average fuel temperature**. The paper's coefficient includes the reactivity effect of the water warming (estimated at 20 pcm of the total).

**Secondary: Žagar, Ravnik, Trkov, *Nuclear Energy for New Europe* 2002 (OSTI 20542841)**, core 176 (54 standard elements): isothermal coefficient **+3.4 ± 0.3 and +3.6 ± 0.3 pcm/°C** (Table 1: +3.5 ± 0.3) at 15–25 °C, and a fuel coefficient of **−4.8 ± 0.5 pcm/°C** against the B-ring thermocouple temperature at about 22 °C and 600 W.

## Disclosure: what was seen before writing

This protocol is **not blind**, but it is fixed before the model's feedback tables are evaluated at the relevant temperatures.

- Everything in the earlier results, including that the library's fuel temperature coefficient at low temperature is about **−7.8 pcm/K per kelvin of mean fuel temperature** (quoted in the heat-transfer results), the fitted law (h0 1289 and 1383 W/K, n 0.217 and 0.233) and the thermocouple peaking now in the libraries.
- **The whole of Table IX**, and a hand calculation on its first four steps with γ_B = 1.525: **−6.3, −7.3, −7.8 and −8.3 pcm per mean fuel kelvin** (the fuel coefficient grows in magnitude with temperature). Against the library's about −7.8, the expected result for the fuel feedback (A) is **good or plausible**.
- **A rough exponent estimate** from the TB column (power 5.3 to 250 kW), without correcting for the warming pool: **n of about 0.37 to 0.43**, above the library's 0.22–0.27. **The expected result for the exponent (D) is therefore "plausible" at best, possibly "fails"**; core 134 had no cooling, so the pool warming (about 8 K) is part of what is compared.
- The grids of the library tables (not their values): fuel temperature at 294, 400, 500, 600 and 800 K; coolant at 294, 313.15 and 333.15 K. **The first fuel knot is at 400 K, so any slope "at room temperature" is the mean over 294–400 K**, and the comparison cannot resolve what happens inside that interval.
- **Not seen:** the library's reactivity values at those knots, its coolant temperature coefficient, any isothermal result, the model's power ascension on core 134.

## The question

(1) Does the library's fuel temperature reactivity, evaluated at the mean fuel temperatures of core 134's power ascension, reproduce the measured reactivity loss within the paper's stated uncertainty? (2) Does the library's heat transfer law, scaled to the 48 fuel positions of core 134, reproduce the measured fuel temperature rise, and does a fit of the exponent to Table IX alone give the library's exponent? (3) Do the 2002 isothermal and fuel coefficients agree with the library's?

## Model quantities (library tables are absolute reactivity; pcm = 1e5 ×)

- **Mean fuel temperature at step i:** `T̄_i = T0 + (T_B,i − T0) / γ_B` (primary; `γ_A` and `T_A` as a sensitivity), with T0 = 21.6 °C = 294.75 K.
- **Water temperature at step i** (not measured): `w_i = T0 + 8 K · s_i`, with the profile `s_i` linear in the step number (primary, 1 at step 14); sensitivities: no warming (`s_i = 0`), and proportional to the cumulative power `Σ P_j / Σ P_14` (energy-like).
- **Model reactivity loss at step i** (the quantity measured as the cumulative Δρ): `D_i = −[ρ_f(T̄_i) + ρ_c(w_i) − ρ_f(T̄_0) − ρ_c(T0)] · 1e5`, from the library's `fuelTemp` and `coolantTemp` tables (linear interpolation, as the engine does).
- **Heat transfer for D and E:** the library's law `hA = h0 (ΔT / 100 K)^n`, with `h0` scaled by the ratio of fuel positions, `48 / N_lib` (N_lib = 61 for core 242, 67 for core 246 in the shape arrays; 48 = 45 elements + 3 followers, the same convention; the paper's 45 + 2.6 as a sensitivity). The model's mean rise over the water at power `P` is `ΔT_model = (P · 100^n / (h0 · 48 / N_lib))^(1/(1+n))`; the measured one is `(T̄_i − T0) − (w_i − T0)`.
- **Library slopes for B and C** (2002 data): the slope of `fuelTemp` and of `coolantTemp` over the first tabulated interval, 294–400 K (the only resolution the tables have) and, as a sensitivity, 294–500 K; `s_iso = s_f + s_c`; the fuel slope per B-ring kelvin is `s_f / γ_B` (primary) or `s_f / r_B` with `r_B` from the hot-element chain at 600 W and the core's F_tc (the first version's conversion, sensitivity).

## Metrics and bands (fixed now)

| # | Quantity | good | plausible | fails |
|---|---|---|---|---|
| **A** | model `D_i` against the measured cumulative Δρ at the **reliable steps 1–7** (average fuel temperature up to about 100 °C); per step, the error `D_i − M_i`; the label is the worst over the steps | ≤ max(10 % of M_i, 10 pcm) | ≤ max(25 % of M_i, 25 pcm) | above |
| **B** | 2002 isothermal: model `s_iso` against +3.5 ± 0.3 pcm/°C | difference ≤ 0.6 | ≤ 1.75 | above |
| **C** | 2002 fuel coefficient: `s_f / γ_B` against −4.8 ± 0.5 pcm/°C | difference ≤ 1.0 (two standard deviations) | ≤ 2.4 (half the value) | above |
| **D** | exponent `n_134` fitted by least squares of `ln(ΔT̄_i − (w_i − T0))` on `ln P_i` over **steps 4–13** (P ≥ 45 kW), `n = 1/slope − 1`, against the library's n | `|n_134 − n_lib|` ≤ 0.10 | ≤ 0.20 | above |
| **E** | ratio of the model's mean fuel rise over the water to the measured one at **steps 4–14** (45–250 kW), worst over the steps (step 14 uses TB only) | 0.85–1.15 | 0.70–1.40 | outside (reported "high" or "low") |
| **F** | reported only: the per-step coefficients `Δρ_i/ΔT̄_i` of the measurement and of the model, `s_f`, `s_c`, `s_iso`, the fitted `n_134` and its spread, the cumulative defect at step 13 (measured 1276.3 pcm) | | | |

The labels are the **worst over the sensitivities** with the best beside them; the primary line is given on its own.

## Sensitivities (the only ones)

1. TB with γ_B (primary) or TA with γ_A, for A, D and E.
2. The water warming profile: linear in the step (primary), none, proportional to cumulative power.
3. The element ratio: 48 (primary) or 47.6.
4. The slope interval for B and C: 294–400 K (primary) or 294–500 K; the B-ring conversion γ_B (primary) or `r_B` from the chain.
5. The two measured isothermal values +3.4 and +3.6 for B.
6. Both libraries (cores 242 and 246) separately. The experiments are cores 134 and 176, neither of them a library, and the libraries use **burned** fuel (uniform 23.7 MWd/kg) where core 134 is fresh, so a label states how the library's coefficients compare, not that the library is that core.

## Decision process

1. **A good or plausible:** the library's fuel temperature table gives the measured reactivity loss within the benchmark's stated scale; the fuel coefficient is not the likely reason for the earlier power-defect disagreement. **A fails:** the table is off by more than the benchmark can explain: record the sign and size; burnup (fresh against 23.7 MWd/kg) is the first candidate and is part of the core 134 library work, not tried here.
2. **D and E:** both good or plausible: the heat transfer law transfers to a second core and a second cooling condition; the source string gains "checked against core 134 (1994 benchmark), exponent n_134 = …". D fails with E good or plausible: the scale transfers, the exponent does not (the exponent is not constrained by the data used to fit it). E fails: the law is specific to the earlier exercise (cooling, element count or pool); a known limit is added to the lesson banner. In every case nothing is refitted here.
3. **B or C fail:** the water temperature coefficient (B) or the fuel coefficient at room temperature (C) is the suspect; record it, no change. The 294–400 K interval is the only resolution, so a failure there is partly a statement about the table's resolution.
4. **In every case:** no fitted number, table or heat transfer constant changes; the status stays `experimental`.
5. **Not tried after seeing the results:** other slope intervals, conversion factors, water profiles or step ranges than those listed, a fit of any library number to this data, a correction of the burned fuel table to fresh fuel.

## Implementation (to be written after this protocol)

`validation/m7_fuel_coefficient.py` reading `validation/data/jsi-core134/power_steps.json`, reusing `m7_hot_element.chain_temperatures` and the library loader; a synthetic-library test (linear tables, known law and conversion, planted exponent); report `validation/m7_fuel_coefficient_report.json`; results note `docs/validation/m7-fuel-coefficient-results.md`. The script is run once.

## Limits, repeated

The measurements are cores 134 (fresh, 45 elements, cooling off) and 176 (54 elements, burnup unknown), not cores 242 and 246 (mixed, burned); the library tables have one interval, 294–400 K, from the reference to the first knot, so the room-temperature coefficient is a mean over it; the paper's temperature conversion (γ) and the water warming profile are assumptions that carry the stated ±5 % and an unknown shape; Table IX has no times; the 2002 coefficient comes through a conversion and carries a relatively large uncertainty; scaling the heat transfer by the number of fuel positions assumes the same per-element cooling in both cores. A "good" label means the library is consistent with these measurements at the stated scale.
