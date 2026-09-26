# M1 comparison C1: results

Run 2026-09-26 exactly as fixed in [m1-c1-protocol.md](m1-c1-protocol.md) (committed `88e9197` before any run).
Code: `validation/c1_comparison.py`. Full numbers: `validation/c1_report.json`.
**Proposal to the user: NO-GO for M1 as stated.** The decision is the user's.

## Checks (thresholds fixed in advance)

| ID | Criterion | Threshold | Result | Pass |
|---|---|---|---|---|
| H1 | Held-out core 246, d ≥ 1.30, RMS ln-error after calibration | ≤ 0.405 (×1.5) | **0.614** (×1.85), bias −0.03, n = 49 | no |
| H2 | Core 242, d ≥ 1.30, core-246 calibration | ≤ 0.693 (×2) | **0.880** (×2.4), bias −0.77, n = 59 | no |
| H3 | Fitted feedback scale s | in [0.5, 2] | **2.63** | no |

Calibration: 53 odd-id pulses of core 246 with d ≥ 1.30. Held-out: 49 (d ≥ 1.30) + 25 (d < 1.30).

Supporting numbers:
- **Uncalibrated (s = 1):** held-out 246 RMS 1.12 (bias +0.94: the model is too high on average); core 242 RMS 0.48 (bias +0.21).
  The library as-is happens to fit core 242 better than 246. The two cores differ by ~60% in measured peak power at $2.00 (138 vs 222 MW).
- **$ uncertainty ±$0.05:** held-out 246 RMS 0.59–0.68 after calibration. A plausible $ error doesn't explain the misfit.
- **Pre-pulse power 1 W vs 100 W:** RMS 0.6141 vs 0.6142. Irrelevant.

## The main finding: the shape is wrong, not just the level

Log-log slope of peak power against prompt excess (d − 1), for d ≥ 1.30:

| | Core 246 | Core 242 |
|---|---|---|
| Measured (medians per $) | **3.75** | **3.06** |
| Model (any s) | 1.96 | 1.96 |

Calibrated core 246, sim/exp median ratio by $: 3.1 at $1.30, 1.0 at $1.55, 0.45 at $2.00.
A single scale factor on the feedback can only shift the curve. It can't turn a square law into a cube-or-steeper law,
which is why the fit is pushed to s = 2.6 and still fails at both ends.

The model reproduces the Nordheim–Fuchs square law because its fuel heat capacity and temperature coefficient change little over a pulse
(cp = 350 + 0.35 ΔT + 2e-4 ΔT² J/(kg·K) and α = −(1.05e-4 + 1.2e-7 ΔT) /K, both `assumed`). The measured data scale more steeply.
**Leading hypothesis (to test, not a conclusion):** the real temperature dependence of UZrH heat capacity and/or the prompt coefficient
is much stronger, putting the reactor in the Fuchs–Hansen regime (heat capacity rising with temperature gives a steeper-than-square law).
That regime is what the JSI pulse-database paper is reported to compare against. Consistent with this:
- Measured energy (`E1000`, window undocumented) at $2.00 is 6.0 MWs in core 246 against the model's pulse energy of ~1–4 MWs.
- The instrumented-element temperature rise T1 at $2.00 is ~250 K against a model core-average rise of 50 K (calibrated) or 129 K (uncalibrated).
  An element peaking factor of ~2 doesn't close that gap.

## What this means for M1

- The engine itself is verified (analytic tests, scipy cross-check). The failure is in the **physics inputs**, which are unverified estimates (review finding 4).
- M1 as stated ("reproduce TRIGA pulses against published data") isn't met, and calibrating a scale factor can't meet it.

## Proposed next steps (for the user to choose)

1. **C2 first:** get real UZrH1.6 cp(T) and α(T) from the sources (Simnad GA-A16377; JSI publications), with values checked, not recalled.
   Rebuild the library with them and re-run C1 **unchanged** (same protocol, thresholds and split). That's a fair second test of the model.
2. If the protocol is re-run after changing inputs, keep the core-246 split and core 242 held out. Report both runs; don't delete this one.
3. Optional: compute FWHM from the processed traces (`fetch_jsi_pulses.py`, needs a download) to add pulse width as a second scored quantity.

## Caveats

- The simulated "energy" in `c1_report.json` is the energy until the run stopped (up to 10 s with the rod out), so it includes the post-pulse tail.
  It isn't comparable with `E1000` and wasn't scored.
- One core configuration was calibrated. The thresholds were chosen by me, before the run. The user may judge them differently.
