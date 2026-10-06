# M7 hot-element temperature: results (2026-10-06)

Protocol: `m7-hot-element-protocol.md` (third protocol; not blind, see its disclosure). Script: `validation/m7_hot_element.py`, run once (`python -m validation.m7_hot_element`). Full output: `validation/m7_hot_element_report.json`. Every metric is reported. Nothing was changed after seeing the results.

## Result in one paragraph

**Both variants fail, for both cores: the protocol's decision is case 3, "the explanation is not found in these inputs".** The library's shape arrays predict a hot-element rise 1.6–1.8 times the measured 201 K (H-shape, as disclosed in advance). The pulse-derived peaking with the primary energy column is not credible: F_tc = 8.7 (core 242) and 7.9 (core 246), with an inter-quartile range of 3.5–33, which is not a peaking factor. The comparison does not explain the thermocouple temperature. Nothing fitted changes and the library stays `experimental`.

## Labels (primary line; worst and best over the sensitivities beside it)

| Core | G: F_tc / F_shape | H1 H-pulse (pred/meas) | H1 H-shape (pred/meas) | H2 shape (H-pulse / H-shape) |
|---|---|---|---|---|
| 242 | **fails** 4.12 (worst fails, best good; 0.58–5.09) | **fails** high 6.24 (1.08–6.58) | **fails** high 1.82 (1.44–1.87; all fail) | plausible 0.056 / plausible 0.053 |
| 246 | **fails** 4.02 (0.67–4.78) | **fails** high 5.31 (1.08–5.77) | **fails** high 1.60 (1.35–1.66; best plausible) | plausible 0.053 / plausible 0.051 |

## Stage 1: the pulses

- Pulses used: 114 of core 242 and 164 of core 246 in the database (all `core_config` values are listed in the report); 218 and 284 usable (pulse, thermocouple) pairs. The two thermocouples agree (8.8 / 8.5 and 7.7 / 8.4).
- **The primary energy column (`energy_1000pts_mws`) gives F_tc 7.9–8.7; the other two columns give 1.2–2.1** (`energy_1pct_mws` 1.28 and 1.39, `energy_tangent_mws` 1.63 and 2.09; initial temperature 20–30 °C moves each by under 15 %). The columns differ by a factor of 5–7, so at least one is on a different definition or unit from the others. Which is right is not decidable from these inputs, and the protocol fixed the primary column before the data were read.
- The "good" best-case labels in G and H1 (ratio 1.08 for H-pulse) come from the 1 % and tangent columns. They are sensitivities, not the primary line, and are reported as such.
- Library fuel fraction is 1.0, so the missing fuel-fraction factor in the protocol's formula has no effect here.

## Stage 2 and 3: shape arrays and the chain

| | core 242 | core 246 |
|---|---|---|
| Elements with power | 61 | 67 |
| Primary B element (centre bin) | B5, F_shape 2.10 | B2, F_shape 1.97 |
| B-ring centre factors | 1.74–2.10 | 1.76–1.97 |
| Fit (case 1) | h0 1289 W/K, n 0.217 | h0 1383 W/K, n 0.233 |
| H-shape predicted rise (measured 200.9 K) | 366 K | 322 K |

- **R (H-shape):** the mean fuel rise that would reproduce 201 K is 83 K (242) or 92 K (246), about half the fitted 172 / 160 K. At that rise the library's power defect would be 641 / 746 pcm, so R_α = 2.23 / 1.91 (not "consistent", band 0.8–1.25).
- R for H-pulse has no solution (even a near-zero mean rise leaves the predicted rise above 201 K), because F_tc is too large to be physical.
- **H2:** the temperature shape is plausible (0.051–0.056, just over the 0.05 good edge) in both variants, so the shape is not what fails; the magnitude is.

## Reading (interpretation, separate from the protocol's labels)

1. **The shape-array result stands as predicted:** the model's B-ring peaking (1.7–2.1) with a conduction drop of tens of kelvin puts the thermocouple at 320–370 K above the pool, not 201 K. Either the instrumented element is not a high-power one, the library's mean fuel rise (and so its fuel coefficient) is about twice too large, or the measured thermocouple under-reads. The protocol's R says the second would need a fuel coefficient of about twice the library's at 250 kW; this is **not** supported by the first protocol, where the heat transfer law matched the measured defect with the library's own coefficient, so the two lines of evidence conflict.
2. **The pulse data cannot arbitrate yet.** The energy columns disagree by a factor of 5–7, and the thermocouple rise per unit energy would have to be an order of magnitude higher than a mean-fuel adiabatic rise for the primary column to be right. The next step is to find out what `energy_1000pts_mws` is (the fetch script and README in `validation/data/jsi-pulses/`), a data-definition check, not a refit.
3. **Candidates for the next protocol,** none run: the energy-column definitions, a thermocouple that sits in a low-power element, a lower library fuel coefficient, a gap or clad conduction term.

## Decision (protocol)

- **Case 3 for both cores.** Nothing fitted is changed (not `h0`, `n`, `k`, not the fuel tables); the library status stays `experimental`.
- **Not tried after seeing the results (per the protocol):** other conductivities, thermocouple radii, axial positions or elements than those listed, a temperature-dependent conductivity, a gap conductance, any change to the shape arrays.
- **Independent of this result,** the library-format change for the heat transfer law can proceed: the law's shape and exponent do not depend on this protocol. Per the first decision rule the shipped source string should read "fitted to the reactivity; the library's mean fuel temperature rise may be too large by R_α⁻¹" only for case 1; here, with case 3, the manifest says only "fitted to the IAEA/JSI power ascension (one exercise, unknown core)".

## Limits, repeated

One steady-state exercise; unknown instrumented-element positions and core; thermocouple lag; a constant-conductivity annulus without gap or clad; a pulse database whose energy columns disagree. A "fails" here means these inputs do not account for the measurement, not that any one of them is wrong.

## Addendum: what `energy_1000pts_mws` is (data check, 2026-10-06; not part of the protocol, nothing re-scored)

- The README defines it as the energy "integrated over ±1000 points around the peak", i.e. a fixed sample window, whereas the other two columns integrate between power thresholds (1 % of peak, or tangents at 1/10 of peak). The fetch script reads the columns in the order of the source table (cells 5, 6, 7), so the columns are not mislabelled.
- Across the 666 pulses that have all three columns, the ratio of the 1000-point energy to the 1 % energy has a median near 0.4 (deciles 0.03–1.0). It is about 0.9–1.0 for the high-reactivity pulses and about 0.17 for the broad low-reactivity ones, whose power curve is wider than the window. **The 1000-point column is truncated for wide pulses**, so it understates the energy and inflates F_tc. That explains the factor 5–7 and the 8.7 and 7.9.
- The protocol's primary column was therefore the wrong choice for these cores' pulses. The 1 % and tangent columns give F_tc 1.2–2.1, the range of a plausible peaking, but that is a **sensitivity result, not a rescored primary**: the protocol fixed the primary column, and changing it after seeing the result would be a new protocol. A follow-up protocol should fix the 1 % column in advance and state that its own result has been seen.
- A check on the narrow pulses (ratio ≥ 0.9) did not help: only 2 such thermocouple readings fall in core 242 and none in core 246, below the 5-pulse minimum.

## Erratum (Codex review, 2026-10-06)

- **The shape-array peaking is frozen at the 250 kW state.** `validation/m7_hot_element.py` reconstructs F_shape once per fit case at the 250 kW state and applies it at every state (its docstring says so); the protocol text says "the mean fuel temperature of the state". Reconstructing the primary element's factor at each state (its regulating rod step and the law's fuel temperature there) leaves H1 unchanged (1.82 and 1.60) and changes the H-shape temperature shape H2 from 0.0534 to **0.0711** (core 242) and from 0.0511 to **0.0607** (core 246); both labels stay "plausible". The H-pulse metrics do not use the shape arrays and are unaffected.
