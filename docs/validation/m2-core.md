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

## Run-time options

`--quick` (4,000 × 60 batches): ~10 s per point, ~3x the statistical error (±220 pcm); for geometry and trend checks only.
`--save-source` / `--source-from`: start a run from a converged fission source of a similar state; 10 inactive batches instead of 50 with the same
active batches (52 s → 43 s per standard point).
