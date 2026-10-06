# M7 core 134 fuel temperature feedback: diagnostic protocol (seventh protocol, written before any run of it, 2026-10-06)

It follows the sixth protocol (`m7-core134-library-protocol.md`) and its results: the core 134 library reproduces the regulating rod but its fresh-fuel feedback table is 17 % low at the first step of the power ascension and **36 % low at 99 °C average fuel temperature**. This protocol runs new OpenMC cases of core 134 to find out whether three candidate causes explain it. It changes nothing in the library; a library change, if one follows, needs its own protocol. Nothing here has been run.

## Disclosure: what was seen before writing

This protocol is **not blind**.

- The sixth protocol's results: the library's fuel table is linear between its first two knots (0 at 294 K, **−657 pcm at 400 K**, so −6.2 pcm/K), while Table IX needs a mean of about −8.6 pcm/K over 22–99 °C (the measured loss at 372 K, 666 pcm, already exceeds the table's value at 400 K).
- **The statistical uncertainty of the library's table was not carried into those labels.** The 41-case sweep used 20 000 particles per case; each case's k has a standard error of about 0.0007, so each knot of the table has about 0.0009 (90 pcm) of uncertainty, 14 % of the −657 pcm at 400 K (the manifest's `unc`). The 36 % shortfall at step 7 is therefore about 2.6 standard deviations, not a certainty. This protocol is built with enough statistics to settle that.
- The gate (`core134-library-gate.md`): with the benchmark's own fuel composition (H/Zr 1.65 against the default 1.60) the model's **reactivity** rose by about 960 pcm; **no feedback or fuel temperature case was run with it.**
- A methodological suspicion made while writing the sweep: the reference case of the library runs with OpenMC's default temperature treatment, while every fuel-temperature case sets `--tfuel`, which switches the run to interpolation between the data temperatures (`core_model.py`, tolerance 10 K). If the two treatments give a different reactivity at the same 294 K, the whole fuel table carries that difference as an offset. **Not checked.**
- **Not seen:** any new run of core 134 with a temperature between 294 and 400 K, with the fuel temperature given explicitly at 294 K, or with the 1994 composition at a raised fuel temperature.

## The three candidate causes and what each would look like

1. **A method artefact at the reference** (default treatment at 294 K against interpolation mode at 294 K): the whole table is shifted by the difference.
2. **Non-linearity inside the first interval:** the real loss curve is convex (the measured slope grows with temperature, −6.3 to −8.3 pcm/K), so a straight line between 294 and 400 K is wrong in between, and the 400 K knot may be about right while the values at 330–372 K are too low or too high.
3. **The fuel composition:** more hydrogen in the fuel (H/Zr 1.65, the 1994 value) may make the fuel temperature coefficient stronger.

## The runs (all core 134, rods at the library's reference state T=0, K=200, V=200, R=727.3; ENDF/B-VIII.0; `openmc-vr`)

Each run uses **100 000 particles, 150 batches, 50 inactive** (a standard error of about 30 pcm per run, about 5 minutes each); the same seed (1) throughout; 9 runs in total.

| Label | Fuel composition | Fuel temperature option |
|---|---|---|
| A0 | default (H/Zr 1.60) | none (the reference treatment) |
| A294, A330, A372, A400 | default | `--tfuel 294`, `330`, `372`, `400` |
| B294, B330, B372, B400 | the 1994 fuel (`--fuel1994`, H/Zr 1.65) | `--tfuel 294`, `330`, `372`, `400` |

372 K is the average fuel temperature of step 7 of the power ascension (98.7 °C), the end of the reliable range. The water is at its default 294 K in every run, as in the library's own fuel temperature cases.

## Quantities

- `ρ = (k − 1)/k` in pcm, with the standard error of each run; differences carry the root sum of squares.
- **Fuel slope** from 294 K to T: `s_X(T) = (ρ_X(T) − ρ_X(294)) / (T − 294)` in pcm/K, for X = A or B (the 294 K run of the same composition is the base).
- **Method offset:** `Δ_method = ρ(A294) − ρ(A0)`.
- **Tables for the what-if comparison:** for each composition, a fuel temperature table with the knots 294 (0 pcm), 330, 372 and 400 K from the runs, and the library's own 500, 600 and 800 K values beyond; reactivity loss at the steps of Table IX computed exactly as metric A' of the sixth protocol (TB with γ_B, linear water warming; the A-ring and the other two water profiles as sensitivities), with the library's coolant table. This is a **what-if**, not a library change.

## Metrics and bands (fixed now)

| # | Quantity | Reading |
|---|---|---|
| **D1** | `Δ_method` against its standard error `σ_Δ` | **no artefact** if `|Δ_method| ≤ 2σ_Δ`; **artefact** otherwise (sign and size reported) |
| **D2** | linearity of the first interval for the default composition: `s_A(372) / s_A(400)` | **linear** 0.85–1.15; **convex** below 0.85 (the slope grows with temperature); **concave** above 1.15; also `s_A(330)/s_A(400)` |
| **D3** | composition: `s_B(372) / s_A(372)` and `s_B(400) / s_A(400)` | **no effect** 0.9–1.1; **stronger** above 1.1; **weaker** below 0.9; the standard error of each ratio is reported |
| **D4** | the what-if reactivity loss at steps 1–7 against Table IX for A and for B, labelled with the bands of metric A' (good ≤ max(10 %, 10 pcm); plausible ≤ max(25 %, 25 pcm)); worst and best over the sensitivities, primary line separately | |
| **D5** | reported only: all nine reactivities, `k` and standard errors; the library's own table knots against the runs at 400 K (the statistical consistency of the sweep) | |

## Decision process

1. **D1 artefact:** the library's fuel table carries an offset of that size and sign (and the coolant table, run in the same mode as the reference, does not); record it. A corrected table is a library change and needs its own protocol; nothing is corrected here.
2. **D2 convex or concave:** the straight line between 294 and 400 K misrepresents the interior; a knot between them is needed (a library change, own protocol). Whether the 400 K knot itself is right is read from D5.
3. **D3 stronger and D4 (B) good or plausible while D4 (A) fails:** the fuel hydrogen content is a lever strong enough to explain the shortfall. It is **not adopted**: the fresh fuel's real hydrogen content is not established by these data, and tuning it to the power ascension would be a fit; the library notes would state it as an unresolved uncertainty with the sensitivity.
4. **D4 (A) good or plausible with the new knots:** the shortfall came from the table's resolution or statistics, not the physics.
5. **None of D1 to D3 explains D4 (A) and (B) both fail:** record it; what remains is the temperature conversion of the measurement (γ), the water warming, or the fuel's temperature treatment in OpenMC that is not tested here.
6. **In every case** nothing in the library changes and its status stays `experimental`.
7. **Not tried after seeing the results:** other temperatures, other hydrogen contents or particle counts than those listed, other water temperatures, any fit.

## Implementation (to be written after this protocol)

The nine runs by `python -B -m pipeline.openmc.core_model --core 134 --rods T=0,K=200,V=200,R=727.3 --particles 100000 --batches 150 --inactive 50 [--tfuel T] [--fuel1994] --json pipeline/openmc/results/core134_feedback.jsonl`; `validation/m7_core134_feedback.py` reading that file, the library and Table IX (reusing `m7_fuel_coefficient`), with a synthetic test (planted reactivities); report `validation/m7_core134_feedback_report.json`; results note `docs/validation/m7-core134-feedback-results.md`. The runs and the script are done once.

## Limits, repeated

One OpenMC model of one core; the standard error of each reactivity is about 30 pcm, so a slope over 78 K carries about ±0.6 pcm/K; the measured loss carries the stated ±5 pcm per step, ±5 % in total, and a γ uncertainty of ±5 % each; the comparison uses the measurement's own temperature conversion and an assumed water warming; a "what-if" table is a diagnostic, not a library.
