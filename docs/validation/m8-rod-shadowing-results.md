# M8 rod shadowing: the library against 13 new held-out transport cases and the cycle 1 physics tests: results (2026-10-15)

Protocol: `m8-rod-shadowing-protocol.md` (fifteenth protocol; predictions written first). Library: `libraries/pwr-beavrs-hzp-openmc` with `rodShadowing` (rod-interaction-v2), g = 0.272, 0.392, 0.328, 0.618 at R = −1000, −2000, −3000, −3850 pcm, fitted to the twelve combined cases of the earlier protocols. Transport: the 13 new cases, OpenMC 0.15.3, ENDF/B-VIII.0, 300 batches, BEAVRS `1ccae04`, run once on 2026-10-15 (15:57 to 17:00, about 5 minutes each; all 13 converged), `pipeline/openmc/results/beavrs_shadow.jsonl`. Analysis run once: `python -m validation.m8_rod_shadowing`, report `validation/m8_rod_shadowing_report.json`. Nothing was refitted. Before the run, a Codex review changed the analysis in five places (a missing case reported as not computed, the thresholds applied to the computed cases, the shadowing error cancelling between states with the same rods, the whole axis pinned, a note on boron); none of the 13 results had been seen.

## Result in one paragraph

**Decision 2 of the protocol: the lesson is not built on this model.** Nine of the 13 cases are good or plausible (ten were needed), and two are beyond 400 pcm (X-5 +562, X-6 +700: states with SA and SB in). The lesson's own group did well by the rule it was given (four of five good or plausible, none beyond 300 pcm, L-ARO-860 good), so the failure is in the groups I added for generality, not in the lesson path. **But the lesson's states turned out not to be critical states** (next section), so that result does not carry the weight it appears to.

## P: the held-out cases (library minus transport, pcm; limit max(100, 3σ), σ about 27)

| Group | Case | Library | Transport | Difference | Without the table | Label |
|---|---|---|---|---|---|---|
| L | L-C-0 | −4417 | −4494 | +76 | +1994 | good |
| L | L-C-40 | −4113 | −4381 | +268 | +2001 | fails |
| L | L-C-83 | −3735 | −3644 | −92 | +1417 | good |
| L | L-C-120 | −3280 | −3228 | −52 | +1236 | good |
| L | L-C-160 | −2953 | −2944 | −9 | +1165 | good |
| R | L-ARO-860 | +1576 | +1625 | −49 | −49 | good |
| O | O-S3 | −1715 | −1607 | −108 | +266 | plausible |
| O | O-S5 | −3337 | −3369 | +32 | +972 | good |
| O | O-S6 | −4376 | −4298 | −78 | +1084 | good |
| O | O-D-76 | −5305 | −5021 | −284 | +1275 | fails |
| X | X-5 | −4401 | −4962 | +562 | +1746 | fails |
| X | X-6 | −5908 | −6607 | +700 | +2580 | fails |
| X | X-9 | −8915 | −8854 | −60 | +3384 | good |

- **Against the summed model** the table is a large improvement everywhere a rod is in (the sum is off by +266 to +3384 pcm). The one case where "the table does not improve on the sum" is flagged (L-ARO-860) has no rod moved, so the table adds nothing and the two differences are equal; that is not a defect.
- **Order claim (decision 3):** 3 of 4 other-order cases are good or plausible, so the library may state the correction for other insertion orders. It fails only at O-D-76 (D part-way with six banks in, −284).
- **SA and SB (decision 4):** X-9 (all nine in) is good; X-5 and X-6 (SA, then SA and SB, added to D to A) fail by +562 and +700 pcm, in the direction of the library being less negative. The model saw no case with SA or SB in.
- **Library listing:** `domain.jointChecked` lists a good case only if its power shape is also within one mean bin (the exporter did not apply that limit at first; on 2026-10-18 a code review found it, and of the eight good cases only the all-rods-out state, L-ARO-860, stays listed; the others have shape errors of 1.7 to 2.6 mean bins). The checks at 860 ppm hold at that boron only: the entries carry a boron window of ±10 ppm (added 2026-10-18; at first the entry had no boron field and the notes alone said so).

## Predictions

| Prediction | Result |
|---|---|
| L: within 100 at L-C-0, L-C-40, L-C-83; within 200 at L-C-120, L-C-160 | 4 of 5 held; L-C-40 +268 |
| R: L-ARO-860 within 100 | held (−49) |
| O: at least 3 of 4 within 200; likely failures O-S3 and O-S5 | 3 of 4 held; but the failure is O-D-76, and O-S3 and O-S5 were good or plausible |
| X: X-5 within 200; X-9 fails | both wrong: X-5 fails (+562), X-9 is good (−60) |
| M: critical boron errors move by no more than 20 ppm, all within 50 | held (see below) |
| M: SC the likely failure of the worths | not held: SC is good (+4.2 %) |
| M: the temperature coefficient fails at both states | held |

## M: the twelfth protocol's metrics on this library (side by side, not used to change the model)

- **A, critical boron (library minus measured):** +8.2, +21.6, +23.7 (plausible), +15.3, +10.4 ppm at S0, S1, S2, S4, S7; all within 50 ppm. The values at S2, S4 and S7 are not independent of the fit cases (three of the twelve).
- **B, sequential worths:** D −3.5 % good, C −4.1 % good, B +12.4 %, A −30.5 %, SE +24.6 % (all plausible, and after the shared-table erratum B, A and SE fail), SD −14.0 % (plausible after the erratum), SC +4.2 % good; total 5993 against 6042 pcm (−0.8 %, good).
- **C, temperature coefficient:** −3.57 pcm/°F at both states against −1.75 and −8.01 measured: fails at both. The temperature feedback stays not validated.
- **F:** J-W2 +83, J-W4 +129 (exceeds), J-W7 +35, J-B4 +226 (exceeds), J-B7 +325 pcm (exceeds). The boron × bank interaction is not in the model; it appears here at the two measured-boron states.

## What I got wrong in the protocol

The lesson cases L-C-0 to L-C-160 were taken at 860 ppm from the draft lesson's numbers. In this library, with seven banks in, **the state at 860 ppm is 2800 to 4400 pcm subcritical at every C position** (library: −4417, −3735, −2953, −2829 pcm at C = 0, 83, 160, 228 steps; transport agrees within 100 pcm at four of the five tested). The library is critical with seven banks in and C out only near 600 ppm (+380 pcm at C = 160, 600 ppm; −261 pcm at 650 ppm). The draft lesson was made against the earlier library, where the sum of single-bank worths was less negative; its numbers (860 ppm, critical at 0.362) do not hold now. So the L cases test the model well away from the states a bank-withdrawal startup would pass through, and a lesson would need cases near critical (boron about 600 to 650 ppm, C well out). I did not see this before the run; it comes from the library with its present table, which I had not tabulated at those states.

## What this means

- Decision 2 stands as the protocol states it. The library's claim widens only as above: the critical boron is within 50 ppm at five states; the order claim holds at 3 of 4; the table is a large improvement over the sum; the library stays `experimental`.
- The bank-withdrawal lesson is **not** built, and its draft on `claude/bank-withdrawal-lesson` is stale (its boron and critical position do not match this library).
- Options for the user (no further modelling without a new plan, as the protocol says):
  1. **A narrower lesson**, designed on this library: seven banks in, boron near 600 to 650 ppm, C withdrawn to critical. It needs a sixteenth protocol with new held-out cases at those states first (about 6 cases, 30 minutes), because none of the 13 is near critical.
  2. **Stop** the rod-worth work here and leave the bank lesson out.
