# M7 core 134 feedback: the effective fuel temperature in transport (tenth protocol, written before any run of it, 2026-10-07)

It follows the ninth protocol (`m7-core134-data-protocol.md`) and its results (parts P and C). Part C found that the library's uniform fuel temperature is a partial explanation of the weak feedback: a calculation from the model's own power shapes gives a reactivity-effective fuel temperature 1.16 times the volume mean (range 1.04–1.27), removing 31 % of the step 7 shortfall. That calculation is a proxy: it assumes the reactivity weights are a power of the local power density. This protocol tests the effect in transport. It changes nothing in any library. Nothing here has been run.

## Disclosure: what was seen before writing

This protocol is **not blind**.

- The ninth protocol's results: the proxy factor κ = 1.159 (primary: weights F², exponent 0.22), its range 1.037–1.268 and its radial and axial parts (1.08 and 1.07); the what-if with that factor (31 % of the step 7 shortfall removed, residual 69 %).
- **The uniform-temperature runs of the seventh protocol** (core 134, default fuel, 100 000 particles): the reactivity change from 294 K to 372 K is −476 ± 44 pcm (A294 +347, A372 −129 pcm). The new runs repeat that pair with better statistics.
- **Not seen:** any run of core 134 with different fuel temperatures in different elements, and the per-element temperatures this protocol defines.

## The test

**Model.** Core 134 at the reference state (rods T=0, K=200, V=200, R=727.3; the library's reference), default fresh fuel (H/Zr 1.60), water at 294 K. Only the fuel temperature changes, as in the library's own fuel temperature cases.

**Per-element temperatures.** From the core 134 library's shape arrays at the reference state (the in-core axial bins; the bin below the core is left out): the relative power density of each of the 48 fuel positions `F_e = (f_e/V_e) / (Σf/ΣV)` with `f_e` the element's fission fraction in the in-core bins and `V_e` its fuel volume there. The temperature rise of the element is

    ΔT_e = ΔT̄ · F_e^(1/(1+n)) / [ Σ V_e F_e^(1/(1+n)) / Σ V_e ]

so that **the volume mean of the rise is ΔT̄**. Primary: **ΔT̄ = 78 K** (the volume-mean rise of step 7 of Table IX is 77 K; 78 K makes the mean 372 K above 294 K) and **n = 0.22** (the fitted exponent of the burned libraries, as in part C). Each element's fuel carries its own temperature (`T_e = 294 K + ΔT_e`) throughout its height: **the axial distribution is not modelled here** (the axial part of part C's factor, 1.07, is not tested).

**Runs** (`core_model`, `openmc-vr`, **600 000 particles, 150 batches, 50 inactive**, seed 1, about 40 minutes each; a statistical error of about 16 pcm per run):

| Run | Fuel temperature |
|---|---|
| R294 | uniform 294 K (`--tfuel 294`) |
| U372 | uniform 372 K (`--tfuel 372`) |
| NU372 | per element, T_e as above (`--element-tfuel`), mean 372 K |

`core_model` gets the option `--element-tfuel FILE` (one fuel material per position with its own temperature; the three fuelled followers' fuel gets its element's temperature). With every temperature equal it must reproduce the uniform run: checked in the test.

## Metrics and bands (fixed now)

| # | Quantity | Reading |
|---|---|---|
| **T1** | `κ_T = Δρ_NU / Δρ_U`, with `Δρ_X = ρ(X) − ρ(R294)` and its standard error | **large** κ_T ≥ 1.35; **partial** 1.05 ≤ κ_T < 1.35; **none** κ_T < 1.05 |
| **T2** | agreement with the proxy of part C (radial part only, since the axial distribution is not modelled: 1.080 primary) | **agrees** if `|κ_T − 1.080| ≤ 2σ_κ`; **differs** otherwise (higher or lower) |
| **T3** | the what-if of part W with κ_T in place of the proxy: the labels of the reactivity loss at steps 1–7 against Table IX (bands of metric A') and the fraction of the step 7 shortfall removed | reported |
| **T4** | reported only: the temperatures used (minimum, maximum, the 48 values), the three reactivities with their standard errors, the volume-mean fuel temperature of NU372 | |

The proxy to compare with is the **radial** one because only the radial distribution is in the transport model. T3 uses κ_T as the effect of the radial distribution alone; the axial part (proxy 1.07) is reported separately as untested.

## Decision process

1. **κ_T partial or large and agrees with the radial proxy:** the proxy is confirmed in transport; the radial part of the effective-temperature effect is real and of the stated size. The what-if T3 is the corrected statement of what it removes. A library change (a table referred to an effective rather than the mean fuel temperature) would need its own protocol.
2. **κ_T none:** the proxy overstates the effect in transport; the uniform fuel temperature is not an explanation (for the radial distribution).
3. **κ_T differs from the proxy (higher or lower):** report the transport value as the one to use and the proxy as inadequate; the axial part remains untested either way.
4. **In every case** nothing in any library changes and their status stays `experimental`.
5. **Not tried after seeing the results:** other ΔT̄, exponents, particle counts or distributions than those listed; any axial distribution (it needs axially split fuel cells and is a separate protocol); a fit of anything.

## Implementation (to be written after this protocol)

`--element-tfuel` in `pipeline/openmc/core_model.py` (with a model test that equal temperatures give the uniform model), `validation/m7_core134_transport.py` (the temperatures, which it writes as `pipeline/openmc/results/core134_element_tfuel.json`, and the analysis, with a synthetic test), the three runs written to `pipeline/openmc/results/core134_transport.jsonl`, the report `validation/m7_core134_transport_report.json` and the results note `docs/validation/m7-core134-transport-results.md`. The runs and the analysis are done once.

## Limits, repeated

The statistical error of κ_T is about 0.065 (two runs of 16 pcm against a change of about 500 pcm), so κ_T of 1.08 is distinguishable from 1.00 at about 1.2σ only: a "none" or "partial" label near the 1.05 edge is not a sharp statement. The axial distribution (the other 1.07 of the proxy) is not tested. The temperatures follow the model's own power shapes, which carry their tally uncertainty. One element temperature per element: no radial profile inside the pellet.
