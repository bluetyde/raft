# M7 core 134 feedback: ZrH nuclear data, temperature treatment and effective temperature (ninth protocol, written before any run of it, 2026-10-06)

It follows the eighth protocol (`m7-core134-conversion-protocol.md`) and its results, and the sixth and seventh. The fresh-fuel OpenMC model of core 134 gives a fuel temperature coefficient of about −6.2 pcm/K and a reactivity loss at the 1994 power ascension that is 37–40 % short of the measurement at step 7; the paper's thermocouple conversion is supported by independent evidence; the reference treatment, the first table interval and the fuel hydrogen content do not explain the shortfall. This protocol examines the three explanations that remain **inside the model**: (P) OpenMC's temperature treatment of the nuclide and thermal scattering data, (D) the ENDF/B-VIII.0 zirconium hydride data, and (C) the fact that the library applies one uniform fuel temperature while the real fuel is hottest where the neutrons are most important. It changes nothing in any library. Nothing here has been run.

## Disclosure: what was seen before writing

This protocol is **not blind**.

- The sixth to eighth protocols' results (the shortfall, the implied conversion of 1.30 falling to 1.04, the model's flat per-step coefficient of about −7.4 pcm/K against a measured one that grows from −6.3 to −10.8 pcm/K).
- **The data grids** (read from the HDF5 files, not their content): the nuclide data of ENDF/B-VIII.0 (H1, U235, U238, Zr) are tabulated at 250, 294, 600, 900, 1200 and 2500 K; the thermal scattering tables `c_H_in_ZrH` and `c_Zr_in_ZrH` at 296, 400, 500, 600, 700, 800, 1000 and 1200 K. So at 400, 500 and 600 K the thermal scattering data are exact, and the nuclide data (the Doppler broadening) are exact at 294 and 600 K and interpolated by OpenMC in between.
- **The existing pin-cell report** (`pipeline/openmc/pin_cell_report.json`, 40 000 particles, ENDF/B-VIII.0, the standard element in a unit cell with core-average water): the fuel temperature reactivity change against the reference of the pipeline (Švajger 2024 Table 2, Serpent with ENDF/B-VII.0): −572 pcm against −694 at 400 K (ratio 0.82), −1315 against −1612 at 500 K (0.82), −2170 against −2583 at 600 K (0.84), −3024 against −3551 at 700 K (0.85), −3891 against −4533 at 800 K (0.86), each with about 23 pcm of statistical error. **So OpenMC's pin cell is about 16 % weaker than the reference at 600 K, where all the data are exact and no interpolation is involved**; the ratio moves little with temperature. The reference is another code and another evaluation (VII.0), and a deficit that exists at the exact-data temperature points to the data or the model, not to the interpolation.
- A rough estimate made while designing this protocol: if the real fuel temperature is non-uniform with a power peaking spread of about 0.3 and the reactivity weights go as the flux squared, the effective fuel temperature rise exceeds the volume mean by about 13 %. A rough hand calculation, **not computed with the library's shapes**.
- The library's shape arrays for core 134 exist; **no effective-temperature factor was extracted from them**.
- **Not seen:** any run with another nuclear data library, any pin-cell run at 372 K, with another treatment or with more particles, any weighted temperature of the core.

## The shortfall to explain

At step 7 of Table IX (mean fuel temperature 98.7 °C, volume mean rise 77 K) the library's what-if reactivity loss is 424 pcm and the measured one 666 pcm, a ratio of 1.57. The fifth to eighth protocols' labels (metric A') count the step labels at steps 1–7 against the bands of the sixth protocol (good ≤ max(10 %, 10 pcm); plausible ≤ max(25 %, 25 pcm)).

## Part P: temperature treatment (pin cell, OpenMC; no new data)

Runs of `python -m pipeline.openmc.pin_cell` at **200 000 particles × 300 batches, 50 inactive** (a statistical error of about 10 pcm per run, a few minutes each):

| Run set | Treatment | Fuel temperatures |
|---|---|---|
| P1 | the current one (`interpolation`, default 294 K) | 294, 330, 372, 400, 500, 600 K |
| P2 | `nearest` with a tolerance of 300 K (every nuclide and thermal scattering table snaps to its nearest tabulated temperature) | 330, 372, 400, 500 K |

(The pin-cell script gets a `--method` and a `--tolerance` option for P2; nothing else in it changes.)

- **P1 metric:** `R(T) = Δρ_pin(T) / Δρ_ref(T)` at 400, 500 and 600 K, with the reference values −694, −1612 and −2583 pcm. **Constant** if the spread of R over the three temperatures is at most 0.08 (about twice the standard error of a ratio); **varying** otherwise.
- **P2 metric:** the difference of Δρ between P1 and P2 at each untabulated temperature (330 and 372 K for the thermal scattering data, 330, 372, 400 and 500 K for the nuclide data), with its standard error: a **treatment effect** if it exceeds 2σ. P2 snaps, so it is expected to differ; the point is whether the P1 curve is smooth and monotonic between the tabulated temperatures (P1 at 330 and 372 K between P1 at 294 and 400 K, by the ratio of the temperature differences within 25 %).

## Part D: the zirconium hydride and nuclide data (pin cell with another evaluation)

Runs of the same pin cell (P1 settings, 200 000 particles × 300 batches) with the **ENDF/B-VII.1** OpenMC library (the same S(α,β) names `c_H_in_ZrH` and `c_Zr_in_ZrH` and the same nuclide names) at 294, 400, 500 and 600 K. **This part needs a download** (the ENDF/B-VII.1 HDF5 library from `openmc.org/official-data-libraries`, of the order of a gigabyte): it is **not started without the user's approval** of the file, its source and its size. If it is not approved, part D is "not run".

- **D1 metric:** `R_VII.1(T)` at 400, 500 and 600 K against the same reference. The data are **the explanation of the 16 % deficit** if all three ratios are within 0.95–1.05 of 1 (the reference uses ENDF/B-VII.0, whose thermal scattering tables ENDF/B-VII.1 shares); **part of it** if the mean ratio rises by at least 0.05 over the VIII.0 value of P1; **not the explanation** otherwise.
- **D2 metric:** the ratio `Δρ_VII.1 / Δρ_VIII.0` at 400, 500, 600 K: the factor by which the library's fuel feedback would change with the older evaluation (a what-if factor, not an adoption).

## Part C: the effective fuel temperature (calculation from the library's shapes; no OpenMC)

From the core 134 library shape arrays at the reference state (48 fuel positions, 15 axial bins and the bin below the core, fission fractions per bin and the bin volumes): the power density relative to the fuel mean `F_ij = (f_ij/V_ij) / (Σf/ΣV)`, the fuel temperature rise of each bin `ΔT_ij ∝ F_ij^(1/(1+n))` scaled so that its **volume mean equals ΔT̄**, and the reactivity-effective rise `ΔT_eff = Σ w_ij ΔT_ij / Σ w_ij`, with weights `w_ij = F_ij^p V_ij`. The factor `κ = ΔT_eff/ΔT̄`.

- Primary: p = 2 (the worth of a fuel element goes as the flux squared) and n = 0.22 (the fitted exponent of the burned libraries). Sensitivities: p = 1 and p = 3; n = 0; the radial part alone (element-averaged, axial profile uniform) and the axial part alone (the core-averaged axial profile, radial uniform).
- **C1 metric:** κ. **Large** if κ ≥ 1.35 (it alone removes most of the step 7 shortfall: the implied conversion of 1.04 against 1.525 is a factor of 1.46); **partial** if 1.05 ≤ κ < 1.35; **none** if κ < 1.05.
- This calculation is a proxy for the transport effect (it assumes the reactivity weights are a power of the local power density, and uniform in energy); a transport run with the element temperatures of the model (per-element fuel materials) would be the proper test and is not part of this protocol.

## Part W: the what-if

The library's fuel table with the temperatures of Table IX is evaluated as in the sixth protocol (TB with γ_B, linear water warming; the A-ring and the other two profiles as sensitivities) with: (W0) the library as it is; (W1) the mean fuel rise multiplied by κ (part C primary); (W2) the reactivity loss of the fuel table multiplied by `Δρ_VII.1/Δρ_VIII.0` at the table's temperatures (part D2, if run; otherwise not computed); (W3) both. Reported: the labels at steps 1–7 and the fraction of the step 7 shortfall removed. These are what-ifs, not library changes.

## Decision process

1. **P1 constant and P2 smooth:** OpenMC's temperature treatment is not responsible for the shortfall; the first table interval's resolution was already excluded (seventh protocol). **P1 varying, or a treatment effect at an untabulated temperature:** a treatment artefact exists; record its size and sign; a corrected library needs its own protocol.
2. **D1 explains or partly explains:** the evaluation of the ZrH and nuclide data is a lever of the stated size. It is **not adopted** (a data library is a library decision with its own protocol, and the older evaluation was not preferred on evidence about this fuel); the library notes would state the sensitivity. **D1 not the explanation, or part D not run:** recorded as such.
3. **C1 large or partial:** the uniform fuel temperature of the library is a known limit of the model; the fraction of the shortfall it removes is reported with W1. A transport test with per-element temperatures is the next protocol if C1 is partial or large.
4. **W3 good or plausible:** the weak feedback is explained by the data evaluation and the temperature distribution together, with the sizes found. **W3 fails, or not computed:** a residual remains, reported as a fraction of the step 7 shortfall; what is left is the measurement's side (the conversion, the water warming) or model assumptions not tested (the temperature of the zirconium rod and the cladding, which the model keeps at 294 K, the reflector).
5. **In every case** nothing in any library changes and their status stays `experimental`.
6. **Not tried after seeing the results:** other evaluations, treatments, weights, exponents or particle counts than those listed, a fit of anything.

## Implementation (to be written after this protocol)

`--method` and `--tolerance` in `pipeline/openmc/pin_cell.py`; the runs of P1 and P2 (and D if approved) written to `pipeline/openmc/results/core134_pincell_*.json`; `validation/m7_core134_data.py` for the analysis (P, D) and the calculation of part C and the what-if W (reusing `m7_fuel_coefficient`), with a synthetic test (planted pin-cell reactivities, planted shape arrays with a known κ); report `validation/m7_core134_data_report.json`; results note `docs/validation/m7-core134-data-results.md`. The runs and the script are done once.

## Limits, repeated

The pin cell is an equivalent unit cell, not the core; the reference (Serpent, ENDF/B-VII.0) differs from OpenMC in code and data and in details of the cell; the statistical error of a pin-cell run is about 10 pcm, so ratios of deltas at 400 K carry about 3 %; part C is a proxy calculation of the transport effect and assumes the power peaking of the model's own shape arrays, which carry their own tally uncertainty; part D depends on a download that may not be approved; a "partial" label only says how much of the shortfall a candidate could remove, not that it does.
