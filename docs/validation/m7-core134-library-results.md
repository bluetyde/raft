# M7 core 134 library: results (2026-10-06)

Protocol: `m7-core134-library-protocol.md` (sixth protocol; not blind, see its disclosure). Script: `validation/m7_core134_library.py`, run once (`python -m validation.m7_core134_library`). Full output: `validation/m7_core134_library_report.json`. Library: `libraries/triga-jsi-134-openmc` (fresh fuel, 41 OpenMC cases, `experimental`). Data: `validation/data/jsi-core134/`. Every metric is reported. Nothing was changed after seeing the results.

## Result in one paragraph

**The library reproduces the regulating rod, the one rod that moves in the power ascension: total worth 2460 pcm against 2550 measured (ratio 0.965), curve shape within 0.041 of the measured one, and 15 pcm from the measured worth at the critical position (all "good"). It does not reproduce the measured reactivity loss with fuel temperature: the fresh-fuel feedback table is 17 % low at the first step and 36 % low at 99 °C average fuel temperature (A' fails; the burned libraries of cores 242 and 246 were 9–14 % low on the same data).** The decision is therefore: the regulating rod curve is usable, the fuel feedback fails, and no power ascension comparison is written yet. Nothing in the library changes; it stays `experimental`.

## Rod worth curves (R1–R3; model with the other rods at the library's reference state)

| Rod | Model total (pcm) | Measured total (pcm) | R1 ratio | R2 shape difference | R3 at 28.7 cm |
|---|---|---|---|---|---|
| **regulating** | 2460 | 2550 (the 38 cm row) | **0.965 good** | **0.041 good** | **+15 pcm good** (model 2170, measured 2155) |
| shim | 3177 | 2430 | 1.307 **fails** | 0.035 good | |
| safety | 3841 | 3440 | 1.116 plausible | 0.117 **fails** | |
| transient | 2756 | 2270 | 1.214 plausible | 0.099 plausible | |

- The regulating rod is the one the decision uses, and its three labels are good. The model's curve is 3.5 % lower in total than the measured one, inside the stated calibration error (< 10 %).
- The shim rod's total is 31 % high, the safety rod's 12 % high with a curve shape off by 0.117, and the transient rod's 21 % high. These rods do not move in the power ascension, so the decision rule says to record them and change nothing. A cause the protocol names: the library's tables hold the other rods at the reference state, and the measurement used the regulating rod's compensation; the model's rod worths with the regulating rod inserted 28.7 cm differ from those of the exchange measurement. The size of the shim difference is larger than that alone would suggest and is not explained here.

## A': reactivity loss of the library's tables at the measured mean fuel temperatures (primary line: TB, γ_B 1.525, linear water warming)

| Step | Mean fuel °C | Model (pcm) | Measured (pcm) | Label |
|---|---|---|---|---|
| 1 | 29.5 | 41.1 | 49.6 | good |
| 2 | 38.9 | 91.9 | 118.9 | plausible |
| 3 | 51.5 | 162.2 | 217.6 | **fails** |
| 4 | 66.8 | 249.3 | 344.8 | **fails** |
| 5 | 78.6 | 314.7 | 460.6 | **fails** |
| 6 | 89.3 | 373.3 | 563.6 | **fails** |
| 7 | 98.7 | 424.1 | 666.0 | **fails** |

Primary label **fails**; worst over the sensitivities fails, best plausible (A-ring thermocouple).

- The table's fuel slope over 294–400 K is −6.2 pcm/K (the table has −657 pcm at 400 K, a knot above the measured range). The measurement already reaches 666 pcm at an average fuel temperature of 372 K, so it needs a mean slope of about −8.6 pcm/K over 22–99 °C; the table gives −6.2 and is linear in that interval.
- The burned libraries of cores 242 and 246 give 573 and 588 pcm at the same step (the fifth protocol): 14 % and 12 % low, "plausible". So the **fresh-fuel table of this library is further from the measurement of the fresh core than the burned-fuel tables are**.
- Information (F), above the reliable range: the cumulative loss at step 13 is 722 pcm against 1276 measured; the coolant table slope over the first interval is +13.5 pcm/K.

## F: the library's heat transfer and offset

- The library has the base library's **constant `hA` = 3000 W/K (assumed, not fitted)**. The mean fuel rise it gives is 35–68 % of the measured one at 45–250 kW (ratio 0.35 at 45 kW to 0.68 at 250 kW): the model fuel is much too cold. This is not a test of the heat transfer law; the law is the thing a seventh protocol would fit.
- Calibration offset 323 pcm (the model is that much above critical at the measured critical rods; the library carries the offset so that the critical state is critical).

## Reading (interpretation, separate from the protocol's labels)

1. **The reactivity curve of the moving rod is right; the feedback is not.** Together with the power defect that is the whole of the power ascension: a feedback that gives only 64 % of the measured loss at 99 °C means that the same measured defect needs about 46 % more mean fuel temperature rise in the model (the eighth protocol's implied conversion at step 7 is 1.04 against 1.525: a mean rise of 113 K against 77 K, coolant term included), so comparing the power ascension on this library would reproduce the earlier exercises' tension between the heat transfer fit and the feedback strength rather than test the heat transfer.
2. **The suspects named in the protocol.** (a) The fuel hydrogen content: the gate found that the model moves about 200 pcm per 0.01 of H/Zr in reactivity; a stronger feedback with more hydrogen is physically reasonable (more moderation in the fuel, a larger thermal hardening), but the gate's round 2 with the benchmark's own H/Zr 1.65 was not extended to the feedback tables. (b) The temperature conversion: with γ_B larger than 1.525 the measured mean fuel temperature falls and the required slope grows, which makes the discrepancy worse, not better; with γ smaller the discrepancy shrinks. The paper gives γ ±5 % each. (c) The modelled temperature dependence of the fuel in OpenMC (which temperatures the nuclides and the ZrH scattering tables take), which gives the burned and the fresh libraries different slopes.
3. **What this changes in the plan.** The fresh library cannot yet carry a comparison of the power ascension. It does carry something useful: it shows that the feedback strength of the OpenMC fuel model is the open question, in fresh fuel as in burned, and that burned fuel (23.7 MWd/kg) happens to be nearer to the fresh core's measurement than fresh fuel is.

## Decision (protocol)

- **Regulating rod curve: supported.** The other three rods fail or are plausible in ways the power ascension does not use; recorded.
- **Feedback: fails.** Fuel hydrogen and the temperature conversion are the first suspects; **no seventh protocol yet.** The library is not changed (no fit) and stays `experimental`.
- **Not tried after seeing the results (per the protocol):** other rod position conversions, water profiles or step ranges, a compensation correction for the rod-exchange method, any fit of the library to this data.

## Limits, repeated

The rod tables are on a coarse grid (8 points for the regulating, shim and safety rods); the other rods are at the reference state in the model; the temperature conversion and the water warming are assumptions; the model carries a 323 pcm offset and an input uncertainty of about 500 pcm from the fuel composition; the fresh and burned libraries are different fuel states. A "fails" on A' means the table does not reproduce this measurement at the stated scale, not that the measurement is right to better than its ±25 %.
