# M8 bank withdrawal near critical: the library as it is against 7 new held-out transport cases: results (2026-10-15)

Protocol: `m8-near-critical-protocol.md` (sixteenth protocol; predictions written first). Library: `libraries/pwr-beavrs-hzp-openmc`, unchanged (reactivity block digest `91b18998…d343bd`, checked by the analysis). Transport: the 7 new cases, OpenMC 0.15.3, ENDF/B-VIII.0, 300 batches, BEAVRS `1ccae04`, run once on 2026-10-15 (21:52 to 22:29, about 5 minutes each), `pipeline/openmc/results/beavrs_near.jsonl`. Analysis run once: `python -m validation.m8_near_critical`, report `validation/m8_near_critical_report.json`. Nothing was refitted.

## Result in one paragraph

**Decision 1 of the protocol (Q1): the lesson may be built on the library.** Six of the seven cases are good or plausible (the seventh did not converge and enters no item), none is beyond 300 pcm (the worst is +198 pcm), and the position of C at which the core is critical is 135.0 steps in the library against 132.6 steps in transport (+2.5 steps, good; the limit for good was 15). The lesson's envelope is exactly the state family tested: banks D and C in, every other bank at its benchmark position, boron near 900 ppm, C withdrawn.

## P: the held-out cases (library minus transport, pcm; limit max(100, 3σ), σ about 25)

| Case | Library | Transport | Difference | Label |
|---|---|---|---|---|
| N-C-0 | −851 | −897 | +46 | good |
| N-C-40 | −681 | −879 | +198 | plausible |
| N-C-80 | −492 | −446 | −46 | good |
| N-C-120 | −134 (library) | not computed (batches 101 to 200 and 201 to 300 disagree, drift z 2.33) | | not computed |
| N-C-140 | +45 | +63 | −19 | good |
| N-C-180 | +207 | +241 | −33 | good |
| N-C-228 | +303 | +303 | 0 | good |

- **N-C-120 was not rerun** (the protocol's rule: an unconverged case is kept and enters no decision item). Its absence widens the transport bracket for the critical position to N-C-80 and N-C-140, so the interpolated transport value (132.6 ± 3.1 steps) rests on a 60-step line; the library's own curve between the same two points is nearly straight (its linear interpolation gives 135 steps, the same as its true zero), which is why I take the interpolation as sound, but it is an interpolation, not a measurement.
- **The weakest point is the shallow C:** N-C-40 is +198 pcm (the library is less negative than transport), and the fifteenth protocol's L-C-40 (seven banks in, 860 ppm) was +268 pcm. Two different state families, the same place: C at about 40 steps. The positive difference is also the sign of the fit residual of J-W2 (+83 pcm at C = 0).
- **Critical position:** the library crosses zero at 135.0 steps (0.592 of travel); transport at 132.6 ± 3.1.

## Predictions

| Prediction | Result |
|---|---|
| Library within 100 pcm at every case (good) | 6 of 6 computed within 200; 5 within 100; N-C-40 +198 (plausible) |
| Largest differences at the shallow-C cases, near zero from 120 up | held (N-C-40 +198, N-C-0 +46; −19, −33, 0 from 140 up) |
| Library critical C within 15 steps of transport's | held (+2.5) |

## What this means

- The library's claim for this state family is justified: reactivity within 100 pcm in five of six computed cases (198 in the sixth) and the critical position within 3 steps of transport's.
- **`domain.jointChecked` now lists 13 good states** (from the fifteenth protocol's 8 and this protocol's 5: C at 0, 80, 140, 180 and 228 with D in), and its notes say that the checks at 860 and 900 ppm hold at those boron values only. The runtime's check matches a state to an entry by rod positions within 0.05 of travel (±11 steps), so the lesson will show "unvalidated" for C between the listed positions (for example about 12 to 68 steps and 92 to 128 steps); that is honest, since those positions were not checked against transport as good, and the lesson will say so.
- Not covered by this result: other bank sets, other boron, temperature (the temperature coefficient is wrong and the lesson holds it fixed), and the boron × bank interaction.
- The library stays `experimental`.

## Next

Build the lesson on this state family (D and C in, boron 900 ppm, C withdrawn to critical at about 0.59 of travel), with scripted-operator tests whose outcomes are written before they run, a browser check, a Codex review and the notes (README, supported envelope, library README). The draft on `claude/bank-withdrawal-lesson` (seven banks in, 860 ppm) is superseded and will be replaced, not edited.
