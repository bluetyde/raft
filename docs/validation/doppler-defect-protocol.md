# The Doppler-defect benchmark: OpenMC with ENDF/B-VIII.0 against Mosteller's reference results (thirteenth protocol, written before any run of it, 2026-10-10)

Method as in M7 and M8: the cases, the metrics, the bands and the decision are fixed here before anything is run; every case is run once; every metric is reported; nothing is refitted afterwards; errata are not fixes. This protocol tests **the transport tool chain** (OpenMC 0.15.3, ENDF/B-VIII.0 HDF5 library, as in every other protocol of this repository), not any library of RAFT. It exists because two results of the repository are not explained: the isothermal temperature coefficient of the BEAVRS model is 1.6 to 2.0 pcm/°F too negative (`m8-beavrs-hzp-results.md`), and OpenMC's fuel temperature response in a TRIGA pin cell is 15 to 18 % weaker than a Serpent reference (`m2-pin-cell.md`, `m7-core134-data-results.md`). A simple, well-documented pin-cell benchmark of the fuel Doppler response can say whether OpenMC's fuel Doppler treatment is a candidate for either.

## The benchmark and its data

R. D. Mosteller, *Computational Benchmarks for the Doppler Reactivity Defect*, LA-UR-06-2968 (April 2006), and the results of R. D. Mosteller, *ENDF/B-V, ENDF/B-VI, and ENDF/B-VII.0 Results for the Doppler-Defect Benchmark*, LA-UR-07-0922, M&C+SNA 2007 (Monterey), marked "approved for public release; distribution is unlimited". The reference results are Tables II to IV of the second paper (MCNP5, 550 generations of 10 000 neutrons, 50 inactive, so 5 million active histories per k; cross sections processed from each ENDF/B release with NJOY, and from the 300 K data to 600 K and 900 K with the DOPPLER code).

- **The cell:** an infinite array of identical pin cells (reflective box, 20 cm high in the model, reflective top and bottom), fuel, gap (void), Zircaloy cladding, water with 1400 ppm boron. **HZP:** everything at 600 K. **HFP:** the fuel at 900 K, everything else at 600 K; the fuel, cladding and pitch dimensions and the fuel density are those of the hot state (they are in the generator below).
- **The defect:** Δρ = (k_HFP − k_HZP)/(k_HFP · k_HZP); the Doppler coefficient DC = Δρ/ΔT with ΔT = 300 K, in pcm/K (Δρ × 10⁵ / 300).
- **Three subsets:** UO2 (0.711, 1.6, 2.4, 3.1, 3.9, 4.5, 5.0 wt %), reactor-recycle MOX (1, 2, 4, 6, 8 wt % PuO2; Pu isotopics 45.0/30.0/15.0/10.0 at % for 239 to 242), weapons-grade MOX (1, 2, 4, 6 wt %; 93.6/5.9/0.4/0.1 at %). Sixteen pin-cell pairs, **32 cases**.
- **The input generator:** `doppler-defect/make_inputs.py` of `mit-crpg/benchmarks` (MIT licence, Copyright Paul Romano and other contributors), read on 2026-10-10. It holds the dimensions at 300, 600 and 900 K, the densities of each nuclide by subset, enrichment and temperature, the water composition, the Zircaloy density, and writes the XML for OpenMC (an old call style, `ZCylinder(R=...)`, and the author's cross-section path). It is **not copied**: the data are transcribed into `pipeline/openmc/data/mosteller_doppler.json` with the MIT notice beside it, as was done for BEAVRS, and the model is built with the current API.

### Reference values (ENDF/B-VII.0 column, from Tables II to IV; transcribed from an OCR of the paper; all 16 rows were checked on 2026-10-10 by recomputing the Doppler coefficient from the two k values, and agree with the tabulated value to 0.005 pcm/K or better)

| Subset | Content | k_HFP (900 K) | k_HZP (600 K) | DC (pcm/K) |
|---|---|---|---|---|
| UO2 | 0.711 | 0.66108 ± 0.00018 | 0.66661 ± 0.00019 | −4.18 ± 0.20 |
| UO2 | 1.6 | 0.95411 ± 0.00026 | 0.96176 ± 0.00027 | −2.78 ± 0.14 |
| UO2 | 2.4 | 1.09077 ± 0.00028 | 1.09955 ± 0.00027 | −2.44 ± 0.11 |
| UO2 | 3.1 | 1.16794 ± 0.00028 | 1.17741 ± 0.00029 | −2.30 ± 0.10 |
| UO2 | 3.9 | 1.23048 ± 0.00029 | 1.24054 ± 0.00032 | −2.20 ± 0.09 |
| UO2 | 4.5 | 1.26598 ± 0.00029 | 1.27621 ± 0.00028 | −2.11 ± 0.08 |
| UO2 | 5.0 | 1.28959 ± 0.00031 | 1.30027 ± 0.00029 | −2.12 ± 0.08 |
| Reactor MOX | 1.0 | 0.93451 ± 0.00027 | 0.94448 ± 0.00028 | −3.77 ± 0.15 |
| Reactor MOX | 2.0 | 1.00974 ± 0.00029 | 1.02106 ± 0.00032 | −3.66 ± 0.14 |
| Reactor MOX | 4.0 | 1.06468 ± 0.00033 | 1.07643 ± 0.00032 | −3.42 ± 0.13 |
| Reactor MOX | 6.0 | 1.09385 ± 0.00032 | 1.10568 ± 0.00032 | −3.26 ± 0.12 |
| Reactor MOX | 8.0 | 1.11694 ± 0.00032 | 1.12880 ± 0.00031 | −3.14 ± 0.12 |
| Weapons MOX | 1.0 | 1.08002 ± 0.00027 | 1.09000 ± 0.00027 | −2.83 ± 0.11 |
| Weapons MOX | 2.0 | 1.17055 ± 0.00029 | 1.18180 ± 0.00029 | −2.71 ± 0.10 |
| Weapons MOX | 4.0 | 1.23823 ± 0.00030 | 1.25067 ± 0.00029 | −2.68 ± 0.09 |
| Weapons MOX | 6.0 | 1.27495 ± 0.00030 | 1.28722 ± 0.00031 | −2.49 ± 0.09 |

The ENDF/B-V and ENDF/B-VI Doppler coefficients (same cases, same method; for the spread of the reference across data libraries): UO2 V: −4.07 ± 0.20, −2.82 ± 0.13, −2.37 ± 0.10, −2.25 ± 0.09, −2.19 ± 0.09, −2.07 ± 0.08, −1.99 ± 0.08; UO2 VI: −4.16 ± 0.21, −2.92 ± 0.13, −2.41 ± 0.11, −2.30 ± 0.10, −2.12 ± 0.09, −2.12 ± 0.08, −2.04 ± 0.08; reactor MOX V: −3.83, −3.70, −3.43, −3.31, −3.25 (± 0.14, 0.14, 0.12, 0.12, 0.11); VI: −3.90, −3.76, −3.49, −3.37, −3.23 (± 0.15, 0.14, 0.13, 0.12, 0.12); weapons MOX V: −2.74, −2.57, −2.52, −2.57 (± 0.11, 0.10, 0.09, 0.08); VI: −2.87, −2.68, −2.63, −2.46 (± 0.11, 0.10, 0.09, 0.09). The paper finds the three libraries within one standard deviation of each other at nearly every case, and states that **an uncertainty of 10 % in the Doppler coefficient has been considered acceptable in practical applications**.

## Disclosure: what was seen before writing

This protocol is **not blind**.

- **Seen:** all the reference values above (the whole paper); the generator's data and structure; that every nuclide of the cases (O16, U234, U235, U238, Pu239 to Pu242, H1, B10, B11, Zr90 to Zr96) has data at exactly 600 K and 900 K in the ENDF/B-VIII.0 HDF5 library on this machine, and that the thermal scattering library `c_H_in_H2O` has a 600 K set (checked on 2026-10-10, no transport run); the BEAVRS sweep's fuel temperature table, in which the fuel-only reactivity change is about −3.2 pcm/K below 566 K and −2.6 pcm/K above it for the BEAVRS fuel mix.
- **Not seen:** any OpenMC result for these cases (no k of any of the 32 cases, at any settings); any published OpenMC or other ENDF/B-VIII.0 result for this benchmark was not looked up.
- **Prediction (written before the run):** the Doppler coefficients of the UO2 cases agree with the ENDF/B-VII.0 column within a few percent (a z within ±2 for most cases). The two earlier unexplained results are on other systems (a full core with moderator density change; a ZrH pin cell against Serpent), and I expect this benchmark to show that OpenMC's UO2 fuel Doppler response is not the cause of the BEAVRS coefficient error. If the run shows a systematic deficit (a UO2 or MOX coefficient less negative than the reference by more than 10 %), it is reported as such and the decision below applies.

## The question

Does OpenMC 0.15.3 with the ENDF/B-VIII.0 HDF5 library reproduce the Doppler coefficients of Mosteller's 16 pin cells (UO2, reactor-recycle MOX and weapons-grade MOX) within the benchmark's own statistics and the 10 % that the benchmark's author calls acceptable?

## The cases (fixed now)

Model: the benchmark's pin cell, built from the transcribed data of the generator, at its exact dimensions and densities for each of 600 K (HZP) and 900 K (HFP). Water and Zircaloy are always at 600 K; the fuel material at 600 K or 900 K (the case's temperature). The gap is void. Boundaries reflective on all six faces, the box 20 cm high.

- **Nuclear data:** ENDF/B-VIII.0 HDF5 (`/root/nuclear_data/endfb-viii.0-hdf5/cross_sections.xml`), the S(α,β) `c_H_in_H2O` for the water. **Temperature method: `nearest` with a tolerance of 10 K**, so that every nuclide uses its tabulated 600 K or 900 K set and no interpolation of cross sections acts (this is a difference from the BEAVRS model, which interpolates; it is deliberate: the benchmark compares two exact temperatures). If a nuclide of a case had no set within 10 K the run would stop and report it (none is expected).
- **Resonance scattering:** off (the OpenMC default), as in the MCNP5 reference, which used free-gas scattering without a resonance-scattering correction.
- **Settings:** 20 000 particles per batch, 600 batches, the first 100 inactive (10 million active histories per case, twice the reference); a uniform source in the fuel; the seed is 1 for the HZP case and 2 for the HFP case of each pair (so that the two k values of a pair are statistically independent). Each case is run once. A case that crashes or is stopped is run again with the same settings (not counted as a second run); no other rerun is allowed.
- **Convergence check (every case):** the mean k of batches 101 to 350 and of 351 to 600 agree within 2 standard errors of their difference (as in the eleventh and twelfth protocols; batch values taken as independent, so this is a drift check, not a variance estimate). A case that fails is labelled "unconverged", kept in the tables and excluded from the decision items it enters; it is not rerun with more inactive batches under this protocol.

## Quantities

Δρ = 1/k_HZP − 1/k_HFP (the benchmark's definition, the same expression), DC = Δρ × 10⁵ / 300 in pcm/K. σ_DC from the two k errors by partial derivatives (the two cases are independent): σ_Δρ² = (σ_HZP/k_HZP²)² + (σ_HFP/k_HFP²)². **z** = (DC_model − DC_ref)/√(σ_ref² + σ_model²), with the ENDF/B-VII.0 column as the reference. Relative difference = (DC_model − DC_ref)/|DC_ref|.

## Metrics and bands (fixed now)

Labels by |z|: **good** ≤ 1, **plausible** ≤ 2, **fails** > 2 (as before). A second yardstick, the benchmark's own: a case is **within 10 %** if |relative difference| ≤ 10 %.

- **A: the Doppler coefficient**, 16 metrics (z, label, relative difference, within 10 %), and the spread of the three reference libraries at the case (max minus min of V, VI, VII.0) for context; no label for the spread.
- **B: k_HZP**, 16 differences in pcm against the ENDF/B-VII.0 value (reported, not labelled): a check that the transcription and the model are right (a large, regular offset would point to a model error rather than to the nuclear data; ENDF/B-VIII.0 against VII.0 is expected to differ by tens to a few hundred pcm).
- **C: families.** For each subset, the mean z and the mean relative difference with their spread-based standard errors (sample standard deviation over √n); a **systematic deficit** is declared for a subset if the mean relative difference is positive (the model coefficient less negative than the reference) with |mean| > 2 standard errors and at least three quarters of the cases of the same sign; a **systematic excess** if the same holds with the model more negative.
- **D: convergence**, the check above for every case, and the list of cases that failed it.

## Decision process

1. **A good or plausible for at least 12 of the 16 cases, and no systematic deficit or excess in any subset:** OpenMC with ENDF/B-VIII.0 reproduces the benchmark's fuel Doppler response at the pin-cell level. Then the fuel Doppler treatment of the transport tool chain is **not** a candidate cause of the unexplained BEAVRS coefficient (a Doppler coefficient error of the size of the benchmark's own 10 % of about 2.4 pcm/K is 0.24 pcm/K, which is 0.13 pcm/°F against an unexplained 1.6 to 2.0 pcm/°F), and the next suspects for that result stay those named in `m8-beavrs-hzp-results.md` (the moderator density term, the secant, the expansion that the model fixes).
2. **A systematic deficit in a subset:** the size (a percentage of the coefficient) is recorded, with the subset it holds in. A UO2 deficit is a candidate partial cause of the TRIGA pin-cell result (the TRIGA fuel is ZrH-U, not UO2, so it is a candidate only, not an explanation) and the note says what a test of that would need. It does not change any library: nothing is refitted, and the libraries stay `experimental`.
3. **A systematic excess:** recorded in the same way (the BEAVRS coefficient is too negative; an excess in UO2 would be a candidate partial cause).
4. **A mixed outcome** (fewer than 12 good or plausible without a systematic pattern): the cases that fail are named with sign and size, and the note says what was and was not tested; no cause is claimed.
5. **Cases unconverged or missing:** the metrics that need them are "not computed" and enter no decision item.
6. Under all outcomes this protocol changes what is known about the tool chain, not what any library claims.

## Implementation (to be written after this protocol)

1. `pipeline/openmc/data/mosteller_doppler.json` (the generator's data) with the MIT notice of `mit-crpg/benchmarks`, and `validation/data/mosteller-doppler/reference.json` (the three reference columns above), with a test that every Doppler coefficient recomputes from its two k values to 0.02 pcm/K and that the cases are exactly the 32 of this protocol.
2. `pipeline/openmc/doppler_run.py` (WSL; one process per case; refuses a case already in the results file; records the OpenMC version, the seed, the settings, wall and CPU times and the machine load) and `validation/doppler_defect.py` (the analysis above, a loader that refuses a result file that does not hold exactly the 32 cases), with a test on planted k values (known coefficients; the analysis must recover them, name a failed case, declare a planted subset deficit) and deliberate breaks of the script, each caught.
3. The run: about 32 cases of 10 million histories, an estimated 1 to 2 hours on this machine when it is not shared; the results note `doppler-defect-results.md`.

## Erratum (2026-10-17, after the run and a Codex review; nothing in the run or its analysis changed)

The implementation list (item 2) says the loader refuses a result file that does not hold exactly the 32 cases; the decision rules say a missing case is reported as not computed. These conflict. What was implemented, and what the results note relies on, is: the loader refuses a row that is not one of the 32 cases, that appears twice, or whose settings, seed, fuel temperature, subset, content, OpenMC version or cross-section library differ from the protocol's; a case that is absent is reported as not computed. The run delivered 32 rows, so the difference did not arise. The runner also refuses a repeated `--case` in one call (a once-only rule that a repeat could have bypassed).

## Limits, repeated

The reference is itself a Monte Carlo result (MCNP5, ENDF/B-VII.0, cross sections made with NJOY and the DOPPLER code, without resonance scattering), not an experiment: agreement shows consistency between two tool chains and two evaluations, not agreement with a measurement. A pin cell with reflective boundaries says nothing about the leakage, the water density term, the spatial self-shielding of an assembly or the thermal expansion of a core. The ENDF/B-VIII.0 data differ from VII.0 (the resonance parameters of U-238 among them), so a difference of a few percent is not by itself a defect of OpenMC. Boron is at 1400 ppm in the reference and in these cases, not at the BEAVRS 975 ppm.
