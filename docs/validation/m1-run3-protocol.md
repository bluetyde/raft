# M1 run 3: protocol (written before running)

Committed before any run-3 code exists or any run-3 simulation is run, so the inputs, metrics and thresholds can't be tuned to the results.
Author: Claude Code, 2026-09-27. The results go in `m1-c1-results.md` (a "Run 3" section). The GO/NO-GO is **proposed** to the user, not decided here.
Run 1 (C1, assumed inputs) and run 2 (cited inputs, same protocol) stay as they are.

## Why a new protocol

The user replaced C1's criterion (2026-09-27) after C2 and C7 showed:
1. The source group's own model misses the same data in the same way, so matching the labelled data within ×1.5 across $1.3–$3 isn't a fair test.
2. The database's $ labels overstate the prompt excess by about $0.27 (core 242) and $0.42 (core 246). Against the trace-inferred $, measured peak power
   scales with exponent 1.7–1.8, like point kinetics (`m1-c1-results.md`, C7).
3. The library's 84 kg of fuel was unsourced. The C1 cores hold 59 (core 242) and 65 (core 246) standard elements of 2.363 kg.

The agreed criterion has two parts: **(A) code-to-code** against the published model with the published inputs, and **(B) code-to-data** on the
trustworthy, high-$ pulses, **per core**.

## What was looked at before writing this

- Everything in `m1-c1-results.md` up to and including C7, and `validation/trace_period_report.json` (ω fits and inferred $ from the **existing**
  `libraries/triga-jsi`, 84 kg).
- One comparison of model and data on the inferred axis: pulse 521 (core 246, label $2.00, inferred about $1.54, measured 148.5 MW) against the old
  library's engine at $1.50 (72 MW). So I know that the old library was low for that pulse. **No simulation with the run-3 libraries has been run,
  and no Λ/γ values have been computed from the data.**

## Libraries (built by `pipeline/library/build_triga.py`, new `--core` option)

Two libraries, `libraries/triga-jsi-242` and `libraries/triga-jsi-246`, identical to `libraries/triga-jsi` except:

| Input | Value | Source |
|---|---|---|
| Fuel mass | 59 × 2.363 = 139.4 kg (242); 65 × 2.363 = 153.6 kg (246) | svajger2024 Table 10 (2.36 kg/element; geometry check 2.363 kg); element counts from the database core maps |
| Fuel ρ(T) table | Δρ∞ from svajger2024 Table 2 (Serpent, ENDF/B-VII.0, standard fuel): 0, −694, −1612, −2583, −3551, −4533 pcm at 294, 400, 500, 600, 700, 800 K; the 294 K point is used as the reference (293.15 K in the library, 0.85 K apart); beyond 800 K, α held at −9.81 pcm/K to 1200 K | svajger2024 Table 2 |
| cp(T) | 333 + 0.678 (T − 274.15) J/(kg·K) (unchanged) | vavtar2021 eq. 1.8 |
| Λ, β, groups | 40 µs; Table 1 betas (unchanged) | vavtar2021 |

Everything else (rod worth curve shapes, fireTime 0.08 s, geometry and power shapes, coolant) stays `assumed` and unchanged.
Table 2 is chosen over the Fig. 1 reading because it is a tabulated computation with stated uncertainties (±0.4 pcm/K), not a value read by eye.
Its caveat: it is k∞ of standard fuel, not the core's effective coefficient.

## Part A: code-to-code (the published model with the published inputs)

- A third library, `libraries/triga-jsi-paper`, reproduces the inputs of svajger2024 Table 10: α = −10 pcm/K constant (a linear ρ(T) table),
  C = 341.6 J/(kg·K) constant, m = 59 × 2.36 = 139.24 kg, Λ = 40 µs, β = 0.007 (Table 1 groups). Then γ = α/(mC) = 2.102 × 10⁻⁹ /J.
- Simulated exactly as in C1 (transient rod fired from critical at P0 = 1 W, fireTime 0.08 s, outer step 5 ms), at d = $1.5, $1.8 and $2.1.
- Reference: Fuchs–Hansen Pmax = (ρ − β)² / (2γΛ) with the same γ, Λ, β.
- **A1:** P_engine / P_FH within [0.75, 1.02] at all three points. FH is an upper bound: delayed neutrons and the finite ejection lower the peak, by about
  10–25% for the published IPM over this range (vavtar2021 Fig. 4). 1.02 allows for numerical tolerance.

## Part B: code-to-data, per core, on the trace-inferred $ axis

**Inferred $.** For each core, `validation/trace_period.py` (fit window 2–20% of the peak, as committed in `a4ab95c`) is re-run with that core's run-3 library
for the engine ω($) curve. A pulse is used if its trace fit succeeded and its inferred $ is **≥ 1.30**. (The agreed "d ≥ $2" isn't reachable on the corrected axis:
the highest inferred values are about $1.69 and $1.51. The intent, "the higher-$ pulses whose data the source trusts", is implemented as this rule.
Flagged to the user.)

**Simulation.** For each core, the engine with that core's library, set up as in C1 (no calibration: the calibration offset only makes the start critical;
s = 1) on a $ grid of 0.025 from $1.275 to $1.75. ln Pmax is interpolated linearly in $ between grid points.

**Metrics.** e_i = ln(P_sim(d_inf,i) / P_exp,i). Per core: RMS(e), mean(e), and the log-log slope of P_exp and of P_sim against (d_inf − 1) over the same pulses.
Sensitivity (reported, not scored): every d_inf shifted by ±$0.03 (about the spread of the per-session medians in C7).

| ID | Criterion (each core separately) | Threshold |
|---|---|---|
| B1 | RMS(e) | ≤ ln 1.5 = 0.405 |
| B2 | \|mean(e)\| | ≤ ln 1.3 = 0.262 |
| B3 | Measured slope − simulated slope | within ±0.4 |
| B4 | Pulses used | ≥ 20 per core (otherwise that core is reported as untestable, not failed) |

## Decision

- A1, and B1–B4 for both cores → **propose GO** for M1 as redefined: "with cited inputs and no calibration, the engine reproduces the published pulse model and,
  per core configuration, the measured peak powers on the trace-derived reactivity axis".
- Otherwise → **propose NO-GO**, naming the failed items and the likely cause.
- Either way: the inferred-$ axis depends on the library's Λ = 40 µs (8% uncertainty per svajger2024 Table 14), and B tests γ/Λ jointly. The libraries stay `experimental`.

## Outputs

`validation/m1_run3.py` → `validation/m1_run3_report.json` (all numbers above, per pulse and per core) and a "Run 3" section in `m1-c1-results.md`.
