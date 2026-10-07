# M8 BEAVRS hot zero power: the transport model against the cycle 1 physics tests (eleventh protocol, written before any run of it, 2026-10-07)

This is M8 step 1 (`docs/m8-second-reactor-plan.md`). It fixes what is computed with the BEAVRS full-core OpenMC model and how the result is read, **before** the cases are run. It tests the transport model, which the library of M8 step 3 will inherit; the library's own comparison with the measurements is a later protocol. Method as in M7: every case is run once, every metric is reported, nothing is refitted afterwards, the library stays `experimental`.

## The data

BEAVRS specification rev 3.0.2 (Tables 21 and 22) and the uncertainty report (`beavrs_uq_report.pdf`, Tables 1, 4 and 6). All cycle 1, hot zero power, inlet 560 °F (566.483 K), 975 ppm at the benchmark configuration (banks A, B, C at step 228, bank D at step 213). In the model, a bank "in" is step 0.

| Quantity | Value | Standard deviation (benchmark's UQ report) |
|---|---|---|
| Critical boron, ARO | 975 ppm | 22 ppm |
| D in | 902 ppm | 22 ppm |
| C, D in | 810 ppm | 22 ppm |
| A, B, C, D in | 686 ppm | 22 ppm |
| A, B, C, D, SE, SD, SC in | 508 ppm | 22 ppm |
| Bank worth D (ARO to D in) | 788 pcm | 29 pcm |
| C (with D in) | 1203 pcm | 32 pcm |
| B (with D, C in) | 1171 pcm | 31 pcm |
| A (with D, C, B in) | 548 pcm | 26 pcm |
| SE (with D, C, B, A in) | 461 pcm | 25 pcm |
| SD (with D, C, B, A, SE in) | 772 pcm | 28 pcm |
| SC (with D, C, B, A, SE, SD in) | 1099 pcm | 31 pcm |
| Isothermal temperature coefficient, ARO | −1.75 pcm/°F | 0.54 pcm/°F |
| ITC, C and D in | −8.01 pcm/°F | 0.54 pcm/°F |

The benchmark's 22 ppm for the critical boron and the 5 % scale for the rod worths are its own estimates (the UQ report notes the common licensing criterion for model predictions is 50 ppm). The errors of the seven worths are treated as independent here; the report derives them from one trend line, so they are probably correlated, and the total's uncertainty below is then too small. The ITC at D in (−2.75 pcm/°F) is not computed (cost; disclosed). Cycle 2 is not used.

## Disclosure: what was seen before writing

This protocol is **not blind**.

- The step 0 runs (`m8-step0-feasibility.md`): the model as generated (ARO configuration, bank D at 213, 975 ppm, 566.483 K, ENDF/B-VIII.0, interpolation of the temperature) gives k = 1.00020 ± 0.00150 (400 000 histories) and **1.00075 ± 0.00045** (7.2 million histories, 40 inactive batches), that is +75 ± 45 pcm from critical at the measured 975 ppm.
- All the measured values of the table above, which were read from the specification and the UQ report to write this protocol.
- **Not seen:** any other BEAVRS case (no bank in, no other boron, no other temperature), the model's boron worth, its bank worths, its ITC, the entropy or the source convergence of any run, and any published OpenMC or other-code result for BEAVRS cycle 1 HZP (none was looked up).

## The question

Does the OpenMC model of BEAVRS, as published and unchanged, reproduce the measured critical boron concentrations, the bank worths and the isothermal temperature coefficients of the cycle 1 hot zero power tests, within the benchmark's stated uncertainties?

## The cases (fixed now)

The model is `models/openmc/make_beavrs.py` of `mit-crpg/BEAVRS` at head `1ccae04`, 3D, not symmetric, run with `openmc-vr` (OpenMC 0.15.3, ENDF/B-VIII.0, temperature method interpolation with tolerance 100 K as in the model). Only these are changed: bank positions (`--rcca-insertion`), the boron concentration, and, for the ITC cases, the material temperatures and the water density.

**Banks, cumulative insertion** (state: banks at step 0; the rest at the benchmark configuration):

| State | Banks in |
|---|---|
| S0 | none (benchmark configuration, D at 213) |
| S1 | D |
| S2 | D, C |
| S3 | D, C, B |
| S4 | D, C, B, A |
| S5 | D, C, B, A, SE |
| S6 | D, C, B, A, SE, SD |
| S7 | D, C, B, A, SE, SD, SC |

**Series W (bank worths):** S0 to S7 at 975 ppm, 566.483 K. (8 cases)
**Series B (critical boron):** S1 at 902, S2 at 810, S4 at 686, S7 at 508 ppm, 566.483 K; S0 at 975 ppm is case W0. (4 cases)
**Series K (the model's boron worth):** S0 at 875 and 1075 ppm; S7 at 408 and 608 ppm. (4 cases)
**Series T (ITC):** S0 at 975 ppm and S2 at 810 ppm, each at 536.483 K and 596.483 K (±30 K, so the temperature difference is 60 K = 108 °F); every material at the case temperature and the water at the density of 15.5 MPa at that temperature, from IAPWS-IF97 (the source and the three densities are written in the script's output; if no IAPWS source can be installed or typed in with a citation, series T is not run and the ITC metrics are "not computed"). (4 cases)

**Settings.** Series W, B and K: 60 000 particles × 300 batches, 100 inactive (about 12 million active histories; expected error about 28 pcm per case). Series T: 100 000 particles × 800 batches, 100 inactive (70 million active; expected about 12 pcm per case). Default source, default seed of the model. Each case is run once. A case that crashes or is stopped is run again with the same settings (not counted as a second run); no other rerun is allowed.

**Convergence check (applied to every case).** The mean k of batches 101–200 and of batches 201–300 (for series T: 101–400 and 401–800) must agree within 2 standard errors of their difference. A case that fails is labelled "unconverged", kept in the tables, and excluded from the decision items it enters (it is not rerun with more inactive batches under this protocol; that would be a new dated protocol).

## Quantities

ρ = (k − 1)/k, in pcm (1e5 ×), with σ_ρ = σ_k/k² (and σ_k the combined estimator's standard error). Cases are statistically independent.

- **Boron worth** BW (pcm/ppm, positive for a loss of reactivity with boron) = −[ρ(C+100) − ρ(C−100)]/200 from the pair of series K at S0 (the one used for the conversion below); the pair at S7 is a check on how much BW changes with the banks in.
- **Critical boron error** for a state with measured CB_m: err = ρ(S at CB_m)/BW_S0. Positive means the model needs more boron than was measured. Its error σ_err comes from σ_ρ and σ_BW by partial derivatives. For S0, ρ is that of case W0.
- **Bank worth** of bank i = ρ(S_{i−1}) − ρ(S_i) at 975 ppm (series W). The worth of D is S0 to S1. σ is the quadrature of the two σ_ρ. The total of the seven banks is ρ(S0) − ρ(S7).
- **ITC** = [ρ(T+) − ρ(T−)]/108 °F, pcm/°F; σ from the two σ_ρ. (A symmetric difference removes the curvature to first order.)
- **z** for each metric = (model − measured)/√(σ_meas² + σ_model²), with σ_meas from the table and σ_model the metric's own statistical error.

## Metrics and bands (fixed now)

Each metric is reported with its raw difference and its z. Labels, by |z|: **good** ≤ 1; **plausible** ≤ 2; **fails** > 2. The bands are the benchmark's own uncertainties, not tuned.

- **A: critical boron.** Five metrics (S0 to S7 as in the table above); also reported against the 50 ppm criterion cited in the UQ report. Aggregates: the mean of the five errors with its standard error (the errors of different states share the same BW and are not independent, so the standard error is a lower bound); a **systematic offset** is declared if |mean| > 2 standard errors and at least four of the five have the same sign.
- **B: bank worths.** Seven metrics plus the total (σ_meas of the total 77 pcm, from independent errors; see above). Also reported as relative differences.
- **C: ITC.** Two metrics (S0 and S2).
- **D: boron worth check.** BW at S0 against BW at S7, relative difference; reported, not labelled. If the two differ by more than 5 %, the critical boron errors of states with many banks in (S4, S7) are marked as sensitive to the conversion and are also reported with the S7 BW.
- **E: convergence.** The check above for every case, and the list of cases that failed it.

## Decision process

1. **A good or plausible for four or five states, no systematic offset:** the transport model reproduces the critical boron; the library of step 3 is built without a calibration offset.
2. **A systematic offset:** the offset (in pcm, using BW) is recorded as a calibration offset for the library, as for the TRIGA libraries, and shown in the interface; it is not removed from the transport results.
3. **B: a bank that fails** is recorded with its sign and size; the library inherits it with a validity note, and nothing is refitted. If the total fails, the bank worth model is called "not validated for the shutdown banks".
4. **C fails:** the temperature feedback of the library is marked as not validated at HZP (this affects the boron dilution lesson's temperature drift, not the dilution itself).
5. **Cases unconverged or missing:** the metrics that need them are "not computed" and appear as such in the results note; they do not enter any decision item.
6. Under all outcomes the library status stays `experimental` and the next step (2, the format fit check) goes ahead; this protocol's outcome changes only what the library is allowed to claim.

## Implementation (to be written after this protocol)

`validation/m8_beavrs_hzp.py` with a synthetic test: a case driver that writes the run list (with the model commit, the settings and the water densities), a loader that refuses a result file that does not hold exactly these cases, and the analysis above. Cases are run in WSL by a driver script (not by hand), results appended to `pipeline/openmc/results/beavrs_hzp.jsonl` with each case's seed, settings and wall and CPU times, and the machine load noted. Expected time: about 2.5 hours for the 16 standard cases and 3.5 hours for the four long ones on this machine when it is not shared.

## Limits, repeated

The model fixes the geometry at its published dimensions at HZP: the ITC omits thermal expansion of the fuel and structures. The measured data come from the plant's cycle 1 startup with its own tilt and instrument effects; the model has the published instrument tubes. One boron worth (from S0) converts all the critical boron errors. The seven worth errors are treated as independent. The ITC at D in, cycle 2, the flux maps and the boron letdown are not compared here.
