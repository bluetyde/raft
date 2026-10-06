# Core 134 library: the gate before the full sweep (written 2026-10-06, before the gate runs were read)

Context: `TODO.md`, option 2 (a core 134 library through the OpenMC pipeline, so the power ascension of the 1994 benchmark can be compared on its own core). The gate decides whether the full sweep is worth running. The three gate cases had not been run when this note was written.

## What the gate tests

The OpenMC model of cores 133 and 134 (fresh fuel, no burnup calibration, the loading maps of `validation/data/jsi-core134/loading_map.json`, the same geometry and materials as cores 242 and 246) against three measured numbers of the 1994 paper, at the 294 K reference of the pipeline (the paper's water was 22–23 °C):

| # | Case | Measured | Source |
|---|---|---|---|
| G1 | core 133, all rods withdrawn, source out (E-12 empty) | **+310 pcm** (k = 1.0031), total uncertainty about 15 pcm | Table V; Jeraj et al. 1996 |
| G2 | core 134, critical: regulating rod 28.7 cm inserted (step 727.3), the others withdrawn | **0 pcm** (critical) | Table VII note |
| G3 | core 134, all rods withdrawn | **+2022 pcm** (average of the four rods' critical positions; the four values 1872–2144 pcm, about ±5 % in Jeraj et al. Table 5) | Section III.C |

The step of the regulating rod comes from the paper's 28.7 cm inserted at 38.1 cm full travel and the pipeline's 700 steps from 200 (withdrawn) to 900: `200 + 28.7 / (38.1 / 700) = 727.3`. G3 minus G2 also checks the model's regulating rod worth over that stretch against the measured integral worth at 28.7 cm (about 2150 pcm, Table VI).

## Pass criteria (fixed now)

- **Pass:** `|model − measured| ≤ 300 pcm` in all three cases. The statistical error of a run is about 30 pcm; the pipeline's data (ENDF/B-VIII.0) and the model's assumed materials (B4C density, graphite density, aluminium) are expected to leave a systematic of the order of 100 pcm (Jeraj et al. found +105 pcm with ENDF/B-VI for the same cores).
- **Borderline:** the worst case between 300 and 600 pcm. Continue only after looking at which input is likely (B4C density, reflector graphite density, fuel density: the fuel density of the pipeline, 6.045 g/cm³, is 1.2 % below the 1994 Table II value, 6.12 g/cm³; its 235U density agrees), as a labelled sensitivity, not a fit.
- **Fail:** the worst case above 600 pcm: stop. The pipeline's model of these cores is not good enough for a library to carry the benchmark, and the cost of the full sweep is not spent.
- A constant offset between model and measurement in all three cases (the same sign and size) is not a failure by itself: the earlier libraries carry a calibration offset (`reference.calibration.deltaRho`) for that reason. What would fail is a **difference** between G3 and G2 (the rod worth) that is more than 300 pcm off the measured 2150 pcm.

## What is not tested here

Temperature feedback (the fuel and coolant tables), the regulating rod's curve shape, the fuel element worths of Table VII (±20 pcm), the pulse parameters. Those are the checks of the full sweep and the library.

## Result

Run 2026-10-06 in the `openmc-vr` environment, 20000 particles, 150 batches (50 inactive), about 1 minute per case, ENDF/B-VIII.0; raw lines in `pipeline/openmc/results/core134_gate.jsonl` and `core134_gate2_fuel1994.jsonl`.

### Round 1: the pipeline's default fuel (Svajger 2024 Table 1, H/Zr 1.60), as pre-registered

| # | Case | Model (pcm) | Measured (pcm) | Difference |
|---|---|---|---|---|
| G1 | core 133, all rods out, source out | +674 ± 69 | +310 | **+364** |
| G2 | core 134, critical (regulating rod 727.3 steps) | +323 ± 66 | 0 | **+323** |
| G3 | core 134, all rods out | +2493 ± 68 | +2022 | **+471** |
| | G3 − G2: regulating rod worth over the stretch | 2170 | about 2155 (Table VI at 28.7 cm) | **+15** |

**Result by the pre-registered criteria: borderline** (the worst case, +471 pcm, is between 300 and 600 pcm). The three differences have the same sign and about the same size, which the criteria say is not a failure by itself, and the **rod worth difference (+15 pcm) is within the statistical error**, so the rod worth over 28.7 cm is reproduced.

### What was looked at for the borderline result (a labelled sensitivity, not a fit)

The gate note listed the fuel density as a candidate. Reading Table II again showed a larger difference: the 1994 fuel has **H/Zr 1.65**, the pipeline's default fuel 1.60, with the same uranium (the 235U and 238U densities agree to 0.04 %). Per cm³ the 1994 fuel has 4.6 % more hydrogen and 1.4 % more zirconium. The option `--fuel1994` of `core_model` builds that composition from Table II (mass 2360 g per element, in the pipeline's fuel volume).

### Round 2: the benchmark paper's own composition (`--fuel1994`), the same three cases

| # | Model (pcm) | Difference from measured |
|---|---|---|
| G1 | +1648 ± 71 | **+1338** |
| G2 | +1287 ± 69 | **+1287** |
| G3 | +3253 ± 78 | **+1231** |

The paper's composition **moves the model away from the measurement by about 960 pcm**, so it is not adopted. It shows how sensitive the model is to the hydrogen content of the fuel: about 190–200 pcm per 0.01 of H/Zr. The round 1 offset (about +390 pcm on average) corresponds to an H/Zr of about 1.58, which lies within what the real fuel's hydrogen content could be (the paper gives the 1.65 as a batch average; ZrH loses hydrogen with use and with time), but nothing here establishes it. No input was fitted to the measurement.

### Decision

- **Continue to the full sweep with the default composition (H/Zr 1.60)**, and the same reference offset that the 242 and 246 libraries use (`reference.calibration.deltaRho`, which makes the measured critical state critical: here about −323 pcm). The offset is a calibration, and the library is `experimental` like the others.
- **Reservation, to be stated in the library and in the next protocol:** the model's reactivity moves about 200 pcm per 0.01 of H/Zr, so the constant offset absorbs the fuel composition only to first order. A rod or feedback result that depends on the fuel hydrogen (the temperature coefficient above all) carries that uncertainty; the sweep's own feedback tables are the test.
- **The gate does not test** the feedback tables or the shape of the regulating rod curve beyond 28.7 cm; those are the checks of the library (step 6 of the TODO).

### Addendum: sensitivity scan on core 133 (2026-10-06, after the criticism that +364 pcm on a +310 pcm measurement is a 100 % error)

Core 133, all rods out, 40000 particles, 150 batches (statistical error 43–52 pcm), one assumed input changed at a time; raw lines in `pipeline/openmc/results/core133_sensitivity.jsonl`. Not a fit: every run is listed.

| Change | Model (pcm) | Change from the baseline |
|---|---|---|
| baseline (graphite 1.6, B4C 2.48 g/cm³, 294 K) | 647 ± 45 | |
| reflector graphite 1.5 / 1.7 g/cm³ | 552 ± 52 / 788 ± 50 | −95 / +141 |
| B4C 2.2 / 2.7 g/cm³ | 639 ± 43 / 685 ± 47 | −8 / +38 (rods are out; no effect beyond the noise) |
| whole core at 295.65 K (22.5 °C, the paper's water) | 746 ± 49 | +99 (the wrong direction) |

- **None of these inputs explains the +340 to +360 pcm.** Closing it with the reflector alone would take a graphite density of about 1.2 g/cm³, which is not physical.
- **What the 1994 paper itself says about this:** the uranium content of the core is known only to about ±10 g of 235U (0.5 %), and its own linear estimate is 100 pcm per 2 g, so **the calculation of these cores is uncertain by about ±500 pcm from the fuel composition alone**. The offset found is inside that. (The measured reactivities, ±15 pcm, are not.)
- **Data not yet used:** Table III gives each element's own 235U content. The pipeline uses the batch average for every element. For the cores here the sum of the individual values is 0.9 g (core 133) and 3.9 g (core 134) below 40 and 45 times the average, which by the paper's estimate is about −46 and −195 pcm: it moves core 134 toward the measurement and core 133 barely.
- **The hydrogen content of the fuel remains the largest single lever** (about 200 pcm per 0.01 of H/Zr; an H/Zr of about 1.58 would remove the offset).
