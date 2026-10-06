# M7 hot-element temperature, second attempt: results (2026-10-06)

Protocol: `m7-hot-element-2-protocol.md` (fourth protocol; not blind, see its disclosure). Script: `validation/m7_hot_element_2.py`, run once (`python -m validation.m7_hot_element_2`). Full output: `validation/m7_hot_element_2_report.json`. Every metric is reported. Nothing was changed after seeing the results.

## Result in one paragraph

**Decision case 1 for both cores: the chain with the pulse-derived thermocouple peaking reproduces the measured hot-element rise, and the peaking is stable.** With the whole-pulse energy column, F_tc is **1.28 (core 242) and 1.39 (core 246)**, the same in both cores (K2 ratio 0.92) and in both halves of the pulses (K1 0.998 and 1.005). The predicted rise at 250 kW is **237–238 K against 201 K measured (ratio 1.18–1.19, "plausible")**. The library's own B-ring peaking (1.8–1.9) still fails high (ratio 1.82 and 1.60), so the thermocouples read elements with a peaking nearer the D ring's than the B ring's. The protocol reads that as "no correction to the library's fuel rise is needed". It is a consistency result: the first run's conflict (R_α about 2) disappears once the thermocouple's own peaking replaces the library's hottest B element.

## Labels (primary line; worst and best over the sensitivities beside it)

| Core | F_tc (1 % column) | K1 split-half | T size trend | G: F_tc / F_shape | H1 H-pulse (pred/meas) | H1 H-shape | H2 (H-pulse) | R_α (H-pulse) |
|---|---|---|---|---|---|---|---|---|
| 242 | 1.276 (n 222, IQR 1.21–1.60) | good 0.998 | plausible 0.82 | **fails** 0.607 (worst fails, best good; 0.58–1.11) | **plausible** 1.18 (worst fails, best good; 1.08–1.74) | fails 1.82 | plausible 0.053 | 1.23 consistent |
| 246 | 1.390 (n 292, IQR 1.33–1.56) | good 1.005 | good 0.95 | plausible 0.705 (0.67–1.23) | **plausible** 1.19 (1.08–1.79) | fails 1.60 | plausible 0.051 | 1.25 (edge; not "consistent" by 0.0027) |

K2, core 242 over core 246: 0.918, **good**.

## Reading (interpretation, separate from the protocol's labels)

1. **The shape-array peaking was the wrong comparator, not the fuel coefficient.** The first run implied the library's mean fuel rise was about half what the data wanted (R_α 1.9–2.2). With a peaking of 1.3–1.4 the predicted rise is only 18–19 % above measured, and the implied correction R_α drops to 1.23–1.25. The earlier conflict with the heat transfer protocol is gone.
2. **Where the thermocouples sit.** W puts the element whose factor is closest to F_tc in the **D ring** (D5 at 1.274 in core 242; D12 at 1.379 in core 246). The medians by ring are B 1.76/1.91, C 1.62/1.63, D 1.26/1.35, E 1.02/1.08, F 0.81/0.80. This is a description: the position of the instrumented elements is not known, and a thermocouple lag that biases F_tc low would move it toward C.
3. **The stability checks are what make this more than the earlier near-agreement.** The peaking does not depend on which pulses are used (K1), on the core (K2) or, for core 246, on pulse size; for core 242 the lowest energy third reads 18 % lower than the highest third (T 0.82, "plausible"), the direction a lag in slow pulses would produce.
4. **The agreement is not blind.** The 1 % column's F_tc and the 1.08 best-case ratio were seen before the protocol was written, and the primary line predicts 18–19 % too hot rather than a match: the outcome is "plausible", not "good", and the worst sensitivity (the other conductivity, thermocouple radius or element choice) fails (ratios up to 1.7–1.8). The comparison is therefore a check that the numbers hang together, not a measurement of the thermocouple's position.
5. **Residual:** the chain still runs 18–19 % hot. The rise ratio H2 (0.05–0.055) is just over the 0.05 "good" edge, as in the first protocol. Candidate causes, none tested: the real conductivity or a gap term, a thermocouple reading below the pellet's hottest radius, the 25 °C assumption for the pulse initial temperature, lag.

## Decision (protocol)

- **Case 1 (both cores):** the library's fuel temperature rise needs no correction; the heat transfer law is shipped as "consistent with the hot-element data given a thermocouple peaking of F_tc (pulse database)" in the library's source string (1.28 and 1.39 for cores 242 and 246), still `experimental`.
- **Nothing fitted changed** (not `h0`, `n`, `k`, the fuel tables or the shape arrays); the status stays `experimental`.
- **Not tried after seeing the results (per the protocol):** other columns or pulse subsets, other conductivities, thermocouple radii or axial positions, a gap or clad term, a temperature-dependent conductivity, any change to the shape arrays.
- **Record only:** the 1000-point column gives F_tc 8.7 and 7.9 (IQR 3.5–33), as in the first run; it takes no part in any label.

## Limits, repeated

Thermocouple lag biases F_tc low and conduction during slow pulses spreads heat; the initial temperature of each pulse is assumed (25 °C; 20 and 30 move F_tc by under 15 %); the instrumented elements' positions and the pulse database's core assignment are not independently confirmed (the database lists 31 `core_config` values, and cores 242 and 246 are two of them); the first run's result was seen, so a good H-pulse here is a stability check, not a blind confirmation; a "plausible" result means the chain is consistent with the data, not that each factor is right.
