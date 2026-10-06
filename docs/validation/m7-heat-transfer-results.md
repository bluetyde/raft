# M7 heat transfer law: results (2026-10-06)

Protocol: `m7-heat-transfer-protocol.md` (second protocol; not blind, see its disclosure). Script: `validation/m7_heat_transfer.py`, run once (`python -m validation.m7_heat_transfer`). Full output: `validation/m7_heat_transfer_report.json`. Data: `validation/data/jsi-steady-power/`. Every metric is reported. Nothing was changed after seeing the results.

## Result in one paragraph

**The protocol's adoption rule is met for both cores.** A heat transfer that depends on the fuel-to-pool temperature difference, `hA = h0 (ΔT / 100 K)^n`, fitted to the reactivity at two states (43.6 and 250 kW), **predicts the held-out reactivity to within 4 %** at 100, 189 and 223 kW and **the shape of the fuel temperature rise, which it was not fitted to, to 0.03–0.05** (the shipped constant `hA` is off by 0.11). The fitted exponent comes out at **n = 0.22–0.27 without being pushed there**, the value of natural convection. It does not touch the library status, which stays `experimental`.

## Labels (worst over the eight sensitivity combinations; best in brackets where different)

| Core | Law | A2 held-out defect | C2 temperature shape (max difference) | X: state 2 (2.9 kW) | N: exponent | E: peaking factor |
|---|---|---|---|---|---|---|
| 242 | L0 constant `hA`, refitted | plausible (best good) | **fails** (0.106–0.113) | good / good | | 1.03–1.05 |
| 242 | **L1 power law** | **good** | **plausible** (0.034–0.051; 6 of 8 good) | plausible (defect) / good (shape) | 0.217–0.248, physical | 1.15–1.17 |
| 246 | L0 constant `hA`, refitted | plausible | **fails** (0.106–0.113) | good / good | | 1.09–1.12 |
| 246 | **L1 power law** | **good** | **good** (0.031–0.048) | plausible (defect) / good (shape) | 0.233–0.272, physical | 1.22–1.25 |

- **Improvement over the baseline:** L1's worst temperature-shape difference (0.051, 0.048) is under half of L0's (0.113), and its defect label is no worse. Both cores.
- **Sensitivities:** the start temperature (25.8 or 30.8 °C), the power axis and the pool case move the fitted n by up to 0.04 and the shape difference by up to 0.02. The only label that changes is core 242's temperature shape (0.0507 against the 0.05 edge in two combinations, good otherwise).
- **Fitted values:** h0 (the heat transfer coefficient at ΔT = 100 K) is 1269–1302 W/K for core 242 and 1362–1389 W/K for core 246, against 3000 W/K shipped.

## The held-out states (core 242, first combination; every combination is in the report)

| State | Power kW | L1 defect pcm | L0 defect pcm | Measured pcm | L1 error |
|---|---|---|---|---|---|
| 4 | 100.3 | 629.4 | 595.8 | 656.4 | −4.1 % |
| 5 | 188.9 | 1106.2 | 1178.7 | 1148.4 | −3.7 % |
| 6 | 223.0 | 1287.1 | 1415.0 | 1315.3 | −2.1 % |
| 2 (extrapolation) | 2.93 | 32.6 | | 20.6 | +12 pcm (about two rod steps; "plausible") |

Core 246 is close: 623.8, 1096.9, 1283.2 pcm. Return leg (states 8–10, information only): L1 defect labels good, good and plausible or good, temperature-shape differences 0.043–0.054; L0's are 0.083–0.124.

## Reading (interpretation, separate from the protocol's labels)

1. **The first protocol's two failures had one cause.** The library's constant `hA` (3000 W/K, assumed) is wrong in two ways: too large, and constant. The first run's calibrated constant `hA` (1450–1560 W/K) fixed the integral and not the shape. A power law fixes both with two numbers, and the exponent lands where convective heat transfer from a heated surface in water would put it. That is the strongest part of the result: the solver could choose any exponent from −0.9 to 3.0, and only afterwards did the protocol check whether it fell in 0 ≤ n ≤ 0.5; it was not tuned.
2. **What the fit does not show.** Two parameters fitted to two points will follow any smooth curve; four held-out states agreeing to 4 % says the *family* is right for these data, not that the physics is understood. The independent check is the temperature shape (not in the fit) and the exponent.
3. **The peaking factor is low.** To match the measured hot-element rise (201 K) at 250 kW the model's *mean* fuel rise needs to be about 172 K (core 242) or 160–165 K (core 246), so the hot element is only 1.15–1.25 times the mean. I would expect more from an element at maximum power density (a centre-to-mean ratio of about 1.3–1.5 for a solid cylinder, times the power peaking of the B ring); this is a hand estimate, not read from the shape arrays. If the factor is really 1.4–2, the model's mean rise is too large for the measured defect, and the library's fuel temperature coefficient would have to be larger than the −7.8 pcm/K it has at low temperature. This is the open question for the next piece of work (E is reported, not banded).
4. **At 2.9 kW the model overshoots the measured defect** (33–37 against 20.6 pcm), still inside the protocol's band. The measurement there is a 3-step rod move and carries about ±3 pcm per reading, so the difference (12–16 pcm) is more than rounding but not much more. It is the lesson's low-power end, so it is the place to look first if the law is adopted.
5. **Relevance to the lesson.** With L1 the model's power defect at 43.6 kW is the measured one by construction, and at 100–223 kW within 4 %. The 0.35 ratio found at the lesson's powers in the first run came from the wrong `hA`; with this law it becomes exact at 43.6 kW (a calibration point) and an overshoot of 12–16 pcm at 2.9 kW.

## Decision (protocol)

- **Adopt as a candidate**: propose the library-format change. It is a separate task (the engine, both implementations, the format and golden vectors), not part of this note. The shape of the change, to be designed in that task:
  - `thermal.hA` becomes either the current scalar or `{ "h0": W/K, "n": exponent, "dTRef": 100 K }`, with the fuel-to-pool heat flow `q = h0 · sign(ΔT) · |ΔT / dTRef|^n · |ΔT|` in the thermal equations (both engines);
  - the format document, the validators (Python and TS), the exporter and the two OpenMC libraries change; golden vectors need new cases for n ≠ 0 and ΔT < 0; the engine version changes so the UI can detect it;
  - the shipped values would come from this fit, with its source stated as "fitted to the IAEA/JSI power ascension (one exercise, unknown core)", status `experimental`.
- **The library stays `experimental`.** One exercise of student "typical real data", no stated core, no stated uncertainty. A matched measurement with uncertainties is still needed (the 1994 JSI steady-state benchmark, Mele, Ravnik and Trkov).
- **The lesson's banner keeps its known limit** (the power defect disagreement) until the library actually changes. When it does, the limit is replaced by a statement of what the law was fitted to and where it was checked.
- **Not done, per the protocol:** no other family, no third parameter, no change of split. The hot-element temperature (point 3) is a separate protocol.

## Limits, repeated

One exercise; one instrumented element; unknown core; no uncertainties; inferred pool temperature; calibration points carry about ±3 pcm each; the fit has two parameters and two calibration states, so the held-out agreement is evidence for the family, not an accuracy claim.
