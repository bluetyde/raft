# M7 steady power ascension: comparison protocol (written before any comparison, 2026-10-06)

Plan 07, level 5: "Define the metrics and the decision process **before** looking at results." This file does that for the one lesson the project supports (`supported-envelope.md`): low-power ascension and hold. Nothing here has been run.

## Disclosure: what was seen before writing

- **The measured data** (`validation/data/jsi-steady-power/`), all of it, including the shape of the fuel-temperature rise (below).
- **The model's parameters, not its output:** `hA` = 3000 W/K (assumed), the fuel takes all the power (`fuelFraction` 1), pool mass 20 000 kg, fuel mass 137 kg, and the M2 temperature coefficients (fuel −8 to −14 pcm/K, coolant about +12 pcm/K, `m2-libraries.md`).
- **No model run** against these data, and no output of the library's temperature or rod tables at the measured states.
- **One hand estimate, made now and kept:** with the lumped model the mean fuel temperature rise at 250 kW is 250 000 / 3000 = 83 K, so the fuel feedback alone is about −660 to −1160 pcm against the measured 1427 pcm. **I expect metric A to come out low (plausible or fails).** The pool's heating does not close the gap: with a positive coolant coefficient it adds reactivity, so it lowers the model's power defect further, by up to about 70 pcm for a 6 K rise. This is written down so the result cannot be read back as a surprise.

## What is compared, and why this is the right test

The experiment holds the shim, safety and transient rods fully withdrawn, turns the pool cooling off, and steps the power from about 0.1 to 250 kW by moving only the regulating rod. At each steady power the reactor is critical, so **the reactivity the regulating rod adds equals the feedback reactivity lost to heating**. That is a measurement of the model's feedback chain: `hA` (how hot the fuel gets) times the fuel temperature coefficient, plus the pool's heating times the coolant coefficient. Both the heat transfer and the coefficients are `assumed` or fitted in the library, so this is the first test that is independent of how the library was built.

In the model each state is quasi-steady: the fuel's time constant is 15 to 20 s (137 kg × cp of 346–418 J/kgK / 3000 W/K), so at constant power `T_fuel = T_pool + P/hA`. The pool heats at P / (20 000 kg × 4184 J/kgK), about 11 K per hour at 250 kW, with no heat removal when the pump is off. The model's feedback at a state is then `rho_fb = fuelTemp(T_fuel) + coolTemp(T_pool)` read from the library's tables, and the rod reactivity needed is `−(rho_fb − rho_fb at the reference state)`. No time stepping is needed.

## Inputs fixed now

| Item | Choice | Why |
|---|---|---|
| Libraries | `triga-jsi-242-openmc` (primary) and `triga-jsi-246-openmc`, both reported | the measured core is not stated, so neither is privileged; neither is tuned |
| Power axis | `pCalculated` of Table 2: 0.09, 2.93, 43.6, 100.3, 188.9, 223.0, 250.0 kW up; 191.1, 103.7, 47.5, 0.29 down | recomputed from the ion cell current, calibrated at 250 kW; `pIndicated` is run as a sensitivity (the two differ by up to 16 % on the way down) |
| Reference state | state 1 (0.09 kW), fuel = pool = T0 | the data's own starting point |
| T0 | 25.8 °C (Table 1), sensitivity 30.8 °C (Table 2's first row) | the two tables disagree on the first row; the later rows agree |
| Pool temperature | two bracketing cases: **(i)** constant at T0; **(ii)** rising linearly with the state number from T0 to T0 + 6 K at state 11 | the data give no pool temperature and no times; the end reading of 32.4 °C against 25.8 °C bounds the pool's rise at about 6 K. All results are the spread over (i) and (ii) |
| Xenon | zero | one short exercise; the protocol does not state a prior history |
| Variants | **V0** the library as shipped (the prediction); **V1** `hA` calibrated on the 250 kW state only, every other state held out | `hA` is the one unmeasured parameter that decides the fuel temperature rise. V1 shows whether one parameter explains the shape; it is never reported as the library's accuracy |

## Metrics and bands (descriptive labels; fixed now)

The source gives no uncertainties, so these are not acceptance tolerances. They label how far the model is from the data. Each is applied to V0 and, separately, to V1.

| # | Quantity | Model value | Measured | Bands |
|---|---|---|---|---|
| **A** | Power defect at 250 kW | `−(rho_fb(250 kW) − rho_fb(0.09 kW))` | 1426.8 pcm | ratio model / measured: **good** 0.8–1.25, **plausible** 0.5–2, **fails** outside |
| **B** | Shape of the feedback with power: `rho_fb(P) / rho_fb(250 kW)` at the held-out up-leg states 43.6, 100.3, 188.9, 223.0 kW | as above | cumulative reactivity from Table 2 divided by the 250 kW value | max absolute difference: **good** ≤ 0.05, **plausible** ≤ 0.10, **fails** above |
| **C** | Fuel temperature rise against power: `θ(P) = (T(P) − T(0.09 kW)) / (T(250 kW) − T(0.09 kW))` at the same four states | model mean fuel temperature (the hot-element centre scale cancels in the ratio, which assumes the element's centre-to-mean ratio is the same at every power) | Table 1 | max absolute difference: **good** ≤ 0.05, **plausible** ≤ 0.10, **fails** above |
| **D** | Regulating rod worth curve, normalised: `rho(x) / rho(total)` against rod travel `x = (900 − step) / 719` | the library's regulating rod table for each core | Table A.1 (core 200) | max absolute difference: **good** ≤ 0.05, **plausible** ≤ 0.10, **fails** above. The total worth (3292.5 pcm) is **reported only**: it is a different core. In the model the inserted worth at travel x is `W(x) = rho_rod(1) − rho_rod(x)` from the library's table (position 1 = fully withdrawn) |

Notes on what each band means:

- **A** is the integral test. **B** and **C** separate the heat transfer from the coefficients: if A is low and C is good, the coefficients are the problem; if C is poor, `hA` (or the pool's heating) is. V1 does the same job numerically.
- **C** compares a model mean with a hot-element centre value, so only its **shape** is meaningful. The absolute temperature at 250 kW (model mean about 83 K above the pool, measured about 200 K above the start) is **reported, not banded**: it needs a peaking factor from the shape arrays, which is a separate piece of work.
- Every metric is computed for both pool cases, both libraries, and both power axes. The reported label is the **worst** label over those combinations that the protocol's own sensitivities (T0, power axis, pool) can reach, and the best is shown beside it. A result is "sensitive" if the two differ.

## Decision process

1. Run `validation/m7_power_ascension.py` (to be written; arithmetic on the library tables, a regression test on a synthetic library). It writes `validation/m7_power_ascension_report.json` and a table plus plot.
2. Report every metric with its label, including failures, in `docs/validation/m7-power-ascension-results.md`. No refitting after the results are seen: V1 is the only calibration and is defined above. Any other change is a new, dated protocol.
3. What the outcome changes:
   - **A or B fails:** the feedback chain of the OpenMC libraries disagrees with the one measurement we have. The model's validity banner for this lesson gets a specific reason (for example "power defect differs from measurement by X %") and `supported-envelope.md` says so.
   - **A good, B and C plausible or better:** supporting evidence, kept as such.
   - **Whatever the result, this data set cannot by itself earn `validated-for-domain`.** It lacks a matched core and any stated uncertainty. The status stays `experimental` until a measurement for core 242 or 246 with uncertainties exists (`jsi-steady-power/README.md`, "Not found yet").
4. Known limits, repeated here so the results are read with them: one run of one exercise by students ("typical real data"); one instrumented element; the pool temperature is inferred; the rod table is of another core; the lumped model has one fuel temperature and one heat transfer coefficient, so it cannot reproduce a temperature that depends on the radial and axial position.

## What would change this plan

- The core of Tables 1 and 2 is found: re-run with that core's library if it exists, and say so. The protocol's bands do not change.
- A measurement for core 242 or 246 with uncertainties is found: write a new protocol that sets the bands from the data's own uncertainty, as plan 07 asks. This protocol then becomes the first, rougher pass.
- The model gains a hot-element temperature (peaking factor from the shape arrays): the absolute fuel temperature in C then gets a band, in a new dated protocol.
