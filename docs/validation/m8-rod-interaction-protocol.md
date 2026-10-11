# M8 combined rod worth: the library with a correction table, against held-out transport cases and the cycle 1 physics tests (fourteenth protocol, written before any code and before any run of the held-out cases, 2026-10-11)

This is the checking step of `docs/m8-rod-interaction-plan.md`. The twelfth protocol measured that the BEAVRS library, which adds single-bank worths, fails with several banks in (`m8-beavrs-library-results.md`). The plan adds one table, `reactivity.rodInteraction` (capability `point-kinetics/rod-interaction-v1`), a correction on the sum of the single-bank rod reactivities. This protocol fixes, before anything is built or run, what the table is fitted to, which new transport cases test it, how the library is read against the measurements again, and what each outcome means. Method as in M7 and M8: every case and metric is run once, every metric is reported, **nothing is refitted afterwards**, errata are not fixes, the library stays `experimental`.

## What is fixed

**The correction table** is fitted by the exporter to these points only (S = the sum of the single-bank reactivities relative to the reference, correction = the transport reactivity minus the summed prediction, both in pcm; all from the 45-case sweep `pipeline/openmc/results/beavrs_sweep.jsonl` and `beavrs_export_report.json`, seen before this protocol):

| S | Correction | Source |
|---|---|---|
| +100 | 0 | assumed (bank D from its bite position to out is +61 pcm; nothing above the reference is claimed) |
| 0 | 0 | every rod at its reference position, by definition |
| −827 | 0 | the deepest single-bank worth (bank B); one bank has nothing to interact with |
| −1576 | −420 | case J-W2 (C and D in) |
| −2632 | −1107 | case J-W4 (A to D in) |
| −4075 | −1953 | case J-W7 (D, C, B, A, SE, SD, SC in) |

Piecewise linear, clamp-and-flag outside; the points are given to the nearest pcm here and the exporter uses the cases' own numbers (a weighted monotone fit, the points' statistical errors as weights). **The analysis refuses a library whose table differs from these points by more than 5 pcm in S or in correction.** No measurement and none of the nine cases below enters the fit.

**The nine held-out transport cases** (new, none yet run), 975 ppm, 566.483 K, the sweep's settings (60 000 particles × 300 batches, 100 inactive, IFP off, seed 1), ids and rod positions in steps withdrawn (0 = in; the others at their benchmark reference positions, D at 213 and the rest at 228 unless stated):

| Id | State |
|---|---|
| P-S3 | D, C, B at 0 |
| P-S5 | D, C, B, A, SE at 0 |
| P-S6 | D, C, B, A, SE, SD at 0 |
| P-C-76 | D at 0, C at 76 |
| P-B-76 | D, C at 0, B at 76 |
| P-A-76 | D, C, B at 0, A at 76 |
| P-SE-76 | D, C, B, A at 0, SE at 76 |
| P-SD-76 | D, C, B, A, SE at 0, SD at 76 |
| P-SC-76 | D, C, B, A, SE, SD at 0, SC at 76 |

Each case is run once (a crashed or stopped case is run again with the same settings, not counted as a second run). The convergence check of the earlier protocols applies (the mean k of batches 101 to 200 and of 201 to 300 agree within 2 standard errors of their difference); an unconverged case is kept, labelled, and enters no decision item.

**The library:** `libraries/pwr-beavrs-hzp-openmc` rebuilt by `pipeline.library.export_beavrs` with the table (capability added; everything else as the library of git `3842ace`), read by the Python reference engine. The measured data are those of the eleventh and twelfth protocols (critical boron 975, 902, 810, 686 and 508 ppm, σ 22; the seven sequential worths; the two temperature coefficients).

## Disclosure: what was seen before writing

This protocol is **not blind**.

- **Seen:** everything in the eleventh and twelfth protocols and their results; the exporter's self-check (the summed model against transport at the 45 sweep cases, including the three combined points above and the two at the measured boron); the single-bank tables; the plan's argument that the correction depends on the sum S.
- **Not seen:** any of the nine path cases, at any settings; any library with the table; any reading of the held-out states by another method.
- **What the fit cannot know:** nothing in the table depends on which banks make S (stated assumption, tested by P).

## Predictions (written before the runs; the results decide)

**P:** the states S3, S5 and S6 within 200 pcm of transport; the part-way cases within 300 pcm; the largest errors at the last banks (SD and SC part-way, where one bank moves while six are in and the table is steepest).

**M:** the critical boron errors fall to about those of the transport model plus the boron×bank interaction that the table does not carry: **S0 +8 ppm, S1 +22, S2 +16 to +20, S4 +6 to +10, S7 +6 to +10** (the library at the measured boron is above transport by about 97 pcm at S4 and 290 pcm at S7, 8 and 23 ppm, on top of the transport errors of −2 and −15); the total worth of the seven banks within 1 % of the measured 6042 pcm (the transport total is 6028); the worth of C within 5 % (transport 1236 against 1203); the other sequential worths (B, A, SE, SD, SC) between plausible and fails, because S3, S5 and S6 are interpolated; the temperature coefficient fails at both states as before (−3.57 pcm/°F), because the table does not touch it.

## The question

(P) Does a correction depending only on the summed single-bank reactivity reproduce the transport reactivity at states along the benchmark insertion path that it was not fitted to? (M) Does the library with that table reproduce the measured critical boron, sequential worths and temperature coefficients better than the summed tables did, and where does it still fail?

## The computations (fixed now)

Reactivity is the engine's `reactivity(t, y)["total"]` at the state (rods at the case's steps / 228 withdrawn, boron, `Tfuel = Tcoolant = 566.483 K`), from a fresh engine at zero power, in pcm. Transport ρ = (k − 1)/k from the case, σ = σ_k/k².

- **P: the nine cases.** For each, library ρ and transport ρ, the difference (library minus transport), the statistical error of the transport case, and the difference of the summed model without the table (the same engine state with the table switched off) for comparison. Labels by |difference| against the limit L = max(100 pcm, 3 σ_transport): **good** ≤ L, **plausible** ≤ 2L, **fails** > 2L. A case enters `domain.jointChecked` only if good.
- **M: as the twelfth protocol, unchanged:** A critical boron at S0, S1, S2, S4, S7 (bisection in 300 to 1600 ppm); B the seven sequential worths and their total; C the temperature coefficient at S0 and S2 (fuel and coolant shifted together, ±30 K, 108 °F); F the six differences from transport (R-D-0, J-W2, J-W4, J-W7, J-B4, J-B7); the same model errors (the tables' own errors at their interpolated points; the shared-table cancellation of the erratum of 2026-10-10 is reported next to the as-run rule, as there), z and labels (good ≤ 1, plausible ≤ 2, fails > 2), the 50 ppm criterion, and the library's own reactivity at the states S3, S5 and S6 for the record.

## Decision process

1. **P: at least 7 of the 9 cases good or plausible, and none beyond 400 pcm:** the single-axis correction holds along the benchmark path to the accuracy shown. The cases that are good enter `jointChecked`; the library may claim the path states; the bank-withdrawal lesson may be built on it (its envelope: states on the benchmark insertion order only).
2. **P: fewer than 7, or any beyond 400 pcm:** the assumption fails, with the places named. The lesson is not built on this table; the next candidate is pair terms (a bank's correction as a function of the reactivity of the others), a separate plan and protocol. The table stays in the library only if it improves every held-out case against the summed model; otherwise it is recorded as not adopted.
3. **M:** the claim of the library widens to the states whose critical boron is good or plausible (decision 1 of the twelfth protocol), with the numbers shown; sequential worths and the total are labelled as in the twelfth protocol; a temperature coefficient that still fails keeps the temperature feedback "not validated". The two results (P and M) are reported side by side; M is not used to change the table.
4. **A case not computed** (unconverged, missing, or the critical boron outside the domain) enters no decision item.
5. Under all outcomes the library status stays `experimental` and nothing is refitted.

## Implementation (to be written after this protocol is committed)

1. `pipeline/openmc/beavrs_cases.py`: the nine cases as a second family (`path_cases()`), kept apart from `sweep_cases()` (the exporter and the 45-row results file are unchanged); a runner option for the family, results in `pipeline/openmc/results/beavrs_path.jsonl`; a test of the plan.
2. The capability: format section 16, schema, both validators, fixtures, both engines, a golden vector, the gate (every existing vector unchanged); a Codex review.
3. The exporter: the fit above, a planted-model test (a nonseparable planted sweep along a path: the exporter must recover the planted table), deliberate breaks.
4. `validation/m8_rod_interaction.py` (P and M, run once) and its planted test with deliberate breaks; the results note `m8-rod-interaction-results.md`.
5. Then the lesson, on the result.

## Limits, repeated

The library inherits the transport model's limits (the eleventh protocol): the temperature coefficient is wrong; thermal expansion is not modelled; one boron worth converts the errors; the measured tilt and instrument effects are not in the model. The table is a function of one number and is validated along one path; other bank orders and the two banks that are not in the benchmark sequence (SA, SB) are not covered. The boron × bank interaction (about 100 pcm at four banks in, 290 at seven) is not in the table. The summed power shapes still go negative in a few bins with several banks in; this protocol compares reactivity only.
