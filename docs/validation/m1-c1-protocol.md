# M1 comparison C1: protocol (written before running)

Committed before any C1 simulation was run, so the metrics and thresholds can't be tuned to the results
(plan 07: "define the metrics and the decision process before looking at results").
Author: Claude Code, 2026-09-26. The results go in `m1-c1-results.md`. The GO/NO-GO is **proposed** to the user, not decided here.

## What was looked at before writing this

- The screened data (`validation/pulse_screening.py`): per-core consistency and the per-$ medians of cores 246 and 242
  (peak power, energies, FWHM, T1, rod position). **No simulated values for these cores were computed before this file was committed.**
- The earlier pooled comparison (`validation/pulse_comparison_report.json`), which is why this protocol exists.

## Data selection

- Screened pulses only (`screen_pulses`, SCREEN_VERSION 1), with `rho_dollars` ≥ 1.05.
- **Primary core: 246** (148 kept pulses, 2021-12-08 to 2022-01-27, $1.05–2.00; Spearman rank correlations: $ vs peak power 0.98, $ vs rod position −0.98).
- **Cross-core check: 242** (98 kept, 2019-11 to 2021-05, $1.00–2.00; 0.99 / −0.84). Never used for calibration.
- Not used: the 1990s cores (142, 145, 147) have $ vs power rank correlations of 0.43, 0.21 and −0.35, so their $ column isn't comparable.
- **Scored quantity: peak power.** Not scored:
  - FWHM: stored at 0.1 s resolution, and pulses above ~$1.4 are 10–40 ms wide, so they read 0.1 or 0.0.
  - Energies: the windows of the three columns aren't documented, and `E1pct` includes the post-pulse tail.
  - Temperatures: T1/T2 are instrumented-element thermocouples, while the model gives a core-average fuel temperature.
  Energy and T1 are **reported** beside the model values for information only.

## Simulation of one pulse ($ value d)

- Library `libraries/triga-jsi` (status experimental, values `assumed`), engine `physics_ref`, default solver settings, outer step 5 ms.
- Safety, shim and regulating rods fully out. The transient rod starts at the position x0 where
  `worth(1) − worth(x0) = d × β` (β = the library's 0.0070), found by bisection.
- A test-only calibration offset makes that state exactly critical; source S = 0; start from `critical-equilibrium` at **P0 = 1 W**
  (the actual JSI pre-pulse power isn't in the data; sensitivity to P0 = 100 W is reported).
- Mode `pulse`; the transient rod is **fired** (ramp to fully out over (1 − x0) × fireTime, fireTime = 0.08 s `assumed`). Run until power has
  fallen below 1% of peak and at least 0.2 s after the peak, or 10 s.
- Output: peak power (engine-tracked over internal steps), energy at the end, core-average fuel temperature rise.

## Calibration (one parameter, labelled as a calibration)

- The only calibrated parameter is a scale factor **s** on the fuel-temperature reactivity table (s = 1 is the library as-is).
- **Split of core 246:** pulses with an odd `pulse_id` are calibration, even are held-out.
- **Fit:** s minimizes the sum of squared `ln(P_sim(d_i; s) / P_exp,i)` over calibration pulses with d ≥ 1.30, by golden-section search on [0.25, 4].
- Uncalibrated (s = 1) results are reported as well.

## Metrics

- e_i = ln(P_sim(d_i) / P_exp,i). RMS(e) and mean(e) (the bias), per group.
- Groups: held-out 246 with d ≥ 1.30 (**primary**); held-out 246 with d < 1.30 (informational: near prompt critical, the ejection ramp and $ uncertainty dominate); core 242 with d ≥ 1.30 at the core-246 s (cross-core).
- **Reactivity uncertainty:** each metric is also computed with every d shifted by ±$0.05, to show how much a plausible $ calibration error moves it.

## Proposed decision thresholds (fixed now)

| ID | Criterion | Threshold |
|---|---|---|
| H1 | Held-out core 246, d ≥ 1.30: RMS(e) after calibration | ≤ ln 1.5 = 0.405 (typical error within a factor of 1.5) |
| H2 | Core 242, d ≥ 1.30, using the core-246 s | ≤ ln 2 = 0.693 |
| H3 | Fitted s | within [0.5, 2] (outside means the assumed feedback is badly off, not just calibrated) |

- If H1–H3 all hold, **propose GO** to the user for M1: "the engine with one labelled calibration reproduces measured peak powers of one core configuration and transfers to another".
- If any fails, **propose NO-GO** for M1 as stated, with the failed item and the likely cause, and ask whether to change the model or the goal.
- Either way the library stays `experimental` until parameter check C2 is done.
