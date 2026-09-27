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

## Run 2 (2026-09-27): cited inputs, protocol unchanged

After the user accepted the NO-GO, C2 replaced the assumed kinetics and fuel inputs with values checked in Vavtar & Snoj,
EPJ Web Conf. 247, 08006 (2021) (JSI group, CC-BY 4.0): cp(T) = 333 + 0.678 (T − 274.15) J/(kg·K) (their eq. 1.8, citing Simnad),
|α_f|(T) rising from 6.2 to 8.9 × 10⁻⁵/K between 20 and 300 °C and then falling slowly (their Fig. 1, read by eye, ±0.5 × 10⁻⁵/K),
the Table 1 delayed-group betas, and ℓ = 4 × 10⁻⁵ s. The fuel mass (84 kg, still `assumed`) gives γ = α/(m·cp) = 2.0–2.15 × 10⁻⁹ /J
over 293–573 K, matching the paper's γ = 2.1 × 10⁻⁹. `validation/c1_comparison.py` and the thresholds weren't touched;
report in `validation/c1_report_run2.json` (run 1 stays in `c1_report.json`).

| ID | Run 1 (assumed inputs) | Run 2 (cited inputs) | Threshold |
|---|---|---|---|
| H1 held-out 246 RMS | 0.614 | **0.615** | ≤ 0.405 |
| H2 core 242 RMS | 0.880 | **0.794** | ≤ 0.693 |
| H3 fitted s | 2.63 | **4.00** | [0.5, 2] |
| Uncalibrated bias, held-out 246, d ≥ 1.30 | +0.94 | **+1.48** | — |

**Still NO-GO.** But the reason is now clearer:

- **The engine matches the published model with the published inputs.** Uncalibrated, a $2.00 step gives 284 MW peak, 6.9 MWs energy and a
  196 K core-average fuel rise. Vavtar & Snoj's own Fuchs–Hansen and improved pulse models give about 290 MW and 265 MW at $2 (their Fig. 2 and 4).
  Measured medians at $2.00: 222 MW (core 246), 138 MW (core 242); E1000 6.0 MWs; instrumented-element rise ~250 K.
- **The disagreement is at low $.** Measured peak power falls with (d − 1)^3.1–3.8, and no point-kinetics model with these inputs does that:
  realistic cp(T) and α(T) move together (γ nearly constant), so the square law survives. Fitting s to the whole range therefore pushes s up
  (to 4.0) to pull the model down at low $, and it then misses both ends.
- **Next suspect: the $ assigned to each measured pulse**, not the physics inputs. A reactivity axis stretched at low $ (for example from the rod
  calibration used for each core, or the prompt-jump correction) would produce exactly this pattern. Švajger et al., NET 56 (2024) 1165–1203,
  compares these same measurements with Fuchs–Hansen; it is the next thing to read (not yet checked: the PDF exceeds the fetch limit).
- **Energy points the same way.** The pooled pulse comparison (`validation/pulse_comparison_report.json`, regenerated with the cited
  library) gives measured E1000 ∝ (d − 1)^2.65 against the model's ^0.74. Every pulse model has energy roughly linear in the prompt excess
  (Nordheim–Fuchs: E = 2ρ′/γ), so a measured exponent near 2.7 is hard to get from any feedback physics. It is easy to get from a compressed
  or offset reactivity axis, or from an E1000 integration window that varies with pulse size (the window is undocumented).
- **Also fixed in C2:** `validation/pulse_comparison.py` computed its Nordheim–Fuchs reference from a hardcoded α = 1.05 × 10⁻⁴ /K instead of the
  library. It now linearises the library's own ρ_fuel(T) and cp(T) over each pulse, and agrees with the engine within 2% at $1.50–$2.00.
