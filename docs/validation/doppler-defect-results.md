# The Doppler-defect benchmark: OpenMC with ENDF/B-VIII.0 against Mosteller's reference results: results (2026-10-11)

Protocol: `doppler-defect-protocol.md` (thirteenth protocol, not blind, predictions written first). Runs: `pipeline/openmc/results/doppler_defect.jsonl` (32 cases, each run once, OpenMC 0.15.3, ENDF/B-VIII.0, temperature method `nearest` so every nuclide used its exact 600 K or 900 K set, 20 000 particles × 600 batches with 100 inactive, seeds 1 and 2, 12 OpenMP threads on a quiet machine, about 1.7 minutes a case). Script: `validation/doppler_defect.py`, run once. Full output: `validation/doppler_defect_report.json`. Every metric is reported. Nothing was changed after seeing the results.

## Result in one paragraph

**OpenMC with ENDF/B-VIII.0 reproduces the benchmark's fuel Doppler coefficients: all 15 computed cases are good or plausible (|z| at most 1.61) and every one is within the benchmark author's own 10 % (the largest is +8.8 %, uo2-5.0).** One case, `uo2-1.6`, is **not computed** because its hot-full-power run failed the drift check (z = 3.32, the next highest row is 1.66); per the protocol it is kept and not rerun. **One subset shows a systematic deficit: in UO2 the model's coefficient is less negative than the reference in all six computed cases, by a mean of +5.8 % ± 1.3 %.** The reactor-recycle MOX (mean +2.4 % ± 1.4 %) and weapons-grade MOX (−1.4 % ± 2.7 %) show no pattern. The protocol's decision: item 2 (a UO2 deficit, recorded, nothing refitted), items 5 and 6. Item 1 does not apply, because of the UO2 pattern, although 15 of 15 computed cases are good or plausible.

**The prediction held** ("the UO2 coefficients agree within a few percent; fuel Doppler is not the cause of the BEAVRS coefficient error"), with the small UO2 deficit that the protocol had said would be reported if found.

## A: the Doppler coefficient

| Case | Model DC (pcm/K) | Reference DC (ENDF/B-VII.0) | Difference | z | Label | Spread of the three references |
|---|---|---|---|---|---|---|
| uo2-0.711 | -3.860 ± 0.205 | -4.18 ± 0.20 | +7.6 % | +1.12 | plausible | 0.11 |
| uo2-1.6 | not computed | | | | unconverged row: hfp | |
| uo2-2.4 | -2.432 ± 0.110 | -2.44 ± 0.11 | +0.3 % | +0.05 | good | 0.07 |
| uo2-3.1 | -2.170 ± 0.100 | -2.30 ± 0.10 | +5.7 % | +0.92 | good | 0.05 |
| uo2-3.9 | -2.108 ± 0.089 | -2.20 ± 0.09 | +4.2 % | +0.73 | good | 0.08 |
| uo2-4.5 | -1.936 ± 0.086 | -2.11 ± 0.08 | +8.2 % | +1.48 | plausible | 0.05 |
| uo2-5.0 | -1.934 ± 0.084 | -2.12 ± 0.08 | +8.8 % | +1.61 | plausible | 0.13 |
| reactor-mox-1.0 | -3.644 ± 0.141 | -3.77 ± 0.15 | +3.3 % | +0.61 | good | 0.13 |
| reactor-mox-2.0 | -3.474 ± 0.129 | -3.66 ± 0.14 | +5.1 % | +0.98 | good | 0.10 |
| reactor-mox-4.0 | -3.341 ± 0.114 | -3.42 ± 0.13 | +2.3 % | +0.46 | good | 0.07 |
| reactor-mox-6.0 | -3.122 ± 0.107 | -3.26 ± 0.12 | +4.2 % | +0.86 | good | 0.11 |
| reactor-mox-8.0 | -3.236 ± 0.102 | -3.14 ± 0.12 | -3.1 % | -0.61 | good | 0.11 |
| weapons-mox-1.0 | -2.653 ± 0.107 | -2.83 ± 0.11 | +6.2 % | +1.15 | plausible | 0.13 |
| weapons-mox-2.0 | -2.789 ± 0.097 | -2.71 ± 0.10 | -2.9 % | -0.57 | good | 0.14 |
| weapons-mox-4.0 | -2.859 ± 0.082 | -2.68 ± 0.09 | -6.7 % | -1.47 | plausible | 0.16 |
| weapons-mox-6.0 | -2.542 ± 0.080 | -2.49 ± 0.09 | -2.1 % | -0.43 | good | 0.11 |

## B: k_HZP against the ENDF/B-VII.0 value (reported, not labelled)

| Case | k_HZP offset (pcm) |
|---|---|
| uo2-0.711 | +216 ± 20 |
| uo2-1.6 | +185 ± 27 |
| uo2-2.4 | +61 ± 28 |
| uo2-3.1 | -134 ± 30 |
| uo2-3.9 | -283 ± 29 |
| uo2-4.5 | -356 ± 30 |
| uo2-5.0 | -399 ± 28 |
| reactor-mox-1.0 | +206 ± 27 |
| reactor-mox-2.0 | +209 ± 29 |
| reactor-mox-4.0 | +302 ± 28 |
| reactor-mox-6.0 | +304 ± 28 |
| reactor-mox-8.0 | +447 ± 27 |
| weapons-mox-1.0 | -69 ± 27 |
| weapons-mox-2.0 | -65 ± 28 |
| weapons-mox-4.0 | +113 ± 26 |
| weapons-mox-6.0 | +224 ± 28 |

The offsets run from −399 to +447 pcm and change sign with the enrichment and the fuel. The protocol expected tens to a few hundred pcm from the change of nuclear data (ENDF/B-VIII.0 against VII.0, and the cross-section processing); the largest values (+447 for the 8 wt % reactor MOX, −399 for 5 % UO2) are a little beyond that range. The sign pattern is smooth in enrichment, which argues for a data difference and against a model transcription error (a wrong dimension or density would give a constant offset); the reference k values were not used in any decision.

## C: families

| Subset | n | Mean z | Mean relative difference | Positive / negative | Systematic |
|---|---|---|---|---|---|
| UO2 | 6 | +0.98 | +5.81 % ± 1.30 % | 6 / 0 | **deficit** (|mean| > 2 SE, all six the same sign) |
| Reactor MOX | 5 | +0.46 | +2.38 % ± 1.44 % | 4 / 1 | no |
| Weapons MOX | 4 | −0.33 | −1.36 % ± 2.73 % | 1 / 3 | no |

Positive means the model's coefficient is less negative (weaker) than the reference.

## D: convergence

`uo2-1.6/hfp` failed (z 3.32). The batch values are treated as independent, which probably makes the check too tolerant for a pin cell with strongly correlated batches, so the 31 passing rows are less secure than the numbers suggest (the highest are 1.66, 1.55 and 1.43). That case is excluded from the metrics it enters (its Doppler coefficient and the UO2 subset statistics, n = 6 of 7) and is not rerun under this protocol; a rerun with more inactive batches would be a new dated protocol.

## Decision (protocol)

2. **A systematic deficit in UO2: +5.8 % ± 1.3 % (n = 6, all six positive).** Recorded; nothing refitted. It is small, inside the 10 % the benchmark's author calls acceptable, and it is a statistical pattern of six cases that share data and settings (the error of the mean is the spread over cases, not a model of the cause).
5. `uo2-1.6/hfp` is unconverged; `uo2-1.6` enters no item.
6. This changes what is known about the tool chain, not what any library claims.

## Reading (interpretation, separate from the protocol's labels)

1. **The fuel Doppler treatment is not the cause of the BEAVRS coefficient error.** The BEAVRS model's isothermal coefficient is 1.6 to 2.0 pcm/°F **too negative** (`m8-beavrs-hzp-results.md`); here the fuel Doppler response is, if anything, about 6 % **less** negative than the reference in UO2. A 6 % deficit in a fuel coefficient of about 2.4 pcm/K is 0.14 pcm/K, 0.08 pcm/°F, in the opposite direction: correcting it would make the BEAVRS error slightly worse, not better. The remaining suspects stay those named there (the moderator density term, the ±30 K secant, the thermal expansion that the model fixes, the measurement).
2. **For the TRIGA pin-cell result** (OpenMC's temperature response 15 to 18 % weaker than a Serpent reference): the direction is the same (weaker), but the size here is 6 %, in UO2 fuel, against ENDF/B-VII.0 results of another code; the TRIGA fuel is ZrH-U, whose temperature response is dominated by the hydrogen bound in the zirconium hydride and the thermal spectrum, not by U-238 Doppler broadening. So this is **not** an explanation of the 15 to 18 %. What it does show: OpenMC's UO2 Doppler response is not 15 to 18 % weak, so a defect of that size would have to be in the hydride treatment or in the model, not in the U-238 broadening.
3. **A test of the UO2 deficit** would need the same cases with ENDF/B-VII.0 in OpenMC (to separate the data from the code) and more histories; neither is run here.

## Limits

The reference is another Monte Carlo result (MCNP5 without resonance scattering), not a measurement; the cases that share a data library are not independent samples of OpenMC's error; the seven UO2 enrichments are one fuel family; ENDF/B-VIII.0 differs from VII.0, so a few percent is not by itself a defect of OpenMC. One case is not computed.
