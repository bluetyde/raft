# M7 core 134 temperature conversion: independent check (eighth protocol, written before any run of it, 2026-10-06)

It follows the seventh protocol (`m7-core134-feedback-protocol.md`) and its results: the fresh-fuel OpenMC model gives a fuel temperature coefficient of about −6.2 pcm/K, 37–40 % too weak at steps 4–7 of the 1994 power ascension **if** the measured mean fuel temperature is taken from the paper's conversion, `ΔT_thermocouple = γ ΔT̄` with `γ_B = 1.525` and `γ_A = 1.575`. A rough estimate made while writing the results says that reconciling the two without changing the model would take a conversion near 1.0–1.1. This protocol tests the conversion against evidence that does not use the feedback tables: the paper's own ring temperatures and the library's power shapes. It changes nothing in any library. Nothing here has been run.

## The conversion under test

The paper (Section III.F, Eqs. 5–10) defines the measured temperature rise at a thermocouple as `ΔT(r,z) = γ_r γ_z ΔT̄` with `ΔT̄` the volume-averaged fuel temperature rise of the whole core. It takes `γ_r` from the radial temperature distribution of Fig. 5 (A ring 1.26, B ring 1.22) and `γ_z = 1.25` from the axial power distribution at the thermocouples' half-height; both are quoted with ±5 %. Only the radial temperatures are tabulated (Table VIII); the axial value comes from flux measurements not reproduced.

## Disclosure: what was seen before writing

This protocol is **not blind**.

- The seventh protocol's results, and its rough estimate that the library's feedback and the paper's γ would agree for a γ of about 1.03–1.1.
- **A quick calculation of the radial factor** from Table VIII, made while designing this protocol (element-count weights over the 48 fuel positions, the three followers given their ring's temperature, T0 = 21.6 °C, 250 kW): the volume-mean fuel temperature is about 208.7 °C, so `γ_r` is about **1.19 for A-1 (244 °C) and 1.14 for B-5 (234 °C)**, against the paper's 1.26 and 1.22: 5–7 % lower. With the paper's `γ_z = 1.25` that gives a total conversion of about 1.42 for B-5, between the paper's 1.525 and the 1.0–1.1 the feedback seems to need. **Not computed in detail, no other sensitivities looked at.**
- The library's shape arrays for core 134 have been written (48 fuel positions including the three followers, 15 axial bins of 2.54 cm and one bin below the core); **no power factor was extracted from them**.
- **Expected result:** with an independent conversion of about 1.4, the library's what-if reactivity loss at step 7 rises from 417 pcm to about 470 pcm against 666 measured; it stays "fails". The conversion is expected to explain a part of the shortfall, not all of it.

## The three computations

**C1: the radial factor from Table VIII (the paper's own data, recomputed).** At 250 kW and at 125 kW (Table VIII, cooling on): the temperature of every fuel position of core 134 from the ring values, `T̄ = Σ_positions T / N` over the 48 fuel positions of `loading_map.json` (45 elements and the three followers), with the ring values A 244, B the mean of B-2 and B-5, C the mean of C-8 and C-9, D the mean of D-11 and D-13, E the single E-14 value (and the 125 kW column; the ring D, E values of 125 kW use the single values given). `γ_r(A) = (T_A-1 − T0)/(T̄ − T0)` and `γ_r(B) = (T_B-5 − T0)/(T̄ − T0)`.

**C2: the model's power factors for the same two elements (the library's shapes).** From `libraries/triga-jsi-134-openmc` shape arrays at the reference state: `F_r(e) =` the element's total power fraction times the number of fuel positions (48), and `F_z(e) =` the power density of the axial bin containing the midplane divided by the element's mean over the 15 bins. The temperature factor of a thermocouple follows from the power factor by the heat flux scaling of the earlier protocols, `γ(F) = F^(1/(1+n))`; with n = 0 (the library's own constant `hA`) as primary and n = 0.22 (the fitted exponent of the burned libraries) as a sensitivity. The model total is `γ_model = γ(F_r) γ(F_z)`.

**C3: the conversion the feedback would need, and the effect of the independent ones.** For each reliable step (1–7) of Table IX, the mean fuel temperature rise with a conversion `γ` is `(T_B − T0)/γ`; with the library's own fuel and coolant tables (default composition, primary water warming profile of the fifth protocol) the loss is compared with the measured one. Reported: (a) the `γ` at which the model's loss equals the measured one at each step and its mean (the **implied conversion**, a diagnostic, never applied); (b) the labels of the loss at steps 1–7 with `γ = γ_B` of the paper, with `γ_B` from C1 × the paper's `γ_z`, and with `γ_model` from C2, using the bands of metric A' of the sixth protocol (good ≤ max(10 %, 10 pcm); plausible ≤ max(25 %, 25 pcm)).

## Metrics and bands (fixed now)

| # | Quantity | good | plausible | differs |
|---|---|---|---|---|
| **G1** | C1's `γ_r` against the paper's 1.26 (A) and 1.22 (B), absolute difference | ≤ 0.05 | ≤ 0.10 | above |
| **G2** | C2's `γ_model` against the paper's total 1.575 (A) and 1.525 (B), relative difference | ≤ 10 % | ≤ 20 % | above |
| **G3** | the implied conversion (mean over steps 1–7) against the paper's, ratio | within 0.9–1.1 | 0.8–1.25 | outside |
| **G4** | the labels of metric A' at steps 1–7 with the independent conversions (worst over the steps), B-ring primary | | | |

Sensitivities: T0 = 20, 21.6 and 25 °C and the weights (the three followers given the ring value, or excluded; and the paper-like weighting by ring area `r dr`) for C1; n = 0 and 0.22, and the axial bin choice (the bin containing the midplane, or the mean of the three central bins) for C2; the A-ring thermocouple with `γ_A` for C3. Labels are the worst over the sensitivities with the best beside them; the primary line separately.

## Decision process

1. **G1 and G2 good or plausible, and G4 good or plausible with the independent conversions:** the paper's conversion was too high; the feedback is consistent with the measurement once the independent conversion replaces it. A later protocol compares the power ascension with that conversion fixed in advance. The library's feedback tables are not changed.
2. **G1 and G2 good or plausible (the paper's conversion stands), G3 differs and G4 fails:** the conversion is supported by independent evidence, and the feedback is too weak by the factor G3 implies (the ratio of the paper's conversion to the implied one). The cause is then in the model (the OpenMC treatment of the fuel's temperature dependence); the next protocol tests that, not the measurement.
3. **G1 or G2 differs, but G4 still fails with the independent conversion:** the conversion is partly off, as the quick calculation suggests, and does not explain the shortfall; report the fraction of the shortfall it removes at step 7 (the loss at step 7 with the independent conversion against with the paper's, over the measured minus the paper's loss).
4. **In every case** nothing in any library changes, no conversion is adopted for later work without a later dated protocol, and the status stays `experimental`.
5. **Not tried after seeing the results:** other weightings, T0, exponents or bins than those listed, a fit of γ to the feedback (the implied conversion of G3 is a diagnostic only).

## Implementation (to be written after this protocol)

`validation/m7_core134_conversion.py` reading `validation/data/jsi-core134/ring_temperatures.csv`, `loading_map.json`, `power_steps.json`, the library's shape arrays (through `physics_ref.library`) and reusing `m7_fuel_coefficient` (the feedback comparison); a synthetic test (known ring temperatures, known power factors, planted implied conversion); report `validation/m7_core134_conversion_report.json`; results note `docs/validation/m7-core134-conversion-results.md`. The script is run once. No OpenMC runs are needed.

## Limits, repeated

Table VIII has one or two values per ring and a missing E-ring spread; the axial factor of the paper cannot be recomputed from the paper's data; the power factors of C2 are the model's and carry the 0.07–0.1 relative uncertainty of the shape arrays' fission tallies; the heat flux scaling from a power factor to a temperature factor is the earlier protocols' approximation; cooling is on in Table VIII and off in Table IX, so the radial temperature distribution of the first is applied to the second. A "good" or "plausible" label is a statement of consistency with the available evidence, not a measurement of the conversion.
