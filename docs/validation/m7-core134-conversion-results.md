# M7 core 134 temperature conversion: results (2026-10-06)

Protocol: `m7-core134-conversion-protocol.md` (eighth protocol; not blind, see its disclosure). Script: `validation/m7_core134_conversion.py`, run once (`python -m validation.m7_core134_conversion`; no OpenMC). Full output: `validation/m7_core134_conversion_report.json`. Data: `validation/data/jsi-core134/` and `libraries/triga-jsi-134-openmc`. Every metric is reported. Nothing was changed after seeing the results.

## Result in one paragraph

**The independent evidence supports the paper's conversion; it does not explain the weak feedback. The decision is case 2 of the protocol: the feedback is too weak, and the next protocol tests OpenMC's treatment of the fuel temperature, not the measurement.** The radial factor recomputed from the paper's own Table VIII is 1.19 (A ring) and 1.14 (B ring) at 250 kW, "plausible" against the paper's 1.26 and 1.22, and **1.27 and 1.23 at 125 kW, "good"**: the paper's values are those of the 125 kW distribution. The model's own power shapes give an axial factor of 1.24–1.26 at the thermocouples against the paper's 1.25, and a total conversion of 1.47–1.74 against 1.525–1.575. With any independent conversion the library's what-if reactivity loss still fails at steps 5–7 and in the aggregate (steps 3 and 4 become plausible with the Table VIII conversion; the model-based conversion fails from step 2): 15 % of the shortfall at step 7 is removed with the Table VIII conversion and **none** (it gets worse) with the model's. The conversion the feedback would need, 1.04–1.30 depending on the step, is far from every independent estimate, and it **falls from 1.30 at step 1 to 1.04 at step 7**: the discrepancy is not a constant factor.

## G1: the radial factor from Table VIII (cooling on)

| Quantity | 250 kW | 125 kW | Paper |
|---|---|---|---|
| mean fuel temperature (primary weighting) | 208.7 °C | 143.5 °C | |
| γ_r, A ring (A-1) | 1.189 plausible | 1.267 good | 1.26 |
| γ_r, B ring (B-5 at 250 kW; B-2 at 125 kW, the only value given) | 1.135 plausible | 1.226 good | 1.22 |

- Primary line (T0 21.6 °C, element-count weights with the three followers, 250 kW): **plausible** for both; best over the sensitivities good, worst plausible.
- Over the 18 sensitivity combinations (T0 20, 21.6, 25 °C; weights by element count with and without the followers, and by area; 250 and 125 kW): A 1.18–1.28, B 1.13–1.24. The weights and T0 change γ_r by less than 0.02; the power is what matters: **at 125 kW the recomputed values match the paper's to 0.01**.
- Reading: the paper's γ_r agrees with the 125 kW distribution of its own Table VIII, not the 250 kW one. The radial peaking falls with power (the A ring is 1.27 times the mean rise at 125 kW and 1.19 at 250 kW; cooling and the exponent of the heat transfer flatten it). The reliable steps of Table IX are at 5–95 kW, where the peaking is, if anything, higher than at 125 kW, so for those steps the paper's 1.22–1.26 is a fair value.

## G2: the model's power factors (library shapes at the reference state)

| Element | F_r (relative element power) | F_z (midplane density over the element mean) | γ_model, n = 0 | γ_model, n = 0.22 | Paper | Label (n = 0 / 0.22) |
|---|---|---|---|---|---|---|
| A-1 | 1.294 | 1.240 | 1.605 | 1.474 | 1.575 | good / good |
| B-5 | 1.379 | 1.260 | 1.738 | 1.573 | 1.525 | plausible (13.9 %) / good |

- All eight combinations (the exponent and the axial choice) are good or plausible; worst plausible, best good. The axial factors of 1.24 and 1.26 are an independent confirmation of the paper's 1.25.
- The power factor of the B-5 element (1.38) is above the paper's radial temperature factor (1.22): the temperature factor of the paper includes the cooling difference between rings.

## G3: the conversion the library's feedback would need (diagnostic, never applied)

| Step | Mean fuel (°C) at the paper's γ_B | Implied γ, B ring | Implied γ, A ring |
|---|---|---|---|
| 1 | 29.5 | 1.30 | 1.30 |
| 2 | 38.9 | 1.22 | 1.22 |
| 3 | 51.5 | 1.17 | 1.19 |
| 4 | 66.8 | 1.14 | 1.18 |
| 5 | 78.6 | 1.08 | 1.15 |
| 6 | 89.3 | 1.05 | 1.16 |
| 7 | 98.7 | 1.04 | 1.15 |
| mean | | **1.143 = 0.75 × the paper's 1.525 (differs)** | **1.193 = 0.76 × 1.575 (differs)** |

The implied conversion is far below every independent estimate at every step and decreases with temperature: a single constant γ cannot reconcile the library's linear 294–400 K table with a measurement whose slope grows with temperature.

## G4: labels of the reactivity loss at steps 1–7 (library tables, default composition; model/measured, pcm)

| Step | Paper's γ_B 1.525 | Table VIII radial × paper axial, γ_B 1.419 | Model power factors, γ_B 1.738 |
|---|---|---|---|
| 1 | 41/50 good | 45/50 good | 35/50 plausible |
| 2 | 92/119 plausible | 100/119 plausible | 79/119 fails |
| 3 | 162/218 fails | 176/218 plausible | 140/218 fails |
| 4 | 249/345 fails | 270/345 plausible | 215/345 fails |
| 5 | 315/461 fails | 341/461 fails | 271/461 fails |
| 6 | 373/564 fails | 405/564 fails | 322/564 fails |
| 7 | 424/666 fails | 460/666 fails | 366/666 fails |
| **Primary label** | **fails** (best plausible) | **fails** (best plausible) | **fails** (best plausible) |
| Step 7 shortfall removed | 0 % | 15 % | −24 % (worse) |

## Reading (interpretation, separate from the protocol's labels)

1. **The conversion is not the explanation.** The two independent estimates bracket the paper's value (1.42 and 1.74 against 1.525), the axial factor agrees to 1 % with the paper's, and the radial factor reproduces the paper's at 125 kW. A conversion that would remove the shortfall (about 1.1) is 25 % below the lowest estimate.
2. **The model's feedback is too weak, and the shortfall is not a constant factor.** The implied conversion falls from 1.30 to 1.04 with temperature, which says the model needs relatively more feedback at 60–100 °C than at 30 °C. In the nine OpenMC runs of the seventh protocol the model's own slope from 294 K rises with temperature (−4.65, −6.10, −6.41 pcm/K at 330, 372 and 400 K, each with ±0.4 to ±1.2), but the measurement's rises faster (−6.3 at step 1 to −8.3 pcm per mean fuel kelvin at step 4).
3. **What this leaves** (each needs its own dated protocol): OpenMC's temperature treatment of the zirconium hydride thermal scattering and of the Doppler broadening in the fuel (the pipeline interpolates the nuclide data between 294, 600 and 900 K and uses the ZrH tables at the nearest temperatures); whether ENDF/B-VIII.0's ZrH scattering law gives a fuel temperature coefficient as strong as fresh TRIGA fuel really has; a model with a finer table. These are model questions, not measurement ones.
4. **Practical consequence for the power ascension.** The comparison of the power ascension itself on this library would carry the 37–40 % feedback shortfall, which the independent conversions cannot remove; it would test the feedback and the heat transfer together.

## Decision (protocol)

- **Case 2:** the paper's conversion is supported by independent evidence (G1 and G2 good or plausible), G3 differs (0.75 × the paper's) and G4 fails. **The feedback is too weak by the implied factor and the next protocol tests OpenMC's fuel temperature treatment.** No conversion is adopted for later work other than the paper's own.
- **Nothing in any library changes**; the status stays `experimental`.
- **Not tried after seeing the results (per the protocol):** other weightings, T0, exponents or bins than those listed, a fit of γ to the feedback (the implied conversion is a diagnostic only).

## Limits, repeated

Table VIII has one or two values per ring; the axial factor of the paper cannot be recomputed from the paper's data (the model's agrees); the power factors are the model's; the heat flux scaling from a power factor to a temperature factor is the earlier protocols' approximation; Table VIII is with cooling on and Table IX with cooling off. The implied conversion uses the library's tables as they are (linear between 294 and 400 K) and the assumed linear water warming.

## Erratum (Codex review, 2026-10-06)

- **The "best plausible" label of G4 comes from sensitivities the protocol does not list.** The protocol's primary water profile is the linear one and its listed sensitivity for C3 is the A-ring thermocouple. The script also evaluated the "none" and "cumulative" profiles and included them in the best label. Restricted to the protocol's linear profile, both thermocouples **fail for all three routes**; the decision uses the primary and worst labels and is unchanged.
- **G3 with a missing root.** The script averaged the roots it found and labelled the partial mean. It now marks G3 incomplete when a root is missing and reports the partial mean separately (`implied.*.complete`, `partialMean`); the decision then returns "unresolved". Every root exists in this run, so no number changed.
