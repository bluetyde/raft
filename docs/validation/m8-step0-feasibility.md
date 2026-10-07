# M8 step 0: can the BEAVRS full-core model run here? (2026-10-07)

Plan: `docs/m8-second-reactor-plan.md`, step 0. Nothing here is a validation result: the runs were made to time the model and to see whether it is near critical at the benchmark's own state. No library was built, and nothing from BEAVRS is in this repository yet.

## What was found

- **Licence:** `mit-crpg/BEAVRS` is MIT-licensed (GitHub licence field and `LICENSE` file; repository head `1ccae04`, 2025-12-23). It holds the specification (`beavrs_specifications.pdf`, rev 3.0.2), measured data, and an OpenMC input generator (`models/openmc/make_beavrs.py` with the `beavrs` package). Cloned to WSL `~/beavrs` (68 MB, outside this repository). If any BEAVRS file is copied into this repository later, the MIT notice must be kept (M9 licence check).
- **The model generates and runs unchanged** in the `openmc-vr` env (OpenMC 0.15.3, ENDF/B-VIII.0): `python make_beavrs.py` takes 2 s and writes a 3D full-core `model.xml` (386 cells, 140 kB). Its materials carry 566.483 K (560 °F) and its settings already use temperature interpolation.
- **Measured data that the plan needs are in the specification** (section 3.2, Tables 21 and 22, cycle 1 hot zero power): inlet 560 °F, banks A, B, C at step 228, bank D at step 213, **critical boron 975 ppm**; critical boron for D in (902), C+D in (810), A+B+C+D in (686), A+B+C+D+SE+SD+SC in (508) ppm; bank worths in pcm (D 788, C with D in 1203, B with D, C in 1171, A 548, SE 461, SD 772, SC 1099); isothermal temperature coefficients in pcm/°F (ARO −1.75, D in −2.75, C+D in −8.01). Cycle 2 has its own table (Table 23). The specification gives no uncertainties in these tables; `beavrs_uq_report.pdf` is the place to look (step 1).

## The runs (seen before the protocol; disclosed there)

All with the model as generated (ARO, bank D at 213, 975 ppm, 566.483 K), ENDF/B-VIII.0, 16 threads, WSL.

| Run | Histories | k-effective | Wall | CPU (user) | CPU per history |
|---|---|---|---|---|---|
| BEAVRS short | 20 000 × 20 (10 inactive) | 1.00020 ± 0.00150 | 28 s | 158 s | 0.39 ms (includes 10 s of start-up) |
| BEAVRS gate | 60 000 × 120 (40 inactive) | **1.00075 ± 0.00045** | 275 s | 2299 s | 0.32 ms |
| TRIGA 242 baseline (`core_model`, the sweep's case) | 20 000 × 150 (50 inactive) | 1.05276 ± 0.00069 (at T=0, K=499, V=200, R=500) | 96 s | 868 s | 0.29 ms |

**Comparison:** a BEAVRS history costs about 1.1 times a TRIGA history in CPU time, so the full core is no harder to run than the TRIGA sweeps. Wall time is not a fair comparison: other agents were running on this machine (load average about 1 for the TRIGA run, 6 to 17 during the BEAVRS runs, from the MCNP tests and the OpenMC Studio worker), and CPU time per history is the figure to trust. A case to ±25 pcm needs about 3× the gate run's histories (roughly 15 minutes); a 20-case sweep is about 5 hours.

## Gate (from the plan, step 0)

- *k at the benchmark's critical state within the benchmark's scatter of the measured critical boron:* k = 1.00075 ± 0.00045, that is **+75 ± 45 pcm** (ρ = (k−1)/k) from critical at the measured 975 ppm. The benchmark's own uncertainty on that point is in `beavrs_uq_report.pdf` (not read yet). **Provisionally passes.**
- *Error below about 30 pcm per case in a time that allows about 20 cases:* the gate run's error was 45 pcm in 4.6 minutes; 30 pcm needs about 10 minutes, 20 pcm about 25. **Passes.**
- *Fallback (2D slice or single assembly):* **not needed.**

## For step 1 (the protocol)

- Read `beavrs_uq_report.pdf` for the uncertainty of the critical boron and the bank worths before the bands are set.
- Source convergence in a full core needs more than 10 inactive batches; the gate run used 40 and its entropy was not checked. The protocol should fix the inactive batches (and check entropy once).
- Bank worth is the difference of two critical boron states or two k values; its statistical error is √2 times a single case's. Plan the number of histories from the bank worths, which are the smallest differences (548 pcm for bank A).
- The `--rcca-insertion` option of `make_beavrs.py` sets bank positions in steps (0–228); boron is a model argument (`BEAVRS` takes ppm through `nominalBoronPPM`, to confirm in the builder).
- Temperature: the model sets 566.483 K on every material; the data grids are at 294 K and 600 K, so the interpolation tolerance matters (the TRIGA pin-cell work showed that `nearest` is wrong here). Isothermal coefficients need runs at other temperatures, with the water density changed too.
