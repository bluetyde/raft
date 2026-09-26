# Plan 07: Validation

How we show the model is right, and how right. Validation runs through every milestone, and M7 is the final full comparison.
It lives in `validation/`, and its results go into each library's `validation/report.json`, so the app can show them.

## Five levels

| Level | Question | Method | When |
|---|---|---|---|
| **1. Code verification** | Do we solve the equations correctly? | Analytic tests in [01](01-physics-core.md): prompt jump, inhour, Nordheim–Fuchs, source multiplication, xenon | M1, then every change |
| **2. Port agreement** | Does TypeScript match Python? | Golden vectors in `schema/vectors/`, run in CI on both sides | M4, then every change |
| **3. Transport model** | Is the OpenMC TRIGA right? | k-eff against the benchmark; rod worths and other measured quantities the benchmark publishes | M2 |
| **4. Method error** | How much does the precomputed-shape approach cost? | Holdout OpenMC runs at off-grid states compared with interpolated shapes and reactivities; joint rod runs compared with superposition | M2–M4 |
| **5. System against measurement** | Does the whole thing behave like the real reactor? | Published measured TRIGA data | M1 (pulse), M7 (everything) |

**Independence:** golden vectors (level 2) catch port drift only. A mistake shared by both versions passes them.
Levels 1 and 5 plus an independently configured integrator (scipy) are what catch shared mistakes.

## Level 5 data to collect

Every data set goes into `validation/data/` with a full citation and a note on how it was digitized (tables or figures).

- **Pulses:** peak power, FWHM, energy released and peak fuel temperature, against inserted reactivity.
  This is the core test. **Source found:** the public JSI pulse database ([trigapulse.ijs.si](http://trigapulse.ijs.si/)):
  493 pulses from 1991 to 2021, with ρ in $, rod position, P_max, energy, FWHM, T_max and raw/processed traces.
  It has no license statement, so ask before redistributing. A published analysis of the earlier 289 pulses compares them with the adiabatic Fuchs–Hansen model.
- **Independent code comparison:** JSI's own Research Reactor Simulator models the same reactor.
  Compare pulse and xenon behavior with it (reference only; it's likely GPL, so no code reuse).
- **Rod calibration:** measured integral worth curves (compared with our OpenMC curves).
- **Temperature feedback:** measured reactivity loss with power or temperature.
- **Steady-state:** fuel temperature against power.
- **Xenon:** only if published for the facility. At TRIGA power levels the effect is small, and we say so.

**Before comparing,** match each measurement to the modeled configuration and conditions (core loading, rod positions, starting temperature).
Being from the same facility isn't enough. Keep **calibration cases** and **held-out cases** separate; results are reported on held-out cases only.

## Library status labels

- `synthetic`: made-up fixture, for tests only.
- `experimental`: built from real data but not yet meeting the validation criteria. Usable, and labelled as such in the UI.
- `validated-for-domain`: passed the defined checks over a stated domain. A failed comparison stays inspectable but never gets this label.

## Acceptance criteria

**Don't set numbers until the data is collected**, because the right tolerance depends on the data's own uncertainty.
Define the metrics and the decision process **before** looking at results, so results don't pick their own tolerances.
The form each criterion takes:
- Level 1: agreement to solver tolerance (effectively exact).
- Level 2: absolute-plus-relative difference below a stated tolerance on every vector.
- Level 3: k-eff within a stated number of pcm of the benchmark, compared with what published OpenMC/MCNP models of it achieve.
- Level 4: maximum and RMS shape error per bin, and reactivity error, across holdouts. Record them in the library and show them in the UI.
- Level 5: model against measurement, with both uncertainties, plotted. We report the agreement, whatever it turns out to be.

## Reports

- `validation/run_all.py` runs every level it can, then writes `report.json` and an HTML report with plots.
- The library carries the summary, and the app's About box shows it ("pulse peak within X% of measured over Y data points").
- A failed level 1 or 2 check fails CI. A worse result at levels 3–5 is recorded, not hidden, and flagged in the TODO.

## Honesty rules

- Never tune a physics parameter to match measurements without recording it as a **calibration**, with the original value kept.
- Keep sourced, computed and assumed values apart, and label which is which in the library.
