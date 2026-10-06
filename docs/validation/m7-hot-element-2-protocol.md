# M7 hot-element temperature, second attempt: comparison protocol (fourth protocol, written before any run of it, 2026-10-06)

It follows `m7-hot-element-protocol.md` and its results, including the addendum that found `energy_1000pts_mws` to be a truncated window. This protocol repeats the thermocouple-peaking comparison with the energy column fixed to the one that integrates the whole pulse, and adds checks that the first protocol did not have. Nothing here has been run.

## Disclosure: what was seen before writing

This protocol is **not blind**.

- Everything in the first hot-element results: the shape-array peaking (B ring 1.7–2.1; hot-element rise 1.6–1.8 times the measured 201 K), the fitted laws and R_α.
- **The pulse thermocouple peaking with the other two energy columns**, as sensitivities: median F_tc 1.28 (1 % column) and 1.63 (tangent column) for core 242, 1.39 and 2.09 for core 246, with initial temperature 20–30 °C moving them under 15 %. In the first run the H-pulse ratio had a best-case sensitivity of 1.08 (both cores), so **the 1 % column is expected to give an H-pulse prediction close to the measurement and G = F_tc / F_shape near 0.6–0.7, i.e. case 2 of the first protocol's decision.** The point of this protocol is to test that reading, not to confirm it by repeating it.
- The ratio of the 1000-point to the 1 % energy over the whole database (median near 0.4), and that only 2 (core 242) and 0 (core 246) thermocouple readings come from pulses where the three columns agree.
- **Not seen:** the F_tc by pulse, by half, by core transfer, by energy size, or the shape factors of any element outside the B ring.

## Change from the first protocol (the only ones)

1. **Primary energy column: `energy_1pct_mws`** (whole-pulse integral between 1 % power thresholds). Sensitivity: `energy_tangent_mws`. `energy_1000pts_mws` is dropped (known truncated for broad pulses) and reported once for the record.
2. The Stage 1 stability checks K and T below, and the element-ring comparison W, are new.
3. Everything else is unchanged and not re-chosen: `k` 17.6 W/m·K (bracket 15 and 25), `r_tc` = Ri (and 0.762 cm), B-ring candidates, the fitted law (eight combinations), the shape reconstruction at the 250 kW state, the pulse initial temperature 25 °C (20 and 30), the chain, bands, and the minimum of 5 readings.

## New checks (Stage 1, with the primary column)

| # | Quantity | Bands |
|---|---|---|
| **K1** split-half | F_tc median of the pulses with even `pulse_id` divided by that of the odd ones (per core) | **good** 0.85–1.15, **plausible** 0.70–1.40, **fails** outside |
| **K2** cross-core | F_tc median of core 242 divided by that of core 246 (the same instrumented elements are assumed; both cores come from the same reactor) | same bands |
| **T** size trend | median F_tc of the lowest energy third divided by that of the highest third (per core); an adiabatic reading is energy-independent, while lag or conduction in a slow pulse biases small, broad pulses | **good** 0.85–1.15, **plausible** 0.70–1.40, **fails** outside; direction reported |

K1, K2 and T are reported for the two thermocouples separately and together; the label is the worst of the two cores.

## The element comparison (Stage 2 extension)

**W:** the centre-plane peaking factor of every element of the library at the 250 kW state (same shape reconstruction), grouped by ring (B, C, D, E, F). Reported: for each ring, the minimum, median and maximum factor, and which ring contains the element whose factor is closest to F_tc. This is a description, not a banded metric: the position of the instrumented elements is not known, and the protocol does not claim to find it.

## Metrics carried over (same bands)

G (F_tc / F_shape), H1 (predicted / measured rise at 250 kW) for H-pulse and for H-shape, H2 (shape of the thermocouple temperature at states 4, 5 and 6) and R (implied mean fuel rise and R_α) are computed exactly as in the first protocol, with the new F_tc.

## Decision process

1. **H1 (H-pulse) good or plausible, K1, K2 and T good or plausible:** the thermocouple data say the instrumented elements carry about F_tc times the mean linear power, and the chain reproduces the measured rise with it. Then if G fails low the explanation is "the instrumented elements are not the library's hottest B element" and **the library's own fuel temperature rise needs no correction** (R_α is read as information). The fitted heat transfer law is shipped as "consistent with the hot-element data given a thermocouple peaking of F_tc (pulse database)", still `experimental`.
2. **H1 (H-pulse) good or plausible, but any of K1, K2 or T fails:** the pulse peaking is not stable, so the agreement does not count. Record it as unresolved; the thermocouple data are not a usable independent check of the peaking.
3. **H1 (H-pulse) fails:** record it. The first protocol's conflict between the shape-array peaking and the fuel coefficient stands.
4. **In every case:** nothing fitted changes (not `h0`, `n`, `k`, the fuel tables or the shape arrays); status stays `experimental`.
5. **Not tried after seeing the results:** other energy columns or pulse subsets than those listed, other conductivities, thermocouple radii or axial positions, a gap or clad term, a temperature-dependent conductivity, any change to the shape arrays.

## Implementation (to be written after this protocol)

`validation/m7_hot_element_2.py`, reusing `m7_hot_element` (stage 3 chain, shape reconstruction, decision helpers) with the column change, K1, K2, T and W; a synthetic test (known peaking per thermocouple, a planted energy trend, an unpowered ring); report `validation/m7_hot_element_2_report.json`; results note `docs/validation/m7-hot-element-2-results.md`. The script is run once.

## Limits, repeated

Thermocouple lag biases F_tc low and conduction during slow pulses spreads heat; the initial temperature of each pulse is assumed, not measured; the instrumented elements' positions and the pulse database's core assignment are not independently confirmed; the first run's result was seen, so a good H-pulse here is a check of stability, not a blind confirmation; a "good" result means the chain is consistent with the data, not that each factor is right.
