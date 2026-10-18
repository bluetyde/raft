# M8 BEAVRS hot zero power: the library against the cycle 1 physics tests (twelfth protocol, written before any run of it, 2026-10-10)

This is M8 step 6 (`docs/m8-second-reactor-plan.md`). The eleventh protocol (`m8-beavrs-hzp-protocol.md`) tested the **transport model**; this one tests the **library built from it** (`libraries/pwr-beavrs-hzp-openmc`, the Python reference engine reading the manifest), against the same measured values. The library sums single-bank tables, so it can differ from the transport model wherever several banks are in. Method as in M7: the library is fixed by its digest below, every metric is run once, nothing is refitted afterwards, errata are not fixes, the library stays `experimental`.

## What is fixed

- **The library:** `libraries/pwr-beavrs-hzp-openmc`, git `b6ff0e8`, manifest SHA-256 `e9103694b658ebf986c9c6b6d66fec625d64efcce4dd823ba87d290a1123ae35`. The analysis refuses to run if the manifest hash differs.
- **The engine:** `physics_ref` (Python), engine version 0.4.0. The TypeScript engine is not used here; it agrees with the Python one on the golden vectors and on this library's critical boron (`web/src/sim/beavrs-library.test.ts`).
- **The measured data:** the table of the eleventh protocol (critical boron 975, 902, 810, 686 and 508 ppm at S0, S1, S2, S4 and S7 with σ 22 ppm; bank worths D 788, C 1203, B 1171, A 548, SE 461, SD 772, SC 1099 pcm; ITC −1.75 pcm/°F at all rods out and −8.01 pcm/°F with C and D in, σ 0.54). The states S0 to S7 are the cumulative insertions of that protocol (banks D, C, B, A, SE, SD, SC in that order; the rods not named are at the benchmark configuration, D at step 213).

## Disclosure: what was seen before writing

This protocol is **not blind**. Seen:

- Everything in the eleventh protocol's disclosure and its results (transport critical boron at all five states, bank worths of B, A, SE, SD, SC, the ITC).
- The exporter's self-check (`pipeline/openmc/results/beavrs_export_report.json`): for 45 transport cases the library's summed prediction against the transport reactivity. At the reference it is exact; for the single-bank cases it reproduces them to the table fit; with several banks in it differs: C and D in +420 pcm, A to D in +1106, A to D, SE, SD, SC in +1953 (the library is less negative), and at the measured boron of S4 and S7 (686 and 508 ppm) +1203 and +2243 pcm. The library's critical boron at all rods out is 983.18 ppm (a Python and TypeScript check).
- The single-bank worths in the library's tables, from ARO: D 760, C 816, B 827, A 230, SA 685, SB 811, SC 495, SD 525, SE 422 pcm.
- **Not seen:** the library's own critical boron, sequential worths or ITC at any state except the one named above; no run of the analysis of this protocol.

## Predictions, written before the run (from the numbers seen above; the run decides)

- **A, critical boron (error = the library's critical boron minus the measured):** S0 about +8 ppm and S1 about +22 ppm (single bank: as the transport model); **S2 about +50, S4 about +93 and S7 about +163 ppm** (the summed tables are not negative enough, divided by the boron worth 12.6 pcm/ppm).
- **B, sequential worths:** each bank's worth in the library is its single-bank worth from ARO. D 760 against 788 (about −4 %), **C 816 against 1203, B 827 against 1171, A 230 against 548, SD 525 against 772, SC 495 against 1099** (all well short, because the real worth of a bank grows when others are in), SE 422 against 461. The total of the seven banks about 4075 against 6042 pcm (−33 %).
- **C, ITC:** the library's coefficient at all rods out about −3.6 pcm/°F (from the fuel and coolant tables, ±30 K), against −1.75; with C and D in the library has the **same** −3.6 (its temperature tables do not depend on the rods) against −8.01.
- **Overall expectation:** the library reproduces the critical boron at the reference configuration and with D in, and fails with several banks in, the sequential worths and the temperature coefficient at D and C in. If the run shows otherwise, the protocol's labels stand and the surprise is reported.

## The question

Does the library, with its summed tables, reproduce the measured critical boron, the sequential bank worths and the isothermal temperature coefficients of the cycle 1 hot zero power tests within the benchmark's stated uncertainties, and how large is its departure from its own transport source at those states?

## The computations (fixed now)

Reactivity is the engine's `reactivity(t, y)["total"]` at the state (rods, boron, `Tfuel`, `Tcoolant`), from a fresh engine at zero power; every number is ρ in pcm (1e5 ×). The reference boron is 975 ppm and the reference temperature 566.483 K.

- **A: critical boron** for S0, S1, S2, S4 and S7: the boron concentration in [300, 1600] ppm at which ρ = 0 (bisection to 0.01 ppm; the concentration must lie inside the library's domain, else the state is "not computed"). Error = critical − measured, in ppm.
- **B: bank worth** of bank i = ρ(S_{i−1}) − ρ(S_i) at 975 ppm and 566.483 K, for the seven banks in the order D, C, B, A, SE, SD, SC; and the total ρ(S0) − ρ(S7).
- **C: ITC** at S0 and S2 = [ρ(T+) − ρ(T−)]/108 °F with `Tfuel = Tcoolant = 566.483 ± 30 K`, at 975 ppm for S0 and 975 ppm for S2 (the measured S2 value is at 810 ppm; the library's temperature tables do not depend on boron or rods, so the choice does not change the library's number; the 975 ppm is stated for the record).
- **F: departure from the transport source.** For the six sweep cases that match a state: R-D-0 (S1 at 975), J-W2 (S2), J-W4 (S4), J-W7 (S7), J-B4 (S4 at 686) and J-B7 (S7 at 508), the library's ρ minus the transport ρ ((k−1)/k, from `pipeline/openmc/results/beavrs_sweep.jsonl`), with the transport case's statistical error. Reported, not labelled.

**Uncertainty of the library's numbers.** Each table used at a state has a `unc` column (the statistical error of the transport case it came from, zero at the reference). The error of a ρ is the quadrature of the `unc` values of the tables at their interpolated points (linear interpolation of `unc`), and for the critical boron it is that divided by the library's boron worth at the critical point (the table slope between the two nearest axis points). The errors of different tables are treated as independent. **z** = (library − measured)/√(σ_meas² + σ_lib²).

## Metrics and bands (fixed now)

As in the eleventh protocol: **good** |z| ≤ 1, **plausible** |z| ≤ 2, **fails** |z| > 2; the 50 ppm licensing criterion is also reported for the critical boron. Metrics: **A** five states; **B** seven worths plus the total (σ_meas of the total 77 pcm); **C** two states; **F** six differences (not labelled). The seven worth errors are treated as independent, as before (they are probably correlated, which makes the total's σ too small).

## Decision process

1. **A good or plausible for four or five states:** the library's rod-combination claim may be widened to the states that are good or plausible, with the numbers shown. **Otherwise** the claim stays at the reference configuration, plus the states that are good or plausible; the README and `supported-envelope.md` get the measured differences. (The dilution lesson uses the reference configuration only, so it is unaffected either way.)
2. **B: a bank that fails** is recorded with its sign and size. If the total fails, the library's rod worth model is called **not validated for combined insertion**, which is what the library README already says without the numbers.
3. **C fails at either state:** the temperature feedback stays "not validated"; a failure at S2 only is recorded as the library having no rod dependence of its temperature tables.
4. **F:** the six differences are the size of the summed-tables error. If any exceeds the larger of 100 pcm and three times its statistical error, the results note names the smallest format change that would remove it (for example a cumulative-insertion table along the benchmark insertion order, or tables of temperature feedback by rod state), **without building it**; that is a separate decision.
5. **A case that cannot be computed** (critical boron outside the domain, or the library digest differing) is "not computed" and enters no decision item.
6. Under all outcomes the library status stays `experimental` and nothing is refitted.

## Implementation (after this protocol)

`validation/m8_beavrs_library.py` (the analysis, run once, output `validation/m8_beavrs_library_report.json`) and its test `validation/tests/test_m8_beavrs_library.py` on a planted library (a synthetic separable library with known worths: the analysis must recover the planted errors, refuse a changed digest, report "not computed" for a critical boron outside the domain; and deliberate breaks of the script, each caught). The results note is `m8-beavrs-library-results.md`.

## Limits, repeated

The library inherits the transport model's limits (the eleventh protocol's results): the ITC omits thermal expansion, one boron worth converts the errors, the seeds of the cases are the same. The measured data carry the plant's tilt and instrument effects, which the model does not. This protocol compares **zero-power reactivity** only; it says nothing about kinetics, power operation, xenon, decay heat or pressure, and nothing about the 3D power shapes.
