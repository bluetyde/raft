# M8 combined rod worth: the shadowing correction against new held-out transport cases and the cycle 1 physics tests (fifteenth protocol, written before any code and before any run of the new cases, 2026-10-15)

This is the checking step of `docs/m8-pair-terms-plan.md`. The fourteenth protocol failed its part P (`m8-rod-interaction-results.md`): a correction on the summed single-rod reactivity S alone misses held-out path cases by up to 364 pcm, and two states with the same S differ by 164 pcm. The plan replaces it with a **shadowing correction**: each rod's worth is scaled by a function of the reactivity of all the *other* rods. This protocol fixes, before anything is built or run, the model, what it is fitted to, which new transport cases test it, how the library is read against the measurements again, and what each outcome means. Method as in M7 and M8: every case and metric is run once, every metric is reported, **nothing is refitted afterwards**, the library stays `experimental`, and an unconverged case is kept, labelled, and enters no decision item.

## What is fixed

**The model** (capability `point-kinetics/rod-interaction-v2`, field `reactivity.rodShadowing = {R, g, unc?, interp, outOfRange, source}`): with wᵢ the single-rod reactivity of rod i at its position (relative to the reference), S = Σ wᵢ, and Rᵢ = S − wᵢ,

ρ_rods = Σᵢ wᵢ · (1 + g(Rᵢ)).

g is piecewise linear, g(R) = 0 for R ≥ 0, clamp-and-flag below the last knot (outOfDomain). A library has v2 or v1, not both.

**The fit.** g is fitted by the exporter, by weighted least squares (weights 1/σ², σ the transport case's statistical error in pcm), unconstrained in sign, to the **12 combined transport cases already run** (J-W2, J-W4, J-W7 of the sweep; the nine path cases of the fourteenth protocol), at 975 ppm and 566.483 K. The target is the transport reactivity minus the reference minus S. Single-rod reactivities wᵢ are the library's own rod tables (fitted from the single-bank cases of the sweep). Knots: R = 0, −1000, −2000, −3000 and −3850 pcm (−3850 is the deepest Rᵢ among the 12 cases, −3845). **Values this procedure gives, computed once now from the seen data (transport single-bank worths in place of the tables; the analysis accepts the library's values within 0.02 at every knot and refuses it otherwise):** g(−1000) = 0.272, g(−2000) = 0.392, g(−3000) = 0.328, g(−3850) = 0.618. Fitted residuals on the 12 cases: −77 to +129 pcm (11 of 12 within 100 pcm; J-W4 +129, J-W2 +83); leaving each case out in turn, errors −102 to +167 pcm (9 of 12 within 100). No measurement and none of the 13 new cases enters the fit.

**The 13 new held-out transport cases** (none run), settings as the sweep (60 000 particles × 300 batches, 100 inactive, IFP off, seed 1, 566.483 K), steps withdrawn (0 = in; every rod not named at its benchmark reference position, D at 213 and the rest at 228):

| Group | Id | State | Boron (ppm) |
|---|---|---|---|
| L: the lesson's own path (seven banks in, C withdrawn) | L-C-0 | D, C, B, A, SE, SD, SC at 0 | 860 |
| | L-C-40 | as L-C-0, C at 40 | 860 |
| | L-C-83 | as L-C-0, C at 83 (the draft lesson's critical position, 0.362 of travel) | 860 |
| | L-C-120 | as L-C-0, C at 120 | 860 |
| | L-C-160 | as L-C-0, C at 160 | 860 |
| R: the boron reference of the lesson | L-ARO-860 | all banks at their reference positions | 860 |
| O: a different insertion order | O-S3 | SC, SD, SE at 0 | 975 |
| | O-S5 | SC, SD, SE, A, B at 0 | 975 |
| | O-S6 | SC, SD, SE, A, B, C at 0 | 975 |
| | O-D-76 | SC, SD, SE, A, B, C at 0, D at 76 | 975 |
| X: SA and SB, which no combined case had | X-5 | D, C, B, A, SA at 0 | 975 |
| | X-6 | D, C, B, A, SA, SB at 0 | 975 |
| | X-9 | all nine banks at 0 | 975 |

About 5 minutes each (65 minutes in all), one run each; a crashed or stopped case is run again with the same settings (not a second run). Convergence check as in the earlier protocols (batches 101 to 200 against 201 to 300 within 2 standard errors).

**The library:** `libraries/pwr-beavrs-hzp-openmc` rebuilt by `pipeline.library.export_beavrs` with `rodShadowing` in place of `rodInteraction` (everything else as the library of the fourteenth protocol), read by the Python reference engine. The boron dependence is the library's existing boron tables; **nothing in the model carries a boron × bank interaction**, so the groups at 860 ppm carry the interaction of the lesson's own boron (the fourteenth protocol measured about 100 pcm at four banks in and 290 at seven, at 686 and 508 ppm, both far below 860). Measured data for part M: the critical boron at five states (975, 902, 810, 686, 508 ppm, σ 22), the seven sequential worths, the two temperature coefficients, as in the eleventh and twelfth protocols.

## Disclosure: what was seen before writing

This protocol is **not blind**.

- **Seen:** everything in the eleventh, twelfth and fourteenth protocols and their results, including all 45 sweep cases and the nine path cases; the exploratory fits of the plan (the one-table shadowing form, four knots, fitted to the 12 combined cases; its residuals and leave-one-out errors are listed above; a first version with the last knot at −4000 gave g = 0.272, 0.392, 0.328, 0.67 and was changed to −3850 only because no case reaches below −3845); the single-bank worths of the sweep.
- **Not seen:** any of the 13 new cases, at any settings; the library with `rodShadowing`; any reading of the lesson's states by any other method.
- **What the fit cannot know:** which banks sit where in the core, beyond what the rods' own worths carry (the model sees only the others' summed reactivity); the boron × bank interaction.

## Predictions (written before the runs; the results decide)

- **L (the lesson's path):** the library within 100 pcm of transport at L-C-0, L-C-40 and L-C-83 and within 200 pcm at L-C-120 and L-C-160, with the largest errors at the first two (the most banks in at the lesson's boron: the boron × bank interaction of the seven banks, on the order of 50 to 100 pcm at 860 ppm, is not in the model and lowers the library below transport).
- **R:** L-ARO-860 within 100 pcm (the boron table's interpolation between 600 and 975 ppm).
- **O (a different order):** within 200 pcm at three of the four; **the likely failures are O-S3 and O-S5** (the model sees only the others' summed reactivity, and these states have the large shutdown banks SC, SD, SE in first, where the benchmark order never had them without D, C, B).
- **X:** X-5 within 200 pcm; X-6 and X-9 beyond what the model was fitted to (R below −3850 flags outOfDomain): X-9 fails.
- **M:** the critical boron errors of the fourteenth protocol's library (+8.2, +21.6, +17.2, +5.2, +7.7 ppm) change by no more than 20 ppm at any state; all five stay within 50 ppm; the sequential worths and the total are labelled as in the twelfth protocol, with SC the likely failure; the temperature coefficient fails at both states as before.

## The question

(P) Does a correction that scales each rod's worth by a function of the others' summed reactivity reproduce the transport reactivity at states it was not fitted to: first at the states of the lesson (L), then at a different insertion order (O) and at states with SA and SB in (X)? (M) Does the library with it reproduce the measured critical boron, worths and temperature coefficients, and where does it still fail?

## Labels

Library reactivity at the state (rods at the case's steps / 228 withdrawn, boron, `Tfuel = Tcoolant = 566.483 K`, fresh engine at zero power) minus the transport reactivity ρ = (k − 1)/k, in pcm; limit L = max(100 pcm, 3 σ_transport); **good** ≤ L, **plausible** ≤ 2L, **fails** > 2L. For each case also reported: the difference of the summed model without the table, and the fourteenth protocol's table (the library of the fourteenth protocol is rebuilt for this, from the committed exporter, as a comparison only). A case enters `domain.jointChecked` only if good.

## Decision process

1. **The lesson may be built on the library** if all hold: in group L, at least 4 of 5 cases good or plausible and none beyond 300 pcm; L-ARO-860 good or plausible; at least 10 of the 13 cases good or plausible overall and none beyond 400 pcm. The library may then claim the lesson's states (the L cases that are good enter `jointChecked`) and the lesson's envelope is: seven banks in, C withdrawn, boron near 860 ppm.
2. **Fails (the lesson is not built on this model):** the places are named; the user chooses a narrower lesson or stops; no further modelling without a new plan. L-ARO-860 failing means the boron table, not the rods, is the cause, and that is stated.
3. **The order claim:** the library may state that the correction is valid for other insertion orders only if at least 3 of the 4 O cases are good or plausible; otherwise the notes say it is valid along the benchmark order and the lesson's path only.
4. **SA and SB:** the library may state the SA/SB states as checked only for the cases good or plausible among X; X cases beyond the knots are flagged by the engine (outOfDomain) in any case.
5. **M:** as decision 3 of the fourteenth protocol: the claim widens to the states whose critical boron is good or plausible, with the numbers shown; sequential worths and the total labelled as in the twelfth protocol; a failing temperature coefficient keeps the feedback "not validated". P and M are reported side by side; M is not used to change the model.
6. **A case not computed** (unconverged, missing, boron outside the domain) enters no decision item. If the cases that could be computed cannot reach the thresholds of decision 1, the decision is 2.
7. Under all outcomes the library status stays `experimental` and nothing is refitted.

## Implementation (to be written after this protocol is committed)

1. `pipeline/openmc/beavrs_cases.py`: the 13 cases as a third family (`shadow_cases()`, boron per case), runner option `--family shadow`, results in `pipeline/openmc/results/beavrs_shadow.jsonl`; a test of the plan against the table above.
2. The capability: `docs/library-format.md` section 17, schema, both validators, fixtures (valid; invalid: capability missing, field missing, g not zero at R = 0 or axis not decreasing from 0, both v1 and v2 present), both engines (Python first), a golden vector, the gate (every existing vector unchanged except the engine-version pin); a Codex review.
3. The exporter: the fit above, a planted-model test (a planted g recovered from a nonseparable planted sweep), deliberate breaks, the library rebuilt.
4. `validation/m8_rod_shadowing.py` (P and M, run once; refuses a library whose g differs from the values above by more than 0.02) and its planted test with deliberate breaks; results note `m8-rod-shadowing-results.md`.
5. Then the lesson (the draft on `claude/bank-withdrawal-lesson`, rebased on the result).

## Limits, repeated

The model is a function of the others' summed reactivity only; it is checked along the lesson's path, at four other-order states and at three states with SA and SB, and nowhere else. The boron × bank interaction and the temperature tables' rod dependence are not in it. The transport model's own limits (the eleventh protocol) apply: the temperature coefficient is wrong; thermal expansion is not modelled; one boron worth converts the errors; the measured tilt and instrument effects are not in the model.
