# M7 heat transfer law: comparison protocol (second protocol, written before any run of it, 2026-10-06)

This follows `m7-power-ascension-protocol.md` and its results (`m7-power-ascension-results.md`), where the shipped libraries failed on the power defect (metric A) and on the shape of the fuel temperature with power (metric C). The results note named the remedy this protocol tests: a heat transfer that depends on temperature. Nothing here has been run. It is a new dated protocol because the first one forbids refitting after results.

## Disclosure: what was seen before writing

This protocol is **not blind** to the data. Seen:

- all of the measured data, and the first run's full output: the shipped model is linear in power; the measured fuel temperature rise is concave (27 % of its 250 kW rise at 43.6 kW against 17 % for a constant `hA`); the calibrated constant `hA` was 1450–1560 W/K; with it the shape metrics B and C still failed (B 0.085–0.101, C 0.106–0.113);
- that the model's fuel coefficient is about −7.8 pcm/K at 300–350 K and that the measured defect per hot-element kelvin is 7.1 pcm/K.

Because of that, the choices below are limited in advance: **one model family, two free parameters, a fixed calibration/hold-out split, fixed bands, and no other family tried after the results are seen.** The held-out states and the independence between the reactivity data and the temperature data are what keep the test meaningful.

## The question

Can a physically motivated heat transfer law with two parameters, fitted to the measured *reactivity* at two states, predict (a) the measured reactivity at the other states and (b) the measured *temperature shape* with power, which it was not fitted to?

## The law

Constant `hA` (shipped, **L0**) against a power-law dependence on the fuel-to-pool temperature difference ΔT (**L1**):

    hA(ΔT) = h0 · (ΔT / 100 K)^n          Q = hA(ΔT) · ΔT = P        (the fuel deposits all power: `fuelFraction` = 1)

so ΔT = (P · (100 K)^n / h0)^(1/(1+n)), in closed form. n = 0 is the shipped law; natural convection from a heated surface has n of about 0.25 (laminar) to 0.33 (turbulent). Free parameters: h0 and n. The fuel and pool feedback tables, the fuel mass and everything else stay as shipped. Pool temperature, start temperature and power axis are handled as in the first protocol (two pool cases, two T0, two power axes).

The model computes a **mean** fuel temperature. The measured one is a hot-element centre value, so the temperature *shape* θ(P) is compared (the scale cancels), exactly as in metric C of the first protocol.

## Calibration and hold-out (fixed)

| Role | States (1-based; `pCalculated`) | Why |
|---|---|---|
| **Calibration** | 3 (43.6 kW) and 7 (250 kW) | state 3 sits at the lesson's upper edge (15 % of the setpoint is 41 kW); state 7 is the top of the range. State 2 (20.6 pcm) is too small to fit: the rod moves in steps of 5–7 pcm, so each reading carries about ±3 pcm |
| **Held out, interpolation** | 4, 5, 6 (100.3, 188.9, 223.0 kW) | |
| **Held out, extrapolation** | 2 (2.93 kW) | the lesson's low-power end; reported separately |
| **Held out, return leg** | 8, 9, 10 (191.1, 103.7, 47.5 kW) | the pool is warmer and the rod was moved the other way: a hysteresis check, reported separately and not part of the pass rule |

The two calibration conditions are the model's power defect equal to the measured one at states 3 and 7 (316.4 pcm and 1426.8 pcm). h0 and n are solved numerically for each combination of sensitivities.

## Metrics and bands (fixed now)

| # | Quantity | Bands |
|---|---|---|
| **A2** | Defect at each held-out interpolation state: error = \|model − measured\| against the larger of 10 % of the measured value and 8 pcm (about one rod step) | **good**: every held-out state within the 10 % / 8 pcm tolerance; **plausible**: within 25 % / 20 pcm; **fails** beyond |
| **C2** | Temperature shape θ(P) = (T(P) − T(0.09 kW)) / (T(250 kW) − T(0.09 kW)) at the held-out interpolation states; max absolute difference from the measured θ | **good** ≤ 0.05, **plausible** ≤ 0.10, **fails** above (the first protocol's bands) |
| **X** | Extrapolation to state 2 (2.93 kW): A2's rule and C2's rule applied to that state alone | reported with its own label |
| **N** | The fitted exponent n | physical if 0 ≤ n ≤ 0.5. Outside, the fit is flagged non-physical whatever its other labels |
| **E** | Peaking factor f = measured rise at 250 kW (200.9 K) / model mean rise at 250 kW | reported only; interpreted later against the shape arrays' B-ring power share (separate piece of work) |

The labels are the worst over the eight sensitivity combinations and both cores, with the best shown beside them. The return-leg states get A2 and C2 labels for information only.

## Baseline for the comparison

**L0 is refitted on the same two states** (constant `hA` calibrated to state 3 and state 7: two conditions, one parameter, solved by least squares on the relative errors) and scored with the same A2 and C2. L1 counts as **an improvement** only if its worst-case C2 difference is at most half of L0's and its A2 label is no worse. Otherwise the result is "no better than a constant `hA` on these data".

## Decision rule (before the results)

- **Adopt as a candidate** (propose a library-format change, a separate task with golden vectors in both engines) only if, for both cores: A2 and C2 are good or plausible in the worst case over the sensitivities, X does not fail, N is physical, and L1 is an improvement over L0.
- **Otherwise record the result and stop.** The likely readings are a different loss of linearity (for example the pool, or boiling at the clad), too noisy data, or a coefficient problem; none of them is a licence to add a third parameter here.
- **In every case** the library status stays `experimental`: this data has no stated uncertainty and no stated core.
- **Not tried after seeing the results:** other families (two-term laws, a pool model, a different heat sink), a three-parameter law, a different split. Each would be a new dated protocol.

## Implementation (to be written after this protocol)

`validation/m7_heat_transfer.py`, reusing the loaders and data of `validation/m7_power_ascension.py`; a synthetic-library regression test (closed form for ΔT, calibration recovers known h0 and n, the n = 0 case reproduces the first script's arithmetic); report `validation/m7_heat_transfer_report.json`; results note `docs/validation/m7-heat-transfer-results.md`. The script is run once.

## Limits, repeated

One exercise of student "typical real data"; one instrumented element; the core is not stated; the pool temperature is inferred; calibration points carry a rod-step resolution of about ±3 pcm each; the lumped model has one fuel temperature. A good fit would show that a two-parameter law is *consistent* with this one data set, not that the heat transfer is understood.
