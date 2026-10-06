# M7 core 134 fuel temperature feedback: diagnostic results (2026-10-06)

Protocol: `m7-core134-feedback-protocol.md` (seventh protocol; not blind, see its disclosure). Runs: the nine OpenMC cases of the protocol, 100 000 particles each (`pipeline/openmc/results/core134_feedback.jsonl`, 5 to 7.5 minutes each). Script: `validation/m7_core134_feedback.py`, run once (`python -m validation.m7_core134_feedback`). Full output: `validation/m7_core134_feedback_report.json`. Every metric is reported. Nothing was changed after seeing the results, and the library was not changed.

## Result in one paragraph

**None of the three candidate causes explains the shortfall; the decision is item 5 of the protocol.** The reference treatment is not an artefact (D1: −48 ± 44 pcm). The first interval is linear within the statistics (D2: slope ratio 0.95 ± 0.11). More fuel hydrogen (H/Zr 1.65) does not change the fuel temperature slope (D3: 1.05 ± 0.13). And the new, better-resolved knots **confirm the library's weak feedback** (D5: the 400 K knot is −679 ± 44 pcm against the library's −657 pcm): the fresh-fuel OpenMC model gives a fuel temperature coefficient of about −6.1 to −6.4 pcm/K from 294 to 400 K, in either composition, and the what-if reactivity loss at the power ascension steps stays 37–40 % below the measurement at steps 4–7 (a shortfall of 140–250 pcm against a 30 pcm statistical error per knot). What remains is the measurement's side (the temperature conversion, the water warming) or OpenMC's treatment of the fuel temperature, none of which these runs test.

## The nine runs

| Run | Composition | Fuel temperature | k | ρ (pcm) |
|---|---|---|---|---|
| A0 | default, H/Zr 1.60 | reference treatment | 1.00396 ± 0.00032 | +394 ± 32 |
| A294 | default | 294 K | 1.00348 ± 0.00030 | +347 ± 30 |
| A330 | default | 330 K | 1.00179 ± 0.00031 | +179 ± 31 |
| A372 | default | 372 K | 0.99871 ± 0.00032 | −129 ± 32 |
| A400 | default | 400 K | 0.99668 ± 0.00032 | −333 ± 32 |
| B294 | 1994 fuel, H/Zr 1.65 | 294 K | 1.01286 ± 0.00033 | +1269 ± 32 |
| B330 | 1994 fuel | 330 K | 1.01006 ± 0.00029 | +996 ± 28 |
| B372 | 1994 fuel | 372 K | 1.00777 ± 0.00030 | +771 ± 30 |
| B400 | 1994 fuel | 400 K | 1.00560 ± 0.00033 | +557 ± 32 |

(The 1994 fuel's reactivity is 820 to 920 pcm above the default at every temperature, as the gate found.)

## The metrics

- **D1, the reference treatment:** `ρ(A294) − ρ(A0) = −48 ± 44 pcm`. Within 2σ (88 pcm): **no artefact**. The sign and size are noise-compatible; the whole table is not shifted by the interpolation option.
- **D2, linearity of the first interval (default composition):** slopes from 294 K are −4.65 ± 1.2 (330 K), −6.10 ± 0.57 (372 K) and −6.41 ± 0.42 pcm/K (400 K). The ratio 372/400 is **0.95 ± 0.11: linear** (band 0.85–1.15). The 330/400 ratio (0.73) is lower but carries ±0.19 from a slope over 36 K measured with 30 pcm per run, and the protocol's label uses the 372 K ratio.
- **D3, composition:** the slopes with H/Zr 1.65 are −7.59 ± 1.2, −6.39 ± 0.56 and −6.72 ± 0.43 pcm/K; B/A is 1.05 ± 0.13 at 372 K and 1.05 at 400 K: **no effect** (band 0.9–1.1). The 330 K slope is the one place where B differs from A (−7.6 against −4.65) and the difference is 1.7σ.
- **D4, the what-if reactivity loss at steps 1–7 of Table IX with the new knots:**

| Step | Mean fuel (°C) | Measured (pcm) | A what-if | B what-if |
|---|---|---|---|---|
| 1 | 29.5 | 49.6 | 29 plausible | 52 good |
| 2 | 38.9 | 118.9 | 65 fails | 116 good |
| 3 | 51.5 | 217.6 | 116 fails | 204 good |
| 4 | 66.8 | 344.8 | 206 fails | 290 plausible |
| 5 | 78.6 | 460.6 | 285 fails | 346 plausible |
| 6 | 89.3 | 563.6 | 355 fails | 395 fails |
| 7 | 98.7 | 666.0 | 417 fails | 438 fails |

Primary labels **fail** for both compositions (worst fails; the best over the sensitivities is "fails" for A and "plausible" for B). The B what-if is better at the first steps only because its 330 K knot is 105 pcm deeper than A's; the two differ by 1.7σ there, and the two compositions have the same 372 and 400 K knots to within the statistics, so the better early labels are a statistical fluctuation of one knot, not a hydrogen effect. At steps 4–7 both fall 40 % short.
- **D5, consistency:** the library's own 400 K knot (−657 pcm, 20 000 particles) and the rerun (−679 ± 44 pcm, 100 000 particles) agree: the sweep's table was statistically right.

## Reading (interpretation, separate from the protocol's labels)

1. **The weak feedback is a result of the OpenMC model, not noise, method or composition.** The 294 to 400 K slope is −6.1 to −6.4 pcm/K for fresh fuel in both compositions. The burned libraries (23.7 MWd/kg) have −7.8 and −8.1 over the same interval, so burnup raises the magnitude; the measurement of the fresh core needs about −8.6 pcm/K.
2. **A rough estimate of what the measurement side would have to change** (not a metric): the step 7 reactivity loss is 666 pcm; the model's fuel slope of about −6.3 pcm/K and its coolant term (+13.5 pcm/K over a 4 K warming) need a mean fuel rise of about 114 K to give it, against the 77 K the paper's conversion (γ_B 1.525) gives. That corresponds to a conversion near 1.0 to 1.1, not 1.5, i.e. a thermocouple that reads about the same rise as the volume-mean fuel temperature. It contradicts the paper's own γ (from the power and radial temperature distributions), so either the paper's conversion overestimates γ for this experiment or the model's feedback is too weak (or both). **These runs cannot tell which.**
3. **The water term is not the whole story.** The model's coolant coefficient (+13.5 pcm/K) times the assumed 8 K warming is about +108 pcm at the end of the experiment, where the paper estimates the water contribution to the total power defect at 20 pcm. Using the paper's 20 pcm instead would add about 54 pcm to the model's loss at step 7 and leave 130 to 200 pcm unexplained.
4. **Candidates not tested** (and each would need its own protocol): the temperature treatment of the thermal scattering tables of the zirconium hydride in OpenMC (the pipeline keeps the nuclide data at 294, 600 and 900 K and interpolates, the ZrH tables are finer); whether the real fuel temperature coefficient of fresh TRIGA fuel is stronger than ENDF/B-VIII.0's ZrH treatment gives; and a measurement of the same quantity in an independent source (the 2002 isothermal and fuel coefficients, whose conversion carries the same γ question).

## Decision (protocol)

- **Item 5:** none of the three explains it. **Nothing in the library changes**; it stays `experimental`, and the seventh-protocol runs add no table.
- **No power ascension comparison on this library yet.** The regulating rod is right and the fuel feedback is 40 % short at 99 °C, so a comparison would test the temperature conversion and the heat transfer together without separating them.
- **Not tried after seeing the results (per the protocol):** other temperatures, other hydrogen contents or particle counts, other water temperatures, a fit of anything.

## Limits, repeated

One OpenMC model of one core, 30 pcm per run; the 330 K slopes carry ±1.2 pcm/K; the measurement's temperature conversion and the water warming are assumptions; the what-if tables are diagnostics, not libraries. The comparison says the OpenMC fuel feedback of this core is 40 % weaker than the measurement needs under the paper's own conversion, not that the conversion or the model is right.
