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

## C2 pass 2 (2026-09-27): Švajger et al., NET 56 (2024) 1165–1203

This is the JSI group's own comparison of the same pulse database with Fuchs–Hansen, Nordheim–Fuchs and their Improved Pulse Model (IPM).
It settles the question C1 raised:

- **Their model shows the same misfit.** On a single core (4 April 2018, their Fig. 42) the IPM "always predicts higher maximum power than
  experiments": about 85% higher at $2 and 9% at $3. That is the steep low-$ behaviour C1 found (our uncalibrated engine: +28% at $2 against core 246).
- **Their explanation:** the inserted reactivity comes from rod-calibration curves and carries about 5% uncertainty (Table 14). It shifts with
  core composition (number and position of fuel elements). Measurements at low power are noisier, and their conclusions say the theoretical models
  "can only be applied at higher reactivity". Across core configurations, the measured peak power moves the opposite way from the models
  (more fuel elements: models higher, data lower; §9.3).
- **Energy windows:** E1000 is their "1000-points method" (1000 samples either side of the peak). The three windowing methods agree at high
  reactivity and diverge at low reactivity (their Fig. 40, 43), which fits the steep measured energy law.
- **Inputs, cross-checked:**
  - Computed α(T) for standard fuel (their Table 2, Serpent, ENDF/B-VII.0): −6.54, −9.19, −9.71, −9.68, −9.81 pcm/K at 400–800 K. This agrees
    with the value we read off Vavtar's Fig. 1 to about 10% up to 500 K, and stays flatter above it.
  - α range 5–10 × 10⁻⁵ /K, median 7.5 × 10⁻⁵, 1σ 20%.
  - Fuel mass 2.36 kg per element (their Table 10).
- **An inconsistency to resolve, not tune:** 56 elements (our library's geometry) × 2.36 kg = 132 kg, against the library's `assumed` 84 kg.
  With 132 kg, γ = α/(m·cp) drops to about 1.3–1.4 × 10⁻⁹ /J, where Vavtar & Snoj 2021 use 2.1 × 10⁻⁹. Švajger's own constant inputs
  (α 7.5 × 10⁻⁵, C 341.6 J/(kg·K), 57–61 elements) give 1.5–1.6 × 10⁻⁹. So the two JSI papers imply different γ.
  The library keeps 84 kg (γ ≈ 2.1 × 10⁻⁹, matching Vavtar) until the user decides; 132 kg would raise the model's peak power by about 1.5×,
  toward the IPM's own overprediction.

**Conclusion for M1.** C1's criterion (point kinetics matching measured peak powers within ×1.5 across $1.3–$3) is stricter than what the source
group's own, more detailed model achieves on its own data. Failing it no longer says our engine or inputs are wrong. It says the criterion asks for
something the measured reactivity axis can't support at low $. A fair M1 needs a different criterion (the user's decision), for example:
1. **Code-to-code:** match the published IPM/FH with the published inputs (we do: 284 MW at $2 against about 265–290 MW), and
2. **Code-to-data where the source trusts its data:** within the paper's uncertainty band at d ≥ $2, and a single core only (not pooled
   across configurations).

## C2 pass 3 (2026-09-27): fuel mass

The γ "inconsistency" from pass 2 is resolved, and the library's 84 kg is wrong:
- **Table 10 of Švajger et al. gives α = 10 pcm/°C** (the value was lost in text extraction). Then γ = α/(mC) = 1 × 10⁻⁴ / (59 × 2.36 kg × 341.6 J/(kg·K))
  = 2.1 × 10⁻⁹ /J, exactly Vavtar & Snoj's value. The two papers agree: real fuel mass with a round, high-end α.
- **2.36 kg per element matches the geometry:** fuel meat Ø3.63 × 38.1 cm minus the Ø0.635 cm Zr rod is 382 cm³; U-ZrH1.6 with 12 wt% U is about 6.18 g/cm³
  (rule of mixtures, U 19.05 and ZrH1.6 5.66 g/cm³); 382 × 6.18 = 2.363 kg.
- **The C1 cores, from the database's core maps** (trigapulse.ijs.si `242.pdf`, `246.pdf`): both use only standard 12 wt% fuel.
  Core 242 (26 Sept 2019) has **59** elements in the core; core 246 (23 July 2021) has **65** (two more are in the storage rack, not counted).
  That is 139 kg and 154 kg of fuel.
- **84 kg is unsourced:** it came in with the first parameter commit (`15192b3`) with no citation, and equals 36 elements, fewer than any JSI core.
  It reproduced γ ≈ 2.1 × 10⁻⁹ only because a too-low mass cancelled the figure-read α(T) (6–9 pcm/K, lower than Table 10's 10 pcm/K).
- **Consequences:**
  1. A faithful model is one library per core (fuel mass N × 2.363 kg), not one library for both. C1 used one library for two cores
     that differ by 6 elements (10% of fuel mass, different geometry and rod worths).
  2. With real mass and the figure-read α(T), γ ≈ 1.3–1.4 × 10⁻⁹, and the model's peak power rises about 1.5×. That lands near the source group's own IPM,
     which overpredicts the data by about 85% at $2.
  3. Which α to use (the Fig. 1 curve, Table 2's computed values, or Table 10's constant 10 pcm/K) is a modelling choice. The first two agree within about 10% up to 500 K.
- **Not changed yet:** the library still has 84 kg. Changing mass or α and re-running C1 is a protocol change, so it waits for the user's decision on the M1 criterion (pass 2).
