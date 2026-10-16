# M8 follow-up: pair terms for the combined rod worth: plan (2026-10-15)

Why: the fourteenth protocol's part P failed (`docs/validation/m8-rod-interaction-results.md`): a correction that depends only on the summed single-rod reactivity S misses the held-out path cases by up to 364 pcm. This plan sets up the next candidate, the one the protocol named: a rod's correction as a function of the reactivity of the *other* rods. Nothing here is built or run yet; the protocol (a fifteenth) comes next and is committed before any code or run.

## 1. What I looked at first (existing data, already seen; not a test)

All 12 combined transport cases (J-W2, J-W4, J-W7 and the nine path cases) were used below. They are **spent as held-out data**: any model fitted to them needs new held-out cases (section 3). Scripts: scratchpad only (`pairlook.py`, `pairlook2.py`); the numbers are repeated here so they can be redone.

1. **S alone cannot carry it, for any table shape.** P-A-76 (D, C, B in, A two thirds inserted) and J-W4 (D, C, B, A in) have the same S (−2633 pcm) and the same sum of pair products (2.476e6 against 2.475e6), but need corrections of −942 and −1106 pcm: 164 pcm apart, about 4.4 times the combined statistical error (26 and 27 pcm). So a function of S, or of S and the pair sum, is ruled out; what differs is which banks are in and how far.
2. **A one-table shadowing model fits much better.** Each rod's worth is scaled by its surroundings: correction = Σ_i w_i(x_i) · g(R_i), with R_i = S − w_i the reactivity of all the other rods and g one table (g(0) = 0, piecewise linear, knots at 0, −1000, −2000, −3000, −4000 pcm; four free values). Fitted to all 12 cases: residuals −77 to +129 pcm (11 of 12 within 100), against up to 364 for the S-only table. Leaving each case out in turn: errors −97 to +167 pcm (9 of 12 within 100). The fitted g is 0.27, 0.39, 0.33, 0.67 at the four knots (the last is poorly determined: only J-W7 reaches it). J-W4 is the worst case in both.
3. **Reading:** the shadowing form is the right kind of model (it is the S-only table plus a dependence on which rod is moving), but four numbers fitted to 12 cases leave residuals of 3 to 5 sigma at J-W2 and J-W4. It may pass the 100 pcm limit on new cases, or it may not; the protocol decides, not this note.

## 2. The change: capability `point-kinetics/rod-interaction-v2`

- **Library field:** `reactivity.rodShadowing = { R, g, unc?, interp, outOfRange, source }`. R is the reactivity of the other rods, g the fractional change of a rod's worth (g(0) = 0, axis strictly increasing, same checks as `rodInteraction`).
- **Engine:** `rho_total = reference + calibration + Σ w_i(x_i) · (1 + g(S − w_i(x_i))) + ...`; the snapshot gains the breakdown field. Python reference engine first, then TypeScript, one golden vector with a planted answer, the gate as before (every existing vector unchanged).
- **Relation to v1:** v2 replaces v1 in the BEAVRS library (a library carries one of them; a library with both is refused by the validators). v1 stays in the format and the engines (it is built, tested and reviewed; the TRIGA libraries are untouched).
- **Joint check:** same rule as v1 (a state with a non-zero correction needs a `jointChecked` entry; `R_JOINT_UNCHECKED` otherwise). Axis range sets `R_DOMAIN_ROD_INTERACTION`-style outOfDomain flag.

## 3. New held-out cases (the fit uses the 12 seen cases only)

About 12 new OpenMC cases, run once, settings as the sweep (975 ppm, 566.483 K, 300 batches; about 5 minutes each, so about 1 hour; needs the user's go and an idle machine). Chosen to be **different from what the fit saw**, and to include the states the lesson passes through, with the earlier path states mostly absent:

- the lesson's own withdrawal path: the seven banks in, then C withdrawn in steps (say 3 states), then B, then A (3 more);
- a different insertion order from the benchmark (for example SC, SD, SE in first, then D): 3 states, which tests the claim that the correction does not depend on the order;
- two states with SA and SB in (they never appeared in a combined case; the model's R range is extended by them).

The exact list is fixed in the protocol, before the run. Cases are labelled as in the fourteenth protocol (good ≤ max(100 pcm, 3σ), plausible ≤ 2×, fails beyond); the decision is the same (at least 7 of the new 12 good or plausible, none beyond 400 pcm; I would add: at least 3 of the order-different states, so the claim is not only about the benchmark order).

## 4. The protocol (fifteenth), written before any code or run

Part P as above, part M as the twelfth (critical boron, worths, ITC, differences from transport), predictions written first. The fit rule is fixed in the protocol: knots, weights (the statistical errors), monotonicity if any, how g at −4000 is held when only one case reaches it. **Predictions I would write now:** 8 or more of 12 within 100 pcm for the lesson's own path and the SA/SB states; the different-order states are the likely failures (the model assumes the effect depends only on the others' reactivity, not on their positions in the core).

## 5. Work, in order

1. This plan, then the protocol (fifteenth), committed; the case list in the protocol.
2. Format section 17, schema, both validators, fixtures (valid; invalid: capability missing, field missing, not zero at R = 0, axis not increasing, both v1 and v2 present), tests.
3. Engines (Python, then TypeScript), golden vector, gate; Codex review of the capability.
4. Exporter: the fit, a planted-model test (a planted g that the exporter must recover from a nonseparable planted sweep), deliberate breaks, the library rebuilt.
5. The new cases (the user's go), the analysis script (P and M, run once) with planted test and deliberate breaks, the results note.
6. If P passes: the lesson (draft is on `claude/bank-withdrawal-lesson`: rebase it, add the library update, the README and supported-envelope notes, Codex review, browser check). If P fails: the lesson ships only with a narrower envelope that the user chooses, or not at all.

About two working days plus about one hour of machine time, as before.

## 6. Risks

1. The model may fail again, for a reason a function of the others' reactivity cannot see (which bank is where in the core). Then the remaining options are a pair table per bank pair (36 numbers, far more cases) or giving up on combined worth in the library and teaching the lesson with a smaller claim.
2. Four numbers fitted to 12 cases is a low ratio for a table the lesson trusts; the held-out set is what makes this honest, and it is not optional.
3. The poorly determined end of g (−4000 and beyond) is where SA and SB would go; the validity flag stays on there.
4. The boron × bank interaction and the temperature tables' rod dependence stay out (as in the first plan).

## 7. Decisions I need from you

1. **Go with this plan** (write the fifteenth protocol next, then build): recommended.
2. **The new cases:** run them (about 1 hour, best overnight, as soon as the code exists), or accept the model unchecked (not recommended: that is what failed).
3. **If it fails:** a narrower lesson (your choice then), not another round of modelling, unless you say otherwise.
