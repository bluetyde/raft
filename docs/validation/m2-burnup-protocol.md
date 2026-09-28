# M2 burnup calibration: protocol (written before any calibrated result was seen, 2026-09-27)

Disclosure: before writing this, one plumbing test was run with a throwaway low-statistics depletion table (1,000 particles):
core 242 at its critical state with a uniform 15 MWd/kg gave k = 1.009 ± 0.003 (`--quick`). No core 246 run with burnup, and no
production-table run, had been made.

## Why a calibration

The full-core model with fresh fuel is +$7 at core 242's measured critical state (`m2-core.md`). The open sources do not give the burnup
of every element in cores 242 or 246, so the model gets **one uniform burnup B for every fuel region** (elements and fuel followers). B is
a fitted parameter, not a measurement: it also absorbs every other bias of the model (nuclear data, the `assumed` geometry), so it is
called the *effective* burnup and is never quoted as the reactor's burnup.

## Inputs (open sources only; no ICSBEP data)

- **pungercic2024**: A. Pungerčič, A. Haghighat, L. Snoj, "JSI TRIGA fuel rod reactivity worth experiments for validation of Serpent-2
  and RAPID fuel burnup calculations", Nuclear Engineering and Technology 56 (2024) 3405–3424 (CC BY-NC-ND 4.0).
  - Core 246 (64 elements, 6 April 2022) critical at low power with **T up, C 536.6, S up, R 535** (section 2.3.1). C (compensating)
    is our K (shim, D10), S is V (safety, C10).
  - Serpent-2 burnups of 8 core-246 elements: 1.9 to 21.0 MWd/kg (Table 8).
  - Measured burnup reactivity coefficient of an all-SS-12% core (cores 216–232): **−232.8 ± 19.8 pcm per MWd/kg** of core-average
    burnup (Table 7).
- **pungercic2021**: A. Pungerčič, D. Čalič, L. Snoj, "Burnup calculations of the JSI TRIGA reactor fuel and comparison with measurements",
  EPJ Web of Conferences 247 (2021) 08009 (CC BY 4.0): typical fuel burnup ~20 MWd/kg in 2020, maximum 30; an absolute excess
  reactivity measurement has 1σ > 500 pcm; Sm-149 in equilibrium above ~4.5 MWd/kg.
- Depletion: `pipeline/openmc/pin_depletion.py` (unit cell, OpenMC ENDF/B-VIII.0 thermal chain, 14 W/g, 294 K, xenon-free
  Monday state), table in `pipeline/openmc/data/jsi_fuel_depleted.json`.

## Fit (one parameter)

B246 = the uniform burnup at which the model of core 246 at its critical rod positions has k = 1, by linear interpolation between
model runs at table burnups bracketing k = 1 (standard statistics: 20,000 × 150, 50 inactive). The fit uses nothing else.

## Tests (the fit never sees these), with pass criteria fixed now

| # | Test | Pass if |
|---|---|---|
| T1 | Core 242 (58 elements, 2020-10) at its measured critical state (T, V up, K 499, R 500) with B = B246 | \|ρ\| ≤ 500 pcm (the measurement's own 1σ, pungercic2021). Core 242 is 18 months older, so it should read slightly **positive** if anything; the sign is reported, not tested. |
| T2 | Burnup reactivity coefficient: slope of core 246's ρ against B over B246 ± 3 MWd/kg | within 2σ of −232.8 ± 19.8 pcm/(MWd/kg), combining both uncertainties |
| T3 | B246 itself vs the open burnups | reported only: 1.9–21.0 MWd/kg (8 elements, pungercic2024), ~20 typical (pungercic2021). A B246 outside 0–30 MWd/kg would show that the calibration is absorbing a large model bias, and is flagged. |
| T4 | Core 242 transient rod worth (0 → 900 steps) with B = B246, in dollars with the model's own β_eff | reported against the table ($4.33 = 3034 pcm / 700 pcm) with the fresh-fuel result ($3.66); no pass bound, since the table's $ scale is itself uncertain (C7 found the M1 $ labels overstated) |

## What would change the plan

- T1 fails: the uniform burnup is too crude (the burnup spread across rings matters) or the two cores differ in more than burnup;
  report, don't refit.
- T2 fails: the depletion (the specific power, the temperature, or the unit-cell spectrum) misrepresents the core; report.
- No refitting after the tests are seen; any change is a new, dated protocol.
