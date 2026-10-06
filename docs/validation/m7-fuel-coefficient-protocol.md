# M7 low-temperature fuel and isothermal coefficients: comparison protocol (fifth protocol, written before any run of it, 2026-10-06)

It follows the four earlier M7 protocols and their results. Those compared the library with one power ascension and fitted the heat transfer law to it. This protocol checks the library's **temperature feedback coefficients at room temperature** against an independent measurement, with stated uncertainties, from a different experiment. It adds no fitted number and changes nothing in the library. Nothing here has been run.

## The data (read; the only measured values used)

Žagar, Ravnik and Trkov, "Isothermal temperature reactivity coefficient measurement in TRIGA reactor", *Nuclear Energy for New Europe 2002*, Kranjska Gora (OSTI 20542841; local copy in `research/VIRTUAL REACTOR`). Core configuration **176**: 54 standard stainless-steel clad TRIGA fuel elements, three fuelled-follower control rods, one transient rod, seven irradiation channels and the neutron source; xenon-free after more than a week of shutdown. Reactivity by the digital reactivity meter DMR-043.

| Quantity | Value | Conditions |
|---|---|---|
| Isothermal coefficient | **+3.4 ± 0.3 and +3.6 ± 0.3 pcm/°C** (two runs; the paper's Table 1 gives +3.5 ± 0.3) | fuel, cladding and water within 0.5 °C, at 15–25 °C (fuel 17.8 → 21.4 °C in the first run), power 100 W and 5 W; temperature uncertainty 0.1 °C |
| Fuel temperature coefficient | **−4.8 ± 0.5 pcm/°C**, defined against the fuel temperature of the **B ring** | fuel temperatures around 22 °C, power about 600 W |
| Context | the same paper quotes the 1994 benchmark paper's indirectly measured fuel coefficient as having a relative error of **25 % at room temperature and 40 % at 100 °C**, which is the realistic scale of this type of measurement | |

Also read, not used here: fresh-core criticality, excess reactivity and rod worths (Jeraj et al. 1996, from the 1994 paper).

## Disclosure: what was seen before writing

This protocol is **not blind**, but it is fixed before the model's coefficients at the relevant temperature are computed.

- Everything in the earlier results, including that the library's fuel temperature coefficient at low temperature is about **−7.8 pcm/K per kelvin of mean fuel temperature** (quoted in the heat-transfer results), and the fitted law (h0 1289 and 1383 W/K, n 0.217 and 0.233) and thermocouple peaking (F_tc 1.28 and 1.39) now in the libraries.
- **A rough conversion made in discussion:** with a B-ring thermocouple rising about 1.3 times the mean fuel temperature, −7.8 per mean kelvin corresponds to about −6 per B-ring kelvin, against −4.8 ± 0.5 measured. **The expected result for the fuel coefficient is therefore "plausible" at best, with the model about 25 % too steep.** The isothermal coefficient has not been looked at.
- **Not seen:** the library's table values segment by segment, its coolant temperature coefficient, any isothermal result.

## The question

Does the library's fuel temperature coefficient at room temperature, converted to the quantity the experiment measured (per B-ring thermocouple kelvin), agree with −4.8 ± 0.5 pcm/°C, and does the model's isothermal coefficient (fuel plus coolant table together) agree with +3.5 ± 0.3 pcm/°C?

## Model quantities (library tables are absolute reactivity; pcm = 1e5 ×)

- **Fuel slope** `s_f(T)`: slope of `reactivity.fuelTemp` at T (pcm per kelvin of mean fuel temperature). **Primary: the secant between 294 K and 300 K** (the table starts at 294 K, so the experiment's 291–295 K mostly lies below it: the first segment is used as an extrapolation and the result is labelled so). Sensitivities: the first tabulated segment's own slope, and the secant 294–305 K.
- **Coolant slope** `s_c(T)`: the same for `reactivity.coolantTemp` (kelvin of pool temperature), same three definitions.
- **Isothermal coefficient:** `s_iso = s_f + s_c`, both tables at the same temperature (as in the experiment).
- **Conversion of the fuel slope to the B-ring temperature:** at the experiment's power `P` the mean fuel rise over the pool is the library's law, `dT = (P · 100^n / h0)^(1/(1+n))`, and the thermocouple rise is the chain of `validation/m7_hot_element.py` (`chain_temperatures`: peaking `F`, conductivity 17.6 W/m·K, `r_tc` = the zirconium rod radius, element count from the library's shape). The ratio `r_B = (T_tc − T_pool) / dT` converts: `s_f,B = s_f / r_B`. The primary uses **P = 600 W** and **F = the core's F_tc from the second hot-element protocol (1.276 for core 242, 1.390 for core 246)**.

The library's `hA`, `exponent` and `dTRef` are read from the shipped manifests.

## Metrics and bands (fixed now)

| # | Quantity | Prediction minus measurement | good | plausible | fails |
|---|---|---|---|---|---|
| **A** | fuel coefficient per B-ring kelvin, `s_f,B` against −4.8 ± 0.5 | absolute difference, pcm/°C | ≤ 1.0 (two standard deviations of the measurement) | ≤ 2.4 (half the value; twice the 25 % the 1994 paper's method carries) | above 2.4 |
| **B** | model isothermal coefficient `s_iso` against +3.5 ± 0.3 | absolute difference, pcm/°C | ≤ 0.6 | ≤ 1.75 | above 1.75 |
| **C** | reported only: `s_f` per mean kelvin, `s_c`, `s_iso`, `r_B` and the sign of each, for every sensitivity | | | | |

The labels are the **worst over the sensitivities** with the best beside them; the primary line is given on its own.

## Sensitivities (the only ones)

1. Slope definition: secant 294–300 K (primary), first tabulated segment, secant 294–305 K.
2. Conversion peaking `F`: the core's F_tc (primary), 1.0 (no peaking) and 1.9 (the library's B-ring shape factor).
3. Power for the conversion: 600 W (primary), 400 W and 800 W.
4. The measurement value used for B: +3.5 (primary), +3.4 and +3.6 (the two runs).
5. Both libraries (cores 242 and 246) separately; the experiment is core 176 and neither library, so a label is a statement about the library's coefficient, not about that core.

## Decision process

1. **A and B good or plausible:** the library's room-temperature feedback agrees with a second, independent measurement within the 25 % realistic scale, so the coefficient is not the likely reason for the earlier power-defect disagreement. The shipped source strings are unchanged; the library stays `experimental`.
2. **A fails, B good or plausible:** the fuel coefficient is off by more than a measurement with this method can explain, while the coolant side and the sum are not. Record the sign and size; the library's fuel temperature table goes on the list for a re-derivation (burnup or fuel composition) as a separate, dated protocol. Nothing is refitted here.
3. **B fails (whatever A is):** the coolant (water) temperature coefficient is the suspect; a positive isothermal coefficient at room temperature depends on the water's moderator density effect, which the library may not carry at 294–300 K. Record it; no change.
4. **In every case:** no fitted number, table or heat transfer constant changes; status stays `experimental`.
5. **Not tried after seeing the results:** other slope definitions, conversion factors or powers than those listed, an extrapolation of the table below 294 K, a fit of any library number to this measurement.

## Implementation (to be written after this protocol)

`validation/m7_fuel_coefficient.py` reusing `m7_hot_element.chain_temperatures` and the library loader; a synthetic-library test (known linear tables, known law, known conversion); report `validation/m7_fuel_coefficient_report.json`; results note `docs/validation/m7-fuel-coefficient-results.md`. The script is run once.

## Limits, repeated

The measurement is core 176 (54 standard elements, a burnup unknown here), not core 242 or 246 (mixed, burned); the library tables begin at 294 K, above most of the experiment's fuel temperatures (17.8–21.4 °C), so the comparison extrapolates by up to about 3 K; the fuel coefficient was derived through a B-ring temperature and a power-dependent conversion that the paper says carries a relatively large uncertainty; the conversion uses the thermocouple peaking found in the second hot-element protocol, which was itself fitted to that exercise; the measured isothermal coefficient is a small sum of large opposing terms. A "good" label means the library is consistent with this measurement at the stated scale.
