# Supported lesson and operating envelope

Status: proposed 2026-10-06 (user choice: low-power ascension on TRIGA core 242). Nothing here is `validated-for-domain` yet; M7 (measured data) is what could earn that label.

## The lesson

**Low-power ascension and hold, from shutdown, on the OpenMC library `triga-jsi-242-openmc`** (scenario `triga-242-openmc-low-power-ascension`).

- Start: all rods in, the source in the core (`init.rods: shutdown`; the library's reference state is critical, which has no source equilibrium, so a start from the reference state is refused with `E_INIT_NO_EQUILIBRIUM`).
- Goals: pass 1 % and 10 % of the power-high setpoint, then hold 5–12 % for two minutes without a trip.
- Controls: rod motion and scram. No pulses.
- The other TRIGA scenarios run on the older M1 library `triga-jsi-242` and are not covered here.

## The envelope

Every limit comes from the library or has a source (`web/src/runtime/envelope.ts`, scenario field `envelope`).

| Limit | Value | Source |
|---|---|---|
| Power | at most 15 % of the `power-high` setpoint (41 kW) | the lesson's goals end at 12 %; 15 % leaves margin |
| Fuel temperature | at most 570 K | warmest joint-checked state, 569.8 K (`manifest.json` `domain.jointChecked`) |
| Mode | steady only | pulses are a different lesson (run 3 Part B, the pulse comparison, passes on these libraries per `m2-libraries.md`, but this lesson does not use it) |
| Data range | the library `domain` (fuel 294–800 K, coolant 294–333 K, xenon 0–4e20, rods 0–1) | where the OpenMC tables have data |

## What supports the lesson, and what does not

Evidence in the repository (not new claims):

- Critical state: the measured critical rod positions are critical in the library after a one-number calibration (`m2-core.md`, `m2-burnup-results.md`); the uniform-burnup model was calibrated on core 246 and tested on core 242 (−309 pcm).
- Rod worth: core 242's transient-rod curve is within 1 σ of the measured table; integral and differential curves exist for every rod (`m2-libraries.md`).
- Kinetics: β_eff 724 ± 25 pcm and Λ 45.5 µs at the calibrated burnup (`m2-core.md`).
- Feedback: fuel coefficient −8 to −14 pcm/K, coolant about +12 pcm/K (`m2-libraries.md`).
- Joint rod states: six holdout states per core. Core 242's errors are 450, 82, 79, 61, 153 and 69 pcm, consistent with the statistical noise of about 150–240 pcm (1 σ) except the first (about 2 σ). Core 246 has two states off by +590 and +914 pcm with several rods deep.

Not supported:

- **A first comparison with a measured steady power ascension disagrees** (`m7-power-ascension-results.md`, 2026-10-06): the model's power defect at 250 kW is 0.45–0.47 of the measured 1427 pcm (metric A fails for both OpenMC cores), 0.35–0.36 at the lesson's powers, because the lumped fuel heats too little and linearly with power. The regulating rod curve and the rod worth shape agree. The first comparison used the libraries as shipped then (constant `hA` 3000 W/K). Since 2026-10-06 the two OpenMC libraries carry a fitted power law `hA = h0 (ΔT / 100 K)^n` (n 0.217 and 0.233): it predicts the held-out defect within 4 % and the fuel temperature shape within 0.03–0.05, but overshoots the defect at the lesson's lowest measured state (33–37 against 20.6 pcm at 2.9 kW) and is fitted to one exercise on an unstated core (`m7-heat-transfer-results.md`, `m7-hot-element-2-results.md`). The lesson's banner states that as its known limit. A second comparison, with the 1994 JSI core 134 power ascension (`m7-fuel-coefficient-results.md`), found the fuel temperature table within the stated scale (A plausible, 9–14 % weak at 100 °C) but the heat transfer law 20–70 % too hot from 45 kW upward with a different exponent (0.64 against 0.22); that is a second known limit in the banner. The library status stays `experimental` and the state can be `caution` at best, never `ok`.
- Rod interaction: rod worths are added as if the rods acted alone. Only the six holdout states per core check that; every other combination of two or more moved rods is `R_JOINT_UNCHECKED`. A low-power ascension moves several rods, so this reason is normally present.
- **The plant setpoints.** The trips (`power-high` 275 kW, `fuel-temp-high` 873.15 K, `period-short` 3 s) and the interlocks have no source recorded in this repository; they are assumed generic TRIGA-like values, not JSI's (stated in the libraries' provenance notes since 2026-10-07). The period trip reads the true period without a lag, so a reactivity step trips it at once.
- Long runs (xenon), high power, pulses, and the second TRIGA core.

## The warnings a window shows

A banner at the top of the operator and instructor windows follows the runtime's `validity` message:

| Level | Meaning |
|---|---|
| `ok` | supported state, inside the envelope (not reachable until the library is validated) |
| `caution` | inside the envelope, but the model is not validated for this state; the banner lists why |
| `warning` | outside the data range, or outside the lesson's envelope (power, fuel temperature or mode); the banner names the limit |

The AI operator never works toward a power above the envelope: the raise ceiling is the lower of 50 % of the setpoint and the lesson's limit, and an instructor goal above it is clamped (the instructor panel says "limited to … by the lesson envelope").

## The PWR library (BEAVRS, hot zero power)

`pwr-beavrs-hzp-openmc` has two lessons (2026-10-10 and 2026-10-15); the second, **approach to criticality by bank withdrawal** (`pwr-beavrs-hzp-bank-withdrawal`, protocols 14 to 16 in `docs/validation/m8-near-critical-results.md`), starts with banks D and C in, the others out and 900 ppm of boron (about 850 pcm subcritical), and the operator withdraws bank C to its critical position (0.592 of travel in the library, 132.6 of 228 steps in the transport calculation it was checked against) and holds the log channel between 0.1 and 5 W for 5 minutes; only `rod.move` and `scram` are allowed. It claims only that state family (D and C in, every other bank at its benchmark position, boron near 900 ppm): the library's reactivity is within 100 pcm of transport at five of six checked positions of bank C (198 pcm at 40 steps; one case did not converge) and its critical position within 3 steps; the banner shows `unvalidated` for bank C positions between the checked ones. The first lesson is **approach to criticality by dilution** (`pwr-beavrs-hzp-dilution`, plan `docs/m8-dilution-lesson-plan.md`): shut down by 1100 ppm of boron with the rods at the benchmark configuration, the operator lowers the boron (0.1 ppm/s) until the reactor is critical, then holds the log channel between 0.3 and 30 W for 5 minutes with the boron near 983 ppm; only `boron.set` and `scram` are allowed, so the rods leave the reference only in a scram (then the banner warns). Its windows show the `caution` banner and the experimental status. What it claims: the critical concentration at this one rod configuration (the library gives 983 ppm, the benchmark measured 975 ppm). It does not claim the dilution rate, the trip setpoints or the starting power (assumed), nor anything about temperature feedback or power operation. At 100 times real time a human cannot react in time (tried 2026-10-10); 1 to 10 times is workable. The transport model reproduces the critical boron concentration at the five benchmark rod configurations and the shutdown banks' total worth (`m8-beavrs-hzp-results.md`); the **library** was compared with the measurements once (`m8-beavrs-library-results.md`, 2026-10-10): it reproduces the critical boron with all rods out (+8 ppm) and with bank D in (+22 ppm), and, since a correction for the banks shadowing each other was added (fifteenth protocol, `m8-rod-shadowing-results.md`), within 24 ppm at the other three measured states (+24, +15, +10 ppm; three of those cases were fitted); against 13 held-out transport cases it is within the limit at 9, and off by 560 to 700 pcm with SA and SB in, which no fit case had, so any state with those banks in is unvalidated (the library's README lists the checked states; `jointChecked` has 13 entries). Also not supported: the temperature feedback. The transport model's isothermal coefficient is 1.6 to 2.0 pcm/°F too negative against the benchmark (all rods out and C and D in); the library's own coefficient is −3.57 pcm/°F whatever the rods, so it is 1.8 pcm/°F too negative with all rods out and **4.4 pcm/°F too positive** with C and D in (measured −8.01). The bank worths: D and C were not computed for the transport model (one case failed the drift check); in the library D is good (−3.5 %) and C fails (−32 %), five of the seven sequential worths fail. No decay heat, no pressure, no xenon worth. A trip scrams the rods at 1.7 MW.

## A defect this work found and fixed

The OpenMC libraries inherited a heat sink at 293.15 K from the M1 library, but their tables start at 294 K. The pool cooled below 294 K within seconds, and the runtime reported `outOfDomain` (fuel and coolant temperature) for a shift of under 1 K, on every run. The sink is an assumption either way; it is now 294 K (`export_openmc.py`, both shipped OpenMC manifests).

## To widen or promote the envelope

1. M7: the first comparison (steady power ascension) failed on the power defect. A second dated protocol made heat transfer depend on temperature and a power law with n = 0.22–0.27 met its adoption rule for both cores (`m7-heat-transfer-results.md`); the libraries now carry it (format v2, 2026-10-06), and a second hot-element protocol found the measured thermocouple temperature consistent with it given the thermocouple's own pulse-derived peaking (`m7-hot-element-2-results.md`); `validated-for-domain` also needs a matched core and stated uncertainties.
2. A rod-pairs family (plan 02) would let the joint check cover the rod combinations a lesson uses.
3. Fuel-follower bins: decided 2026-10-06 to defer (`TODO.md`). The lesson uses element power, which is unaffected; power density in partly filled follower bins reads low and must not be used.
