# M2 step 3: the OpenMC libraries (2026-09-28)

`libraries/triga-jsi-242-openmc` and `libraries/triga-jsi-246-openmc`: the per-core libraries with every reactivity, kinetics and shape
table from full-core OpenMC transport (0.15.3, ENDF/B-VIII.0) at the calibrated uniform burnup B246 = 23.7 MWd/kg
(`m2-burnup-results.md`). Thermal properties, poisons, instruments, trips, interlocks, scram profiles and rod speeds come unchanged from
the M1 per-core libraries (`pipeline/library/build_triga.py`), which label them.

- **Sweep**: `python -m pipeline.openmc.sweep --core 242 --core 246` (83 cases, 20,000 × 150 each, 2026-09-27 19:5x to 2026-09-28
  00:51, 83 completed, 0 failed; run by the user in their own terminal). Summaries `pipeline/openmc/results/sweep_<core>.json`.
- **Export**: `python -m pipeline.library.export_openmc --summary pipeline/openmc/results/sweep_<core>.json --created 2026-09-28`
  (A11); raw worth points and the holdout details in `pipeline/openmc/results/export_<core>.json`.
- **Validation**: both libraries pass the Python validator and the TS validator (`web/src/library/validate.ts`).

## What the libraries say

| | core 242 | core 246 |
|---|---|---|
| ρ at the measured critical rods (then offset by `reference.calibration`) | −356 ± 63 pcm | +179 ± 61 pcm |
| β_eff (IFP, 6 groups) | 769 ± 23 pcm | 747 ± 23 pcm |
| Λ (IFP) | 44.9 ± 0.3 µs | 49.4 ± 0.3 µs |
| transient rod, total worth | 2998 pcm = $3.90 (measured s242: 3034 pcm) | 2598 pcm = $3.48 (s246 = core 244: 2937 pcm) |
| safety / shim / regulating, total | 3964 / 2389 / 2427 pcm | 3835 / 2509 / 2460 pcm |
| fuel temperature, 294 → 400 / 500 / 600 / 800 K | −822 / −1726 / −3085 / −5425 pcm (±99) | −861 / −1865 / −3060 / −5391 pcm (±95) |
| coolant, 294 → 313 / 333 K | +120 / +464 pcm (±91) | +181 / +503 pcm (±96) |

Checks against open sources (not tests fixed in advance; recorded for the reader):
- **Fuel coefficient** −8 to −14 pcm/K between grid points (the scatter is the ±1.4 pcm/K statistics): svajger2024 Table 10 uses
  −10 pcm/K; the UT Austin TRIGA SAR (2023, Table 4.14) gives −$0.013/°C ≈ −9 pcm/K.
- **Coolant coefficient positive**, about +12 pcm/K on average over 294–333 K. The UT Austin SAR gives a moderator temperature
  coefficient of **+$0.06/°C** for its 2018 core and ~0 for its limiting core (Table 4.16): a positive value is within what TRIGA cores
  show. The M1 libraries had an *assumed* −3.5 pcm/K; the sign change matters for slow transients and is now a transport result.
- **β_eff and Λ**: UT Austin SAR: β_eff 0.0071–0.00735, prompt lifetime 47 µs. The M1 libraries used 700 pcm and 40 µs (vavtar2021).
- **Transient rod, core 242**: 2998 vs 3034 pcm measured (−1%); the full curve was compared in `m2-burnup-results.md`.

## Holdout checks (superposition), `domain.jointChecked`

Six joint states per core (all four rods and the fuel temperature at pseudo-random values), each a full transport run, compared with the
library's separable prediction (ρ = ρ_ref + Σ rod tables + fuel table; shape = base + Σ deltas).

| core | ρ error (pcm) | max shape error (× mean bin) |
|---|---|---|
| 242 | 450, 82, 79, 61, 153, 69 | 0.33–0.63 |
| 246 | 184, **914**, **590**, 217, 110, 161 | 0.31–0.59 |

Statistics alone put roughly 150–240 pcm (1σ) on each ρ error (the prediction adds five interpolated tables, each a difference of two
transport runs, to the holdout's own ±70 pcm). So core 242's errors are consistent with noise, and **two core-246 states exceed it
clearly (914 and 590 pcm): both have several rods deep in the core** (transient 0.18 / shim 0.24 / regulating 0.34, and regulating
0.06 with the others near 0.4). In both, the library **predicts more reactivity than transport finds** (predicted − actual = +914 and
+590 pcm): with several rods deep, they absorb more together than the sum of their separate worths, because each one pushes flux toward
the others (flux redistribution, the opposite of shadowing). Core 242's largest error has the other sign (−450 pcm, about 2σ). The
signed values are in `pipeline/openmc/results/export_<core>.json`. The shape errors are dominated by bins next to rod tips.

What this means for the runtime: states like these are inside `domain` but not covered by a joint check, so the engine reports them as
`unvalidated` (library-format section 13). Scenarios that drive several rods deep at once should say so. A rod-pairs family (plan 02
section 3) is the fix if it matters; it is not part of M2.

## Regression: run 3 Part B with these libraries

`python -m validation.m2_run3b_regression` (report `validation/m2_run3b_regression_report.json`): run 3 Part B's code, pulses and
criteria unchanged (`m1-run3-protocol.md`), with the OpenMC libraries in place of the M1 ones. Each library also re-derives the
trace-inferred $ axis (its own engine curve, so its own Λ). 14 min 46 s on Windows.

| | pulses used | rms (ln) | bias | slope measured / simulated | B1–B4 |
|---|---|---|---|---|---|
| core 242, M2 | 32 | 0.048 | −4.0% | 1.88 / 1.97 | all pass |
| core 242, M1 (counts corrected) | 32 | 0.035 | +2.2% | 1.89 / 1.98 | all pass |
| core 246, M2 | 46 | 0.051 | −4.5% | 1.83 / 1.93 | all pass |
| core 246, M1 (counts corrected) | 36 | 0.037 | −2.9% | 1.85 / 1.95 | all pass |

**M2 keeps the M1 result**: every criterion passes with margin (B1 rms bound ln 1.5 = 0.405, B2 bias bound ln 1.3 = 0.262, B3 slope
difference 0.4). The fit is slightly looser than M1's (rms 0.05 vs 0.04) and both cores now sit a few percent low. The pulse
comparison was never sensitive to what M2 changed most (rod worths enter only through the $ axis, which is inferred from the traces),
so this is a regression check, not new evidence for the libraries. Core 246 uses 10 more pulses because its longer Λ (49 vs 40 µs)
moves more inferred insertions above the $1.30 cut.

## Codex milestone review (2026-09-28) and fixes

Two Codex auditors (silent failures; specification gaps) on the M2 code: 19 findings, 17 distinct, none dropped on checking. Fixed on
`claude/m2-codex-fixes`, one regression each (all fail on the pre-review code except the domain test, which the stricter plan check
already makes unreachable; it pins the rule):

- **Shapes now sum to all fuel fission.** Fuel-follower fuel below the core (0.46% of the power at core 242's reference) was dropped
  and the rest renormalised. The exported shape has a 16th axial bin, [−57.15, −19.05] cm, holding each region's total minus its
  tallied fission: zero for regular elements (their volume there is nominal), the follower power for D1 and D10. Re-extracted from
  the cached statepoints (extractor version 2): no transport re-run, every case key and k unchanged, the other bins identical to
  4e-19. The holdout shape errors above include the new bin.
- **Exporter:** builds in a staging folder, validates, then swaps (a failure leaves the old library byte-identical); refuses a
  summary that isn't exactly the planned sweep (missing, duplicate or changed cases, other axial grids, wrong dimensions,
  non-finite values); repairs only float32 rounding (≤ 1e-6), never a real normalisation error; predicts holdouts from the
  exported float32 arrays with strict lengths; writes JSON with `allow_nan=False`; declares the domain from the table coverage;
  records provenance from the summary (`transportCode`, `nuclearData` with data digests, `model` = a digest of the case keys).
- **Run cache:** an unreadable statepoint fails verification and re-runs instead of aborting the sweep; a re-run drops derived
  results; every FileSource gets its own digest. **Sweep:** missing cases are counted per core.
- **Depletion:** NaN, infinite or clearly negative densities raise instead of being dropped. **Rod curves:** records from another
  model state or conflicting duplicates are refused. **Burnup fit:** B246's uncertainty is propagated through the interpolation
  (0.219 MWd/kg for the committed run, not 0.256; `m2-burnup-results.md`).

Physics tables (reference, kinetics, rod worths, temperature tables), geometry and plant data are unchanged by the fixes.

**Open (a format decision, not fixed):** fuel-follower bins that the follower fuel only partly fills are given a full-height volume,
so power *density* there reads low (about 40% at core 242's reference in the bin holding the follower tip). Bin *power* is
correct. Fixing it needs follower bins that move with the rod, which the format can't express yet.
