# M7 fuel temperature feedback and heat transfer on core 134: results (2026-10-06)

Protocol: `m7-fuel-coefficient-protocol.md` (fifth protocol, amended before the run; not blind, see its disclosure). Script: `validation/m7_fuel_coefficient.py`, run once (`python -m validation.m7_fuel_coefficient`). Full output: `validation/m7_fuel_coefficient_report.json`. Data: `validation/data/jsi-core134/power_steps.json` (Table IX of the 1994 benchmark paper). Every metric is reported. Nothing was changed after seeing the results except the script's printing (see the note at the end); the numbers are those the one run wrote.

## Result in one paragraph

**The library's fuel temperature feedback reproduces the measured reactivity loss of core 134 within the benchmark's stated scale (A: "plausible" for both cores, "good" up to 80 °C average fuel temperature, 9–14 % too small at 99 °C). The library's heat transfer law does not transfer: scaled to core 134's 48 fuel positions it predicts a mean fuel rise 20 % too high at 45 kW and 70 % too high at 236 kW (E fails), and the measured rise grows with power as P^0.6, not P^0.8 (a fitted exponent of 0.64 against the library's 0.22 and 0.23; D fails).** The protocol's decision is "the law is specific to the earlier exercise: add a known limit". The 2002 fuel coefficient agrees (C: good) and the 2002 isothermal coefficient depends on which interval of the library's coarse tables is used (B: fails on the first interval, good on a wider one). Nothing fitted changes; the libraries stay `experimental`.

## Labels (primary line; worst and best over the sensitivities beside it)

| Core | A feedback (steps 1–7) | B isothermal (+3.5 ± 0.3) | C fuel per B-ring K (−4.8 ± 0.5) | D exponent | E rise ratio, model / measured, steps 4–14 |
|---|---|---|---|---|---|
| 242 | **plausible** (worst plausible, best good) | **fails**, diff 4.98 (first interval); good, diff 0.02, on the wide interval | **good**, −5.09 (worst plausible) | **fails**: n134 0.642 (range 0.61–0.70) against 0.217 | **fails** 1.20–1.71 (all combinations 1.13–1.72, "high") |
| 246 | **plausible** (best good) | **fails**, diff 2.18; good, diff 0.30, on the wide interval | **good**, −5.32 (worst plausible) | **fails**: n134 0.642 against 0.233 | **fails** 1.24–1.73 (1.15–1.74) |

## A: reactivity loss from the library's tables at the measured mean fuel temperatures (primary: TB, γ_B 1.525, linear water warming)

| Step | Mean fuel °C | Core 242 model / measured (pcm) | Core 246 model / measured | Label (242 / 246) |
|---|---|---|---|---|
| 1 | 29.5 | 57.5 / 49.6 | 58.5 / 49.6 | good / good |
| 2 | 38.9 | 127.1 / 118.9 | 129.8 / 118.9 | good / good |
| 3 | 51.5 | 221.2 / 217.6 | 226.6 / 217.6 | good / good |
| 4 | 66.8 | 336.1 / 344.8 | 345.2 / 344.8 | good / good |
| 5 | 78.6 | 424.1 / 460.6 | 435.7 / 460.6 | good / good |
| 6 | 89.3 | 503.4 / 563.6 | 517.1 / 563.6 | plausible / good |
| 7 | 98.7 | 573.1 / 666.0 | 588.3 / 666.0 | plausible / plausible |

- With the A-ring thermocouple (γ_A 1.575) core 242 is "good" in every water profile and core 246 "good" in one; the temperature uncertainty (±1 to ±4 °C, γ ±5 % each) is larger than the difference between the two thermocouples.
- Information only, above the paper's reliable range: the cumulative loss at step 13 is **942 pcm (242) and 976 pcm (246) against 1276 pcm measured**, 26 % and 24 % low. The library's slope is about −7.8 pcm/K up to 400 K and steeper above, and the measured loss grows faster.

## B and C: the 2002 coefficients

- Library slopes from the first tabulated interval (294–400 K fuel, 294–313 K coolant): fuel −7.76 and −8.12 pcm/K; coolant +6.27 and +9.44 pcm/K; **isothermal −1.48 (242) and +1.32 (246)**, against the measured +3.5. On the wider interval (500 K fuel, 333 K coolant): fuel −8.38 / −9.05, coolant +11.9 / +12.8, isothermal +3.48 / +3.80: **good**. The coolant table is strongly non-linear (its slope doubles between the two intervals), and the experiment (15–25 °C) lies below the table's first point, so the result is a statement about the table's resolution, not a measurement of the model's isothermal coefficient at room temperature.
- Fuel coefficient per B-ring kelvin: −5.09 / −5.32 with the paper's γ_B (good); −6.08 / −5.97 with the hot-element chain's conversion (r_B 1.28 and 1.36; plausible).

## D and E: the heat transfer law on core 134

- **n134 = 0.61–0.70 in every combination** (0.642 on the primary line), from the rise of the volume-averaged fuel temperature over the warming water, steps 4–13 (45–236 kW). The exponent estimated by hand on the whole range (5–250 kW, no water correction) was 0.37–0.43; over 45–236 kW the data are nearer to linear in power, which is the same physics as the constant `hA` law the first protocol rejected for the other exercise.
- **The model's mean fuel rise is too high at every step, by 20 % at 45 kW rising to 70 % at 236 kW**, with `h0` scaled by 48 / N_lib. The scaling (the same per-element cooling in both cores) is an assumption; the 47.6-position sensitivity does not change the label.
- Both libraries give the same D and E to within a few per cent, as expected (the same law, the same scaling).

## Reading (interpretation, separate from the protocol's labels)

1. **The two exercises disagree about the mean fuel temperature rise at 250 kW.** The fuel thermocouple (B ring) rises about 200 K above the start in both: core 134's TB reads 222 °C from 21.6 °C, and the IAEA/JSI exercise's 201 K. The benchmark paper converts that to a mean rise of 131 K by γ_B = 1.525; the earlier protocols used a thermocouple-to-mean ratio of 1.15–1.4 and so a mean rise of 145–172 K. With the paper's conversion the mean rise at 250 kW is about 25 % lower than the one the library's law was fitted to. The same direction as the second hot-element protocol (R_α 1.23–1.25) and as A (the feedback table is 10–14 % weak at 100 °C): a smaller true mean rise together with a slightly stronger fuel coefficient gives the same measured defect. This is a consistent reading, not a derived result.
2. **The law was a good description of one exercise (state 3 to 7 held out within 4 %, shape within 0.03–0.05), not a law of the reactor.** It matched the other exercise's temperature shape with an exponent of 0.22–0.27; this one wants 0.6 over 45–236 kW. The cooling was on in the first and off in this one, the cores have different sizes and the pool warmed by an unknown profile; any of these, or the conversion above, can account for it. The measurement of this paper has no cooling, so this is a different regime and a fair test of whether the law has the exponent of natural convection or only the shape of one data set.
3. **The lesson stays below 40 kW**, below the 45 kW where E starts, and A is "good" at the corresponding steps (1–3, up to 27 kW). The known limit added to the banner states what was and was not checked.

## Decision (protocol)

- **A (plausible):** the fuel temperature table gives the measured reactivity loss within the stated scale; the fuel coefficient is not the likely reason for the earlier power-defect disagreement, but it is 10–14 % weak near 100 °C. Burnup (the library is 23.7 MWd/kg, core 134 is fresh) is the first candidate for the difference; not tried here.
- **D and E (both fail):** the law is specific to the earlier exercise. A known limit is added to the lesson banner (done with this note). The source string of the libraries keeps "fitted to one exercise on an unstated core". Nothing is refitted.
- **B (fails on the primary interval) and C (good):** record: the water temperature coefficient cannot be resolved by the table at 288–298 K, and the fuel coefficient agrees.
- **Nothing fitted changed**; the libraries stay `experimental`.
- **Not tried after seeing the results (per the protocol):** other slope intervals, conversions, water profiles or step ranges, a fit of any library number to this data, a fresh-fuel correction.

## Note on the run

The script wrote its report and then failed in `print_summary`, which looked up a key (`n134`) under the wrong dictionary. The numbers above are the ones in the report from that single run; the printing was fixed afterwards and the summary re-read from the report file, with no recomputation.

## Limits, repeated

Core 134 is fresh, 45 elements, cooling off, pool warming of about 8 °C with no times; cores 242 and 246 are burned and mixed with cooling on in the other exercise; the library tables resolve nothing between 294 and 400 K; the temperature conversion γ and the water profile are assumptions; the heat transfer scaling by fuel positions is an assumption. "Fails" in D and E means this law with this scaling does not describe this experiment, not that either experiment is wrong.
