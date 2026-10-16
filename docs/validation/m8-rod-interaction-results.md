# M8 rod interaction: the correction table against held-out transport cases: results (2026-10-15)

Protocol: `m8-rod-interaction-protocol.md` (fourteenth protocol; predictions written first). Library: `libraries/pwr-beavrs-hzp-openmc` (rod-interaction table fitted to J-W2, J-W4, J-W7 only). Transport: the nine path cases, OpenMC 0.15.3, ENDF/B-VIII.0, 300 batches, BEAVRS `1ccae04`, run once on 2026-10-14 (22:58 start, about 5 minutes per case), results in `pipeline/openmc/results/beavrs_path.jsonl`. Analysis run once: `python -m validation.m8_rod_interaction`, report `validation/m8_rod_interaction_report.json`. Nothing was refitted.

## Result in one paragraph

**The single-axis correction does not hold along the benchmark path: decision 2 of the protocol.** Of the nine held-out cases, seven converged. Of those, four are plausible and none is good, and three fail (library minus transport −263, −355 and −364 pcm). Every one of the seven differences is negative (the library is more negative than transport) and the size grows with the number of banks in. Two cases (P-SE-76, P-SC-76) did not pass the drift check (z 2.25 and 2.69) and are not computed; they were not rerun. They cannot change the decision: even with both counted as plausible, 6 of 9 is below the 7 required. The bank-withdrawal lesson is therefore **not** built on this table.

## P: the held-out cases (library minus transport, pcm; limit L = max(100, 3σ))

| Case | Library | Transport (σ) | Difference | Without the table | Label |
|---|---|---|---|---|---|
| P-C-76 | −1539 | −1413 (25) | −127 | +166 | plausible |
| P-B-76 | −2831 | −2681 (26) | −150 | +638 | plausible |
| P-A-76 | −3637 | −3473 (26) | −164 | +942 | plausible |
| P-S3 | −3259 | −3133 (26) | −126 | +831 | plausible |
| P-S5 | −4308 | −4045 (26) | −263 | +1092 | fails |
| P-SD-76 | −4901 | −4546 (28) | −355 | +1218 | fails |
| P-S6 | −5142 | −4778 (25) | −364 | +1299 | fails |
| P-SE-76 | not computed (drift z 2.25) | | | | |
| P-SC-76 | not computed (drift z 2.69) | | | | |

- No case is beyond 400 pcm, but the count (4 of 9 good or plausible, at most 6 even if the two were counted) is below 7.
- The table improves on the summed model in all seven computed cases (the differences without the table are +166 to +1299 pcm). By the protocol's rule it therefore stays in the library; it is not adopted as validated.
- `domain.jointChecked` is empty (no case is good), and the manifest notes say "0 within the limit".
- I did not test why the differences are all negative. The fit used three points and held the anchors at zero; the cases between and beyond them are all on the same side.

## M: the twelfth protocol's metrics on this library (reported side by side, not used to change the table)

- **A, critical boron:** +8.2, +21.6, +17.2, +5.2, +7.7 ppm at S0, S1, S2, S4, S7: all good, all within 50 ppm. This is by construction at S2, S4, S7 (the fit cases).
- **B, sequential worths:** D −3.5 % good, C +2.8 % good, B +16.4 % (fails after the shared-table erratum), A −30.8 % (fails after the erratum), SE +45.4 % (fails after the erratum), SD +8.0 % good, SC −28.6 % fails; total 6028 vs 6042 pcm (−0.2 %, good). The as-run labels and the erratum labels are both in the report.
- **C, temperature coefficient:** −3.57 pcm/°F at both S0 and S2 against −1.75 and −8.01 measured: fails at both. The temperature feedback stays not validated, and the library has no rod dependence of its temperature tables.
- **F, library minus transport at the fit and check cases:** the three fit cases and R-D-0 equal transport by construction; J-B4 +96, J-B7 +290 pcm (J-B7 exceeds the limit).

The critical-boron result in A is a fit result, not a held-out one. The held-out result is P, and it fails.

## What this means

- The library's claim stays as it was: the combined rod worth is correct at the three fitted states and at all rods out, and not shown anywhere else. The lesson that withdraws banks passes through the unchecked states between them.
- The status stays `experimental`.
- Next candidate, as the protocol says: pair terms (a bank's correction as a function of the reactivity of the others), which is a separate plan and protocol. The draft lesson stays on `claude/bank-withdrawal-lesson`, not merged.
- Open for the user: whether to plan pair terms now, or to ship the lesson with an envelope limited to the fitted states (a different lesson, and not what was asked for).
