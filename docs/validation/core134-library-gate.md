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

(to be filled in after the runs are read)
