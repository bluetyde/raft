# M8 BEAVRS hot zero power: the transport model against the cycle 1 physics tests: results (2026-10-07)

Protocol: `m8-beavrs-hzp-protocol.md` (eleventh protocol; not blind, see its disclosure). Runs: `pipeline/openmc/results/beavrs_hzp.jsonl` (20 cases, each run once, ENDF/B-VIII.0, OpenMC 0.15.3, BEAVRS head `1ccae04`, seed 1). Script: `validation/m8_beavrs_hzp.py`, run once (`python -m validation.m8_beavrs_hzp`). Full output: `validation/m8_beavrs_hzp_report.json`. Every metric is reported. Nothing was changed after seeing the results, and no library exists yet.

## Result in one paragraph

**The model reproduces the critical boron: all five states are within 1σ of the measurement (errors +8, +21, +16, −2 and −15 ppm against 22 ppm of measurement uncertainty, all within the 50 ppm licensing criterion), with no systematic offset (mean +5.5 ppm).** The bank worths are good or plausible wherever they were computed (B +6 %, A −8 %, SE −12 %, SD −5 %, SC +4 %; the total of the seven banks is within 0.2 % of the measured 6042 pcm). **Two worths (D and C) are not computed, because the case W1 failed the drift check.** **The isothermal temperature coefficient fails at both states: the model is more negative than the measurement by 1.56 pcm/°F (all rods out) and 2.03 pcm/°F (C and D in), about 3σ of the combined uncertainty, with a model error of only 0.135 pcm/°F, so the difference is not statistical.** The protocol's decision: items 1, 4, 5 and 6 apply.

## A: critical boron (error positive = the model needs more boron than was measured)

| State | Measured (ppm) | ρ at the measured boron (pcm) | Error (ppm) | z | Label |
|---|---|---|---|---|---|
| S0, all rods out | 975 | +101 ± 25 | +8.0 ± 2.0 | +0.36 | good |
| S1, D in | 902 | +267 | +21.1 ± 2.0 | +0.96 | good |
| S2, C and D in | 810 | +197 | +15.6 ± 2.1 | +0.71 | good |
| S4, A to D in | 686 | −29 | −2.3 ± 2.0 | −0.11 | good |
| S7, A to D, SE, SD, SC in | 508 | −188 | −14.9 ± 2.0 | −0.67 | good |

The conversion uses the boron worth at S0, 12.61 ± 0.18 pcm/ppm. At S7 it is 12.84 ± 0.17 (+1.8 %, below the 5 % that would mark S4 and S7 as sensitive); with the S7 value the errors change by at most 0.3 ppm. Aggregate: mean +5.5 ppm, spread-based standard error 6.4, three of five positive: **no systematic offset**. In pcm the mean is +70 (the model is that much more reactive at the measured boron, on average; the first sight of this model gave +75 ± 45 pcm at S0 and now +101 ± 25).

## B: bank worths

| Bank | Measured (pcm) | Model (pcm) | Difference | z | Label |
|---|---|---|---|---|---|
| D | 788 | not computed (W1 unconverged) | | | |
| C | 1203 | not computed (W1 unconverged) | | | |
| B | 1171 | 1238 ± 37 | +67 (+5.7 %) | +1.38 | plausible |
| A | 548 | 505 ± 38 | −43 (−7.9 %) | −0.94 | good |
| SE | 461 | 408 ± 37 | −54 (−11.6 %) | −1.19 | plausible |
| SD | 772 | 733 ± 36 | −39 (−5.1 %) | −0.86 | good |
| SC | 1099 | 1149 ± 36 | +50 (+4.5 %) | +1.04 | plausible |
| Total of seven | 6042 (σ 77) | 6028 ± 36 | −14 (−0.2 %) | −0.16 | good |

The total uses W0 and W7 only, so it does not depend on W1. As an arithmetic consequence of computed cases (not a protocol metric, and it says nothing about D and C separately), the model's D and C together are the total minus the other five banks: 6028 − 4031 = **1997 pcm against the measured 788 + 1203 = 1991**.

## C: isothermal temperature coefficient

| State | Measured (pcm/°F) | Model (pcm/°F) | Difference | z | Label |
|---|---|---|---|---|---|
| S0, all rods out | −1.75 ± 0.54 | −3.31 ± 0.135 | −1.56 | −2.81 | fails |
| S2, C and D in | −8.01 ± 0.54 | −10.04 ± 0.135 | −2.03 | −3.65 | fails |

The cases: k at 536.483 K and 596.483 K with the water at 0.79165 and 0.67119 g/cm³ (IAPWS-IF97, 15.5 MPa), every material at the case temperature. The model difference between the two states (−6.73 pcm/°F) is close to the measured one (−6.26): the shift is almost the same at both states.

## D, E: boron worth check and convergence

- D: above.
- E: **W1 failed the drift check (z = 2.33).** Every other case passed. The values near the limit are B7 1.96, B2 1.85, W2 1.84, K7a 1.78, B4 1.57; the T cases are 0.94–1.35. The check treats batch values as independent, which probably makes it too tolerant at a full core's batch correlation (so passing cases are less secure than the numbers suggest, and W1's failure is a real warning). Per the protocol W1 is kept, not rerun, and enters no decision item; a rerun with more inactive batches would be a new dated protocol.

## Decision (protocol)

1. **Critical boron:** five good, no systematic offset: the library of step 3 is built without a calibration offset (item 1).
2. **Bank worths** (item 3): no bank fails among those computed; D and C are not computed (item 5).
3. **ITC fails** (item 4): the library's temperature feedback is marked not validated at HZP.
4. The library status stays `experimental`, and step 2 (the format fit check) goes ahead (item 6).

## Reading (interpretation, separate from the protocol's labels)

1. **The criticality and the shutdown-bank strength are right, the temperature feedback is not.** The model is 1.6–2.0 pcm/°F too negative in both states, while the boron worth and the bank worths agree with the measurement. The moderator density term is a first suspect (the water density falls by 15 % between the two temperatures), but nothing here tests it.
2. **Candidate causes not tested:** (a) the secant over ±30 K against the measurement's ±5 °C (a curvature of the feedback in this range would show up here; the protocol chose the larger range for statistics); (b) thermal expansion of the fuel and structures, which the model fixes (the protocol's limit); (c) the pressure of the water density (15.5 MPa is nominal); (d) the measurement itself (its stated 0.54 pcm/°F is an estimate, and the Krsko literature value the benchmark quotes is 1.8). None is a refit target; each would be a dated protocol.
3. **The coolant temperature feedback of the future library comes from these cases,** so the library inherits the shift; item 4 says so.
4. **The 100 ± 25 pcm at S0** (the model slightly above critical at 975 ppm) and the +5.5 ppm mean are inside the benchmark's 22 ppm; the first sight (+75 ± 45) agrees.

## Timing and a correction to the step 0 note

Total wall time of the 20 cases: 4.07 hours, with the machine's load average between 9 and 27 (other agents; the T2m case ran into a load of 27). **The CPU time recorded per case (4 600–8 600 s for the standard cases against 2 300 s in the step 0 gate run of the same size) is not a clean cost measure under contention:** OpenMP threads spin while waiting, so CPU time grows with the load. The step 0 note said that CPU time per history is the figure to trust; that was wrong for a shared machine. The real comparison with the TRIGA cases is still the quiet-machine one (about 1.1×, from the step 0 run at a load of 5).

## Limits, repeated

Seven worths treated as independent; the ITC omits thermal expansion; one boron worth converts every error; the drift check assumes independent batches; the seed is the same (1) in every case, so statistical errors of cases that share a source start are not fully independent (this also applies to all differences above; the protocol took them as independent). The shipped model has the benchmark's instrument tubes, not the tilt.

## Errata (2026-10-10, from the Codex review of the milestone)

- The runner did not check that the BEAVRS clone was at the commit the protocol fixes (`1ccae04`); it now does (`pipeline/openmc/beavrs_cases.py`, `check_beavrs_head`) and records the head in each new result row. The 20 rows of this note and the 45 of the sweep were run from the clone at `1ccae04` (the core file generator checks it too), but they do not carry the field.
- The analysis marked no state as sensitive to the boron worth conversion, because the S0/S7 boron worth differs by 1.8 % (under 5 %); the code now sets the flag only on S4 and S7, as the protocol says, and only above 5 %. No result here changes.

