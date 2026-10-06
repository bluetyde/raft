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

- No comparison with measured transients or powers of a real TRIGA yet (M7). So the library status stays `experimental` and the state can be `caution` at best, never `ok`.
- Rod interaction: rod worths are added as if the rods acted alone. Only the six holdout states per core check that; every other combination of two or more moved rods is `R_JOINT_UNCHECKED`. A low-power ascension moves several rods, so this reason is normally present.
- Long runs (xenon), high power, pulses, and the second TRIGA core.

## The warnings a window shows

A banner at the top of the operator and instructor windows follows the runtime's `validity` message:

| Level | Meaning |
|---|---|
| `ok` | supported state, inside the envelope (not reachable until the library is validated) |
| `caution` | inside the envelope, but the model is not validated for this state; the banner lists why |
| `warning` | outside the data range, or outside the lesson's envelope (power, fuel temperature or mode); the banner names the limit |

The AI operator never works toward a power above the envelope: the raise ceiling is the lower of 50 % of the setpoint and the lesson's limit, and an instructor goal above it is clamped (the instructor panel says "limited to … by the lesson envelope").

## A defect this work found and fixed

The OpenMC libraries inherited a heat sink at 293.15 K from the M1 library, but their tables start at 294 K. The pool cooled below 294 K within seconds, and the runtime reported `outOfDomain` (fuel and coolant temperature) for a shift of under 1 K, on every run. The sink is an assumption either way; it is now 294 K (`export_openmc.py`, both shipped OpenMC manifests).

## To widen or promote the envelope

1. M7: compare against measured data; only then can `status` become `validated-for-domain` for this domain.
2. A rod-pairs family (plan 02) would let the joint check cover the rod combinations a lesson uses.
3. Fuel-follower bins: decided 2026-10-06 to defer (`TODO.md`). The lesson uses element power, which is unaffected; power density in partly filled follower bins reads low and must not be used.
