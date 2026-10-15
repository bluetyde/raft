# M8 bank withdrawal near critical: the library as it is, against 7 new held-out transport cases at the states of a narrower lesson (sixteenth protocol, written before any code and before any run of the new cases, 2026-10-15)

This follows the fifteenth protocol (`m8-rod-shadowing-results.md`), which ended with decision 2: the lesson is not built on the shadowing model, and the user may choose a narrower lesson. The user chose it. Two facts from that result shape this protocol: (1) the cases tested at 860 ppm with seven banks in were 2800 to 4400 pcm subcritical, so no case was near a state a startup passes through; (2) the model failed at states with SA and SB in and at one other-order state, and had no problem along the lesson path of seven banks in. A startup lesson only needs the states it passes through, so this protocol asks the narrow question, **at the states of that lesson, with the library exactly as it is, is the library close enough to transport?**

## What is fixed

**The library is not changed.** The analysis refuses a library whose `reactivity` block differs from the one tested here (SHA-256 of the block as canonical JSON with sorted keys and no spaces: `91b18998173ddd54a16ac25ef2108a00938394ec6bb32454bc9d58471ed343bd`; the manifest's `jointChecked` list and notes may change, as they list this protocol's own results). No refit; the 13 cases of the fifteenth protocol and the 12 fit cases stay as they are.

**The lesson's states.** Banks D and C in (steps 0), every other bank at its benchmark reference position (D's bite position does not apply: D is in), boron **900 ppm**, 566.483 K, C withdrawn from 0 toward 228. In the library the state with C in is subcritical (−851 pcm), and it becomes critical at C = 135 steps (0.59 of travel); at the measured critical boron of 975 ppm the benchmark is critical with every rod out.

**The 7 new held-out transport cases** (none run), the sweep's settings (60 000 particles × 300 batches, 100 inactive, IFP off, seed 1), steps withdrawn (0 = in; every bank not named at its reference: D at 213 and the rest at 228 when out):

| Id | State | Boron (ppm) | Library predicts (pcm) |
|---|---|---|---|
| N-C-0 | D, C at 0 | 900 | −851 |
| N-C-40 | D at 0, C at 40 | 900 | −681 |
| N-C-80 | D at 0, C at 80 | 900 | −492 |
| N-C-120 | D at 0, C at 120 | 900 | −134 |
| N-C-140 | D at 0, C at 140 | 900 | +45 |
| N-C-180 | D at 0, C at 180 | 900 | +207 |
| N-C-228 | D at 0, C at 228 | 900 | +303 |

About 5 minutes each (35 minutes), one run each; a crashed or stopped case is run again with the same settings (not a second run). Convergence check as before (batches 101 to 200 against 201 to 300 within 2 standard errors); an unconverged case is kept, labelled, and enters no decision item (the thresholds apply to the computed cases).

## Disclosure: what was seen before writing

This protocol is **not blind**.

- **Seen:** the results of the fourteenth and fifteenth protocols, including the 25 combined cases and their errors; the library's predictions above (computed from the library, not from transport); the choice of boron 900 ppm was made from the library's own critical C position at several boron values (860: 78 steps, 880: 106, 900: 135, 920: 205; 940 never critical), to put the critical position near the middle of travel.
- **Not seen:** any of the 7 cases, at any settings; any transport result at 900 ppm or with only D and C in at any boron other than 975 ppm (the fit case J-W2 is D and C in at 975 ppm: library +83 pcm).
- **What the library cannot know:** the boron × bank interaction is not in it (the fourteenth protocol measured about 100 pcm at four banks in and 290 at seven, at 686 and 508 ppm; with two banks in and 75 ppm below the reference it should be small, and this is the part of the prediction that could fail).

## Predictions (written before the runs; the results decide)

- **P:** the library within 100 pcm of transport at every case (good), the largest differences at the shallow-C cases, where the fit residual of J-W2 (+83 pcm) and any boron interplay add: library less negative than transport at C = 0 and 40 by up to about 100 pcm; near zero at 120 and above.
- **Critical position:** the library's critical C (135 steps, found by bisection on the library) within 15 steps of transport's.

## The question

At the states of a startup with D and C in, boron 900 ppm and C withdrawn, does the library reproduce the transport reactivity, and the position of C at which the core is critical, closely enough that a lesson built on it teaches the right physics?

## Computations and labels

Reactivity is the engine's `reactivity(t, y)["total"]` at the state (rods at the case's steps / 228 withdrawn, boron 900, `Tfuel = Tcoolant = 566.483 K`), from a fresh engine at zero power, in pcm. Transport ρ = (k − 1)/k, σ = σ_k/k². Difference = library minus transport; limit L = max(100 pcm, 3 σ_transport); **good** ≤ L, **plausible** ≤ 2L, **fails** > 2L.

**Critical position.** The library's critical C is the root of its reactivity in C at 900 ppm (bisection between 0 and 228 steps). Transport's is the zero of the straight line through the two transport cases that bracket zero reactivity (N-C-120 and N-C-140 if they bracket it, else the neighbouring pair that does); if no pair brackets zero, the item is not computed. Statistical error of the transport value: the larger of the two cases' σ divided by the slope, reported. The difference (library minus transport) is **good** within 15 steps, **plausible** within 30, **fails** beyond.

## Decision process

1. **The lesson may be built on the library** if: at least 6 of the 7 cases are good or plausible, none beyond 300 pcm, **and** the critical position is good or plausible. The good cases enter `domain.jointChecked`; the lesson's envelope is exactly this state family: D and C in, every other bank at its benchmark position, boron near 900 ppm (within the 25 ppm that the lesson's own tests will show), C withdrawn.
2. **Otherwise** the lesson is not built, the places are named, and the rod-worth work stops here unless the user opens a new plan.
3. A case not computed enters no decision item; if the computed cases cannot reach the thresholds, the decision is 2 (the thresholds apply to the computed cases).
4. Part M is not repeated (the library is the one whose M results are in `m8-rod-shadowing-results.md`). Status stays `experimental`; nothing is refitted.

## Implementation (after this protocol is committed)

1. `pipeline/openmc/beavrs_cases.py`: the 7 cases as a fourth family (`near_cases()`), runner option `--family near`, results in `pipeline/openmc/results/beavrs_near.jsonl`; a test against the table above; the exporter accepts the file as additional held-out cases (so the library's `jointChecked` can list the good ones).
2. `validation/m8_near_critical.py` (the analysis above; run once), a planted test with deliberate breaks, results note `m8-near-critical-results.md`.
3. If decision 1: the lesson (redesigned on the library: D and C in, boron 900, goals and tests rewritten, as the dilution lesson), a browser check, a Codex review, the README and supported-envelope notes. If decision 2: stop.

## Limits

The claim is for one state family only. The library's temperature coefficient is wrong (the lesson holds temperature fixed), the boron × bank interaction is not in the model, and the shadowing correction was fitted to cases at 975 ppm.
