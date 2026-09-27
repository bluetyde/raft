# M2 step 2: full-core model of core 242 (2026-09-27)

Model: `pipeline/openmc/core_model.py`, built from open data only (`pipeline/openmc/data/`: fuel element, core geometry, occupancy from the
database core maps). OpenMC 0.15.3, ENDF/B-VIII.0, all materials at 294 K. **All 58 fuel elements are fresh** (burnup isn't in the open sources),
and a few inputs are labelled `assumed` in the model's docstring (B4C and reflector graphite density, end fittings/grid plates/channels as water).

## Critical state

Measured critical at 400 W (rod-table header, s242): T and V fully up, K = 499, R = 500 steps.
Model: **k = 1.0528 ± 0.0007** (+$7.2). Expected in sign and plausible in size for fresh fuel in place of elements with decades of burnup
(vavtar2021 Fig. 1 shows 0/14/30% burnup curves); not a pass/fail test until burnup is modelled.

## Transient rod worth vs the measured table (s242, measured 2020-10-19 on core 242)

Worth W(s) = rho(fully up) − rho(s steps inserted), other rods at the critical positions; 40,000 particles × 200 batches per point.

| steps | model W (pcm) | measured W (pcm) | ratio |
|---|---|---|---|
| 150 | 88 ± 60 | 53 | within noise |
| 300 | 186 ± 58 | 360 | 0.52 |
| 450 | 850 ± 56 | 1012 | 0.84 |
| 600 | 1664 ± 54 | 1887 | 0.88 |
| 750 | 2466 ± 54 | 2675 | 0.92 |
| 900 | 2694 ± 57 | 3034 | 0.89 |

- **Agrees:** the S-curve's midpoint (half worth at ~540 steps in the model, ~537 measured), which supports the step scale (0.0544 cm/step) and
  the absorber placement; the total within 11%.
- **Differs:** the measured curve is broader (twice the model's worth at 300 steps) and 11% larger in total.
- **Candidate causes, not yet separated:** burnup (burned elements flatten the axial flux, which broadens rod worth curves); the assumed B4C density;
  the table's pcm are dollars × 700 pcm, so a model β_eff different from 700 pcm moves the comparison (β_eff from OpenMC is a next step).

## Sensitivity: B4C density (assumed 2.48 g/cm3)

Transient rod worth 0 → 900 steps, core 242, 40,000 × 200 per point:

| B4C (g/cm3) | worth (pcm) |
|---|---|
| 1.8 | 2604 ± 55 |
| 2.48 (model) | 2694 ± 57 |
| 2.52 (theoretical) | 2657 ± 52 |

The absorber is nearly black: a 27% lower density changes the worth by −3%, within about 1.2σ. **The B4C density does not explain the
11% gap.**

## Kinetics parameters (core 242, critical rods, fresh fuel)

OpenMC's iterated fission probability (IFP) tallies (`--kinetics`, 10 generations; 80,000 × 150, 50 inactive):

| | OpenMC (this model) | M1 library (vavtar2021) |
|---|---|---|
| β_eff | **737 ± 11 pcm** | 700 pcm |
| Λ | **40.58 ± 0.15 µs** | 40 µs |
| groups (pcm) | 27.8, 138.0, 127.3, 284.6, 110.2, 49.1 | 23.1, 153.3, 137.2, 276.5, 80.5, 29.4 |

Cross-check by the prompt method (`--prompt`, no delayed neutrons, same statistics): 1 − k_p/k = 1 − 1.04504/1.05254 =
**713 ± 47 pcm**, consistent with IFP. Λ agrees with the library; β_eff is 5% higher (fresh fuel: no Pu-239, whose delayed fraction is
about a third of U-235's, so burnup should lower it; to be re-run with burnup).

In dollars the transient rod worth moves further from the table: the table's 3034 pcm is $4.33 at 700 pcm/$, the model's 2694 pcm is
$3.66 at its own 737 pcm, a ratio of 0.85 (0.89 in pcm).

## Run-time options

`--quick` (4,000 × 60 batches): ~10 s per point, ~3x the statistical error (±220 pcm); for geometry and trend checks only.
`--save-source` / `--source-from`: start a run from a converged fission source of a similar state; 10 inactive batches instead of 50 with the same
active batches (52 s → 43 s per standard point).
