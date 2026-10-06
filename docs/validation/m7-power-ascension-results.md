# M7 steady power ascension: results (2026-10-06)

Protocol: `m7-power-ascension-protocol.md`, written before this run. Script: `validation/m7_power_ascension.py` (run once, `python -m validation.m7_power_ascension`). Full output: `validation/m7_power_ascension_report.json`. Data: `validation/data/jsi-steady-power/`. Every metric is reported, failures included. Nothing was refitted after seeing the results.

## Result in one paragraph

**The shipped OpenMC libraries disagree with the measured JSI power ascension.** At 250 kW the model's power defect (the reactivity the regulating rod must add to hold power) is **about 650–680 pcm against 1427 pcm measured, a ratio of 0.45–0.47: metric A fails for both cores.** The shape of the feedback with power is plausible, not good. The model's fuel temperature rises linearly with power, and the measured rise is clearly concave, so metric C fails. Calibrating the one free parameter (`hA`) on the 250 kW state fixes the integral (A, by construction) but not the shape: C still fails and B stays plausible or worse. The regulating rod curve (D) agrees: good for core 242, plausible for core 246.

## Labels (worst over the protocol's sensitivities, best in brackets only where they differ)

| Core | Variant | A power defect | B feedback shape | C fuel-temperature shape | D rod curve |
|---|---|---|---|---|---|
| 242 | V0 as shipped | **fails** | plausible | **fails** | **good** (0.049, at the edge of 0.05) |
| 242 | V1 `hA` calibrated | good (by construction) | plausible | **fails** | |
| 246 | V0 as shipped | **fails** | plausible | **fails** | **plausible** (0.067) |
| 246 | V1 `hA` calibrated | good (by construction) | **fails** (best: plausible) | **fails** | |

Numbers behind the labels (ranges over the eight sensitivity combinations: start temperature 25.8 or 30.8 °C, `pCalculated` or `pIndicated`, pool constant or rising 6 K):

| | Core 242 | Core 246 |
|---|---|---|
| A, V0 ratio model / measured | 0.453–0.457 | 0.471–0.474 |
| B, V0 max difference | 0.058–0.064 | 0.059–0.065 |
| C, V0 max difference | 0.104–0.113 | 0.104–0.113 |
| V1 calibrated `hA` (shipped 3000 W/K) | 1452–1467 W/K | 1548–1559 W/K |
| B, V1 max difference | 0.085–0.092 | 0.092–0.101 (one combination above 0.10) |
| C, V1 max difference | 0.106–0.113 | 0.106–0.113 |
| Model mean fuel rise at 250 kW: V0 / V1 | 83–87 K / 171–175 K | 83–87 K / 160–165 K |
| D, normalised rod curve | 0.049 | 0.067 |

Reported, not banded: the measured fuel temperature rise at 250 kW is 200.9 K (a hot-element centre value); the library's regulating rod total worth is 2427 pcm (core 242) and 2460 pcm (core 246) against 3292.5 pcm in the core-200 table (a different core).

The two start temperatures and the two power axes move each metric by under 0.01. The pool's heating (constant against rising 6 K) moves them by about 0.005. **The labels are not sensitive to the choices the protocol left open**, except core 246 V1 metric B (plausible to fails, 0.099 against 0.101).

## The states (core 242, V0, pool constant, `pCalculated`)

| State | Power kW | Model defect pcm | Measured pcm | Model / measured | Feedback fraction model / measured | Fuel rise fraction model / measured |
|---|---|---|---|---|---|---|
| 2 | 2.9 | 7.3 | 20.6 | 0.35 | 0.011 / 0.014 | 0.011 / 0.043 |
| 3 | 43.6 | 112.5 | 316.4 | 0.36 | 0.174 / 0.222 | 0.174 / 0.272 |
| 4 | 100.3 | 259.1 | 656.4 | 0.39 | 0.401 / 0.460 | 0.401 / 0.509 |
| 5 | 188.9 | 488.2 | 1148.4 | 0.43 | 0.756 / 0.805 | 0.756 / 0.842 |
| 6 | 223.0 | 576.4 | 1315.3 | 0.44 | 0.892 / 0.922 | 0.892 / 0.932 |
| 7 | 250.0 | 646.2 | 1426.8 | 0.45 | 1.000 / 1.000 | 1.000 / 1.000 |
| 8 (down) | 191.1 | 493.9 | 1140.7 | 0.43 | | |
| 9 (down) | 103.7 | 267.9 | 648.7 | 0.41 | | |
| 10 (down) | 47.5 | 122.6 | 308.7 | 0.40 | | |
| 11 (down) | 0.3 | 0.5 | −8.8 | | | |

Core 246's A ratios are within 0.02 of core 242's (it was not tabulated state by state). The model is linear in power by construction (`T_fuel = T_pool + P/hA`, constant `hA`); the measured fuel temperature and power defect are not.

## Reading (interpretation, separate from the protocol's labels)

1. **The missing power defect is mostly a heat-transfer problem, not a coefficient problem.** The model's fuel temperature coefficient is about −7.8 pcm/K at 300–350 K (−8.4 at 400 K). The measured defect divided by the measured hot-element rise is 1427 / 201 = 7.1 pcm/K, the same size. What differs is the temperature rise: the model has 83 K (mean fuel, `hA` = 3000 W/K, assumed) against 201 K measured at the hot element. If the hot element runs 1.5 to 2 times hotter than the core mean (a guess; the model has no such number), the real mean rise is 100–135 K, and the model's coefficient (−7.8 to −9 pcm/K) over that rise gives about 780–1200 pcm, 0.55–0.85 of the measured value. These are hand estimates, not model runs; they say the shortfall does not go away with any plausible peaking factor.
2. **The shape is the second problem, and `hA` cannot fix it.** The measured fuel temperature at 43.6 kW is 27 % of its 250 kW rise; a constant `hA` gives 17 %. The measured rise per kW falls from about 1.3 K/kW at 42 kW to 0.8 K/kW at 250 kW, which looks like heat transfer that improves with temperature (natural convection) or a pool that heats during the exercise. The protocol's pool bracket (constant, or 6 K rising) does not close it. V1 recovers the integral by halving `hA`, and leaves C failing.
3. **At the lesson's powers the error is larger in relative terms.** The envelope ends at 15 % of the setpoint (41 kW). Between 3 and 44 kW the model's defect is 0.35–0.36 of the measured one, against 0.45 at 250 kW. A student holding 40 kW in the model would see the regulating rod withdrawn about a third as far, in reactivity, as at the real reactor.
4. **The rod curve is fine.** The shape of the regulating rod's integral worth (D) matches the measured core-200 table to 0.05–0.07 of the total. The total worth is 25 % lower in the model (2427 against 3292 pcm), and that is a different core.
5. **My pre-run estimate held.** I wrote down that metric A would come out low from "83 K × −8 to −14 pcm/K". It is 646–652 pcm (core 242), just below the bottom of that range because the coefficient at low temperature is −7.8 pcm/K.

## Limits of this result

- One exercise, "typical real data", one instrumented element, no stated uncertainties, an unknown core (A.1 is core 200; ours are 242 and 246), pool temperature inferred. Items 1–3 above are the reading of these numbers; the labels are the protocol's.
- The comparison uses the lumped model's mean fuel temperature against a hot-element centre value. Only the shape (C) is meaningful across that gap, and the shortfall in A is large enough (a factor of two) that it survives any plausible peaking factor.
- It tests the library's thermal and feedback chain at steady power, not the transient behaviour or the period during an ascension.

## What follows (protocol, section 3)

- **A fails:** the lesson's validity banner now carries a specific known limit from this result (`web/src/app/scenarios/triga-242-openmc-low-power-ascension.json`, `envelope.knownLimits`), and `supported-envelope.md` says so.
- **The library status stays `experimental`.** This data cannot earn `validated-for-domain` (no matched core, no uncertainties), and the result would have prevented it anyway.
- **No refit.** Changing `hA` or making heat transfer depend on temperature is a new, dated protocol. Candidates, in order of effort:
  1. Make `hA` depend on the fuel-to-pool temperature difference, calibrated on some states and held out on the others. **Done 2026-10-06 as a second protocol: `m7-heat-transfer-protocol.md` and `m7-heat-transfer-results.md` (a power law with n = 0.22–0.27 meets the adoption rule for both cores).**
  2. Add a hot-element temperature (peaking factor from the shape arrays) so the absolute temperature can be compared.
  3. Find a measurement for core 242 or 246 with uncertainties (the 1994 steady-state benchmark, Mele, Ravnik and Trkov), and set the bands from its uncertainty.
