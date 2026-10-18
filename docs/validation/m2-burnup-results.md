# M2 burnup calibration: results (2026-09-27)

Protocol: `m2-burnup-protocol.md` (committed `99cd110`/`3546ebe`, before any calibrated result). Runner: `python -m validation.m2_burnup
--grid 22 24 26 28`; report `validation/m2_burnup_report.json`. Depletion table: `pipeline/openmc/data/jsi_fuel_depleted.json`
(5,000 × 50 per depletion step). Core points: 20,000 × 150, 50 inactive.

## Fit

Core 246 at its critical rods (T up, K 536.6, V up, R 535; pungercic2024), uniform burnup B:

| B (MWd/kg) | 16* | 18* | 20* | 22 | 24 | 26 | 28 |
|---|---|---|---|---|---|---|---|
| ρ (pcm) | 1682 | 1307 | 869 | 434 | −84 | −309 | −940 |

\* from a first run with the grid 16–24, which did not bracket k = 1 (ρ = +33 pcm at 24) and stopped; the grid was extended to 22–28
without changing the fit rule. Its 22 and 24 points (413, +33) differ from the second run's by 21 and 117 pcm (≤ 1.2σ combined): the
burned-fuel nuclide order came from a Python set, so each process drew a different random-number stream. Fixed after this run
(`burned_fuel` sorts); the results below are from the second run only.

**B246 = 23.7 ± 0.3 MWd/kg (effective, statistical only).**

(Corrected 2026-09-28, Codex M2 review: propagated through the interpolation, the statistical uncertainty is 0.22 MWd/kg,
not the 0.26 the run printed; the post-hoc check below shows the true uncertainty is larger anyway.)

## Tests

| # | Result | Criterion | Verdict |
|---|---|---|---|
| T1 | core 242 at B246, measured critical rods: **ρ = −309 ± 73 pcm** | \|ρ\| ≤ 500 pcm | **PASS** |
| T2 | slope over 22–26: **−189 ± 26 pcm/(MWd/kg)** vs measured −232.8 ± 19.8 | within 2σ | **PASS** (z = +1.33) |
| T3 | B246 = 23.7 vs open burnups 1.9–21.0 (8 elements), ~20 typical | flag outside 0–30 | not flagged; above the 8-element sample and near the typical value |
| T4 | transient worth 0 → 900 at B246: **3052 ± 107 pcm = $4.21** at the model's β_eff 724 pcm | reported | table $4.33 (3034 pcm); fresh fuel gave $3.66 |

### Notes

- **T1's sign: my protocol's expectation was backwards.** It said core 242, 18 months older, "should read slightly positive". Core 242
  had *less* burnup than core 246, so giving it B246 overstates its burnup and should make it read **negative**, as it does. With T2's
  slope, −309 pcm corresponds to core 242 being about 1.6 MWd/kg less burned than core 246 under this model. That is a plausible size
  but is not tested here (the energy produced between the two cores is not in the open sources used).
- **T4 is the main gain.** With fresh fuel the model's transient rod worth was 0.85 of the table in dollars; with the calibrated burnup
  it is 0.97 ($4.21 vs $4.33), and 1.006 in pcm. The burnup flattens the axial flux, which is what broadens and raises the worth curve
  (m2-core.md listed burnup as a candidate cause; B4C density was ruled out). The S-curve shape at B246 is not yet re-run.
- **Kinetics at B246** (IFP, core 242, 20,000 × 150): β_eff **724 ± 25 pcm** (737 ± 11 fresh; the expected fall from Pu-239, but within
  the statistics), Λ **45.5 µs** (40.6 fresh; less U-235 means fewer fissions per neutron-second, so a longer generation time). The M1
  library uses 700 pcm and 40 µs; whether to move them is a decision for the library step, not made here.
- **What B246 is not:** the reactor's burnup. It is one number that makes this model critical, so it also absorbs the model's other
  biases (nuclear data, the `assumed` geometry, uniform instead of per-element burnup, depletion at 294 K and constant power).

## After the tests: the rod-worth curve at B246 (not part of the protocol)

`validation/m2_rod_curves.py` (report `validation/m2_rod_curves_report.json`); points in `validation/m2_scurve_points.jsonl`,
20,000 × 150 each, worth W(s) = ρ(T = 0) − ρ(T = s), core 242, other rods at the measured critical positions:

| steps | 150 | 300 | 450 | 600 | 750 | 900 |
|---|---|---|---|---|---|---|
| model at B246 (pcm) | 52 ± 107 | 453 ± 101 | 951 ± 105 | 1960 ± 98 | 2753 ± 104 | 3052 ± 107 |
| measured s242 (pcm) | 53 | 360 | 1012 | 1887 | 2675 | 3034 |
| fresh-fuel model (pcm, m2-core.md) | 88 | 186 | 850 | 1664 | 2466 | 2694 |

**Every point agrees with the table within 1σ.** The fresh-fuel model's too-narrow curve (half the measured worth at 300 steps) was the
missing burnup: burned fuel flattens the axial flux, which spreads the rod's worth over more of its travel. (The points share the
T = 0 run, so their errors are correlated.)

### Core 246 against its pulses' rod table (measured on core 244)

Same method, core 246 at its own critical rods (K 536.6, R 535), against `s246` (headed core 244, 8 June 2021; no open map of core 244):

| steps | 150 | 300 | 450 | 600 | 750 | 900 |
|---|---|---|---|---|---|---|
| model at B246 (pcm) | 190 ± 92 | 239 ± 94 | 947 ± 97 | 1776 ± 106 | 2416 ± 91 | 2598 ± 93 |
| measured s246 = core 244 (pcm) | 59 | 362 | 999 | 1840 | 2600 | 2937 |

The core 246 model's transient rod is worth **12% less than core 244's table** in total (−339 ± 93 pcm, 3.6σ), with the gap growing
toward full insertion, while the same method reproduced core 242's own table. The likeliest reading: **core 244's table does not
describe core 246** (a different loading around the rod). This is consistent in direction with C7, where core 246's pulse labels
(made with this table) overstated the prompt excess more than core 242's ($0.42 vs $0.27); a quantitative link is not made here.
Caveats: B246's uncertainty (next section) and one shared T = 0 run per curve.

## Post-hoc check: ρ of core 246 at B246 itself

A run of core 246 at exactly B246 (the curve's T = 0 point, after the nuclide-order fix, so an independent random stream) gives
**ρ = +179 ± 61 pcm**, not ≈ 0. The fit interpolated between two grid points whose own scatter (22 → 24 → 26 MWd/kg: −518, then
−225 pcm per 2 MWd/kg) is larger than their quoted errors suggest, so **B246's ±0.3 MWd/kg understates its uncertainty**; this point
alone suggests B246 ≈ 24.5. Not refitted (protocol). Effect on T1, estimated with T2's slope: core 242 would read about −450 pcm
instead of −309, still inside the 500 pcm bound but with little margin. A refit, if wanted, is a new protocol with more particles
per grid point.

## What this changes for M2

The calibrated model reproduces an independent critical state (core 242) within 309 pcm, the measured burnup reactivity coefficient
within 1.3σ, and the transient rod worth within 3% in dollars. It is the base for the remaining M2 steps: the S-curve shape of the rod
worth at B246, core 246 vs its measured table (on core 244), and the rod shapes for the per-core libraries.

## Erratum (2026-10-18, code review)

`validation/m2_rod_curves.py` divided both cores' model worths by core 242's β_eff (724 pcm). Core 246's own β_eff, from the delayed fractions its library carries, is 747 pcm. The pcm comparisons in this document are unaffected (the core 246 transient rod is 12 % below the table in pcm); in dollars the core 246 model at 900 steps is $3.48, not $3.59, and its ratio to the table 0.83, not 0.85 (0.62, 0.91 and 0.83 at 300, 600 and 900 steps). The script now uses each core's own β_eff and `validation/m2_rod_curves_report.json` carries both (`betaEffPcmByCore`); the stored report was recomputed from its own pcm values, because the measured tables are not in this checkout.
