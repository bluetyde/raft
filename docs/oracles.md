# Oracles: what RAFT's results are checked against

An **oracle** is an expected value that does not come from the code it checks. This page lists every one RAFT has, what kind it is, where its number comes from, how tight it is and which test or protocol holds it. If a result is right, it is right against one of these; for what has none, see the end.

## The rules every oracle follows

- **The expected value never comes from the code under test.** It is a measurement or a published number, a formula written out again in the test, an independent implementation (another language, another method), or a case with a known answer built into the input.
- **Bands and tolerances are fixed before any run.** Each comparison with a measurement is a dated protocol written first (`docs/validation/*-protocol.md`), run once, and reported with its failures; errata are not refits. In the SEED entries the tolerance is part of the entry's hash, so changing it needs a new entry version made by a person.
- **A check is tested by breaking the code once.** The analysis scripts and the exporter were each run against deliberate breaks (a sign, a window, a mapping) and a test that let a break through was extended; the notes record the runs.
- **Say what it does not prove.** Agreement between two engines does not prove the physics; agreement with a benchmark does not prove a library.

## The kinds, from strongest to weakest evidence

| Kind | Where the number comes from | What it can catch |
|---|---|---|
| **Measurement** | a measured value with its stated uncertainty (a reactor, a benchmark's physics tests) | a model that is wrong in the same way as the code |
| **Published calculation** | another tool chain's published result for a fixed case (Serpent, MCNP5) | a transport or data-treatment error |
| **Independent implementation** | the same quantity from a different language or method | a bug in one engine or validator |
| **Closed form** | a formula derived by hand and evaluated in the test | a bug in the code that implements the same physics |
| **Planted answer** | an input built so that the right answer is known (a separable model with chosen worths) | a mapping, sign or unit error in an analysis or exporter |
| **Refusal** | a case with one fault that must be refused with a named code | a check that does not fire |

## The catalogue

### Measurements and published calculations (the validation protocols)

Bands are the measurement's own uncertainties (z within 1 is good, within 2 plausible, beyond fails) unless the protocol says otherwise. Every outcome is in the results note; none of these has made a library `validated`: all libraries are `experimental`.

| Protocol | Reference | Source | Held by |
|---|---|---|---|
| M1 C1 and run 3 (before the numbered series) | JSI TRIGA pulse database (peak power, energy, period of measured pulses) | trigapulse.ijs.si (Švajger and Snoj); **not distributed with this repository** (see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)) | `validation/c1_comparison.py`, `m1_run3.py`, `pulse_*.py`, `docs/validation/m1-c1-*`, `m1-run3-protocol.md` |
| M2 pin cell | Serpent 2.1.27, ENDF/B-VII.0, full model of core 133: temperature *differences* of the fuel reactivity | Švajger 2024 Table 2 | `docs/validation/m2-pin-cell.md`, `pipeline/openmc/pin_cell_report.json`; result: OpenMC is 15 to 18 % weaker, unexplained |
| M2 burnup, rod curves | the measured critical states and rod worths of cores 242 and 246 | JSI core data (cited in `pipeline/openmc/data/`) | `docs/validation/m2-burnup-*`, `validation/m2_burnup.py`, `m2_rod_curves.py` |
| 1 to 4 (M7: power ascension, heat transfer, hot element, hot element 2) | the IAEA/JSI steady-state power ascension (power defect, fuel temperature, regulating rod) and the hot-element thermocouple | IAEA research reactor database, Slovenian protocols, "typical real data" of 2013; **not distributed** | `docs/validation/m7-power-ascension-*`, `m7-heat-transfer-*`, `m7-hot-element*-*`; `validation/m7_power_ascension.py`, `m7_heat_transfer.py`, `m7_hot_element*.py` |
| 5 to 10 (M7 core 134: fuel coefficient, library, feedback, conversion, data, transport) | the 1994 benchmark of TRIGA core 134: rod worths, fuel element worths, thermocouple readings, power steps | I. Mele, M. Ravnik, A. Trkov, *Nucl. Technol.* 105 (1994) 37-51; the transcribed tables are **not distributed** | `docs/validation/m7-core134-*`, `m7-fuel-coefficient-*`, `core134-status.md`; `validation/m7_fuel_coefficient.py`, `m7_core134_*.py` |
| 11 (M8 transport) | BEAVRS cycle 1 hot zero power: critical boron at five rod states (σ 22 ppm), seven sequential bank worths, isothermal temperature coefficient at two states (σ 0.54 pcm/°F) | BEAVRS specification rev 3.0.2 Tables 21 and 22, uncertainty report Tables 1, 4, 6 (MIT, MIT licence) | `docs/validation/m8-beavrs-hzp-*`, `validation/m8_beavrs_hzp.py`; result: criticality good, temperature coefficient fails |
| 12 (M8 library) | the same measured values against the library `pwr-beavrs-hzp-openmc` | as 11 | `docs/validation/m8-beavrs-library-*`, `validation/m8_beavrs_library.py`; result: good with all rods out and one bank in, fails with more banks in |
| 13 (Doppler defect) | Mosteller's 16 pin-cell pairs, Doppler coefficient in pcm/K, MCNP5 with ENDF/B-V, VI and VII.0 | R. D. Mosteller, LA-UR-07-0922, Tables II to IV (public release); the benchmark's inputs from `mit-crpg/benchmarks` | `docs/validation/doppler-defect-protocol.md`, `validation/data/mosteller-doppler/reference.json`; run once 2026-10-11, results in `docs/validation/doppler-defect-results.md` (15 of 15 computed cases good or plausible; one case unconverged) |

Library measurements that fed the libraries themselves (the fuel and cladding data, the heat capacity, the delayed-neutron decay constants) are cited in each library manifest (`provenance.sources`); a value with source `assumed` has no oracle and is labelled so in the library.

### Independent implementations

| Oracle | Method | Held by |
|---|---|---|
| Python reference engine against the TypeScript engine | the same point kinetics, thermal and feedback equations in two languages with two integrators in places (the TypeScript engine uses its own numerics, `web/src/sim/numerics.ts`) | the **golden vectors** `schema/engine-vectors/*.json` (nine: period trip, pulse, rejections, rod withdrawal, scram, source level, two heat-law vectors, boron dilution); `physics_ref/tests/test_vectors.py`, `web/src/sim/vectors.test.ts` |
| Python validators against the TypeScript validators | the library format rules (`docs/library-format.md`) checked twice | `web/src/library/parity.test.ts` over every fixture |
| The reference engine against SciPy's Radau | the Nordheim-Fuchs pulse integrated by a stiff solver | `physics_ref/tests/test_engine.py::test_pulse_matches_scipy_radau`; `test_ros3p.py` for the second integrator |
| SEED oracle entries | 22 entries (18 good: final power, fuel temperature and energy of six of the vectors; 4 bad-input) generated from the committed vectors, checked by the SEED harness's own adapter | `oracles/seed/` (README there); the adapter and generator live in the SEED repository |
| Transport and library agree where one bank has moved | the library's summed tables against the transport cases they were built from | `pipeline/openmc/results/beavrs_export_report.json`, `m8-beavrs-library-results.md` (a self-check of the exporter, not independent: it shows where the format fails) |

### Closed forms

| Oracle | Formula | Held by |
|---|---|---|
| Source equilibrium | P = −S·Λ/ρ | `test_engine.py::test_source_equilibrium_matches_formula_and_holds` |
| Stable period | the positive root of the inhour equation | `test_stable_period_matches_inhour` (5e-3); `web/src/sim/engine.test.ts` |
| Prompt jump | P₁ = P₀ β/(β − ρ) | `test_prompt_jump` |
| Pulse, delayed-neutron return | the Nordheim-Fuchs peak and energy, and the raise of the peak by delayed return | `test_nordheim_fuchs_pulse`, `test_delayed_return_raises_the_peak` |
| Energy balance, xenon peak after shutdown, equilibrium poisons | written out in each test | `test_energy_balance`, `test_xenon_peak_after_shutdown`, `test_equilibrium_poisons_have_zero_derivative` |
| Soluble boron ramp | the concentration moves at exactly the rate and stops at the target; no drift from per-step rounding | `physics_ref/tests/test_boron.py`, `web/src/sim/boron.test.ts` |
| Doppler definition | Δρ = 1/k_HZP − 1/k_HFP, DC = Δρ/300 K; every row of the reference table recomputes from its k values to 0.005 pcm/K | `validation/tests/test_doppler_defect.py`, `pipeline/tests/test_mosteller_doppler.py` |

### Planted answers

| Oracle | What is planted | Held by |
|---|---|---|
| The BEAVRS library exporter | a separable sweep with chosen bank worths, temperature and boron slopes, on the real core layout (asymmetric on purpose): the exported library must reproduce the planted reactivity to 1e-9 and the planted base shape bin by bin; deliberate breaks (a transposed index, a flipped axis, a sign in the boron table, a bank on the wrong id) must fail | `pipeline/tests/test_export_beavrs.py` |
| The BEAVRS data file | the benchmark's own counts: 193 assemblies, 53 control assemblies by bank (SA 8, B 8, C 8, SB 8, D 5, SD 4, SC 4, SE 4, A 4) and four asymmetric positions that pin the orientation | `pipeline/tests/test_beavrs_core.py` |
| The comparison scripts (protocols 11, 12, 13) | a planted model with known worths, offsets and subset biases: the analysis must recover them, name a failed case, mark an unconverged or missing case "not computed", and refuse a file that is not the protocol's | `validation/tests/test_m8_beavrs_hzp.py`, `test_m8_beavrs_library.py`, `test_doppler_defect.py`; the earlier M7 scripts likewise |
| Case plans and runners | the case lists equal the protocols' (counts, seeds, settings); a clone that is not at the protocol's BEAVRS commit is refused | `pipeline/tests/test_sweep_plan.py`, `test_beavrs_head.py`, `test_mosteller_doppler.py` |
| The dilution lesson | five scripted operators (careful, reckless, idle, stop just above critical, slow rise); the first three were planned with their outcomes beforehand, the last two were added after a Codex review found the goals too weak | `web/src/runtime/dilution-lesson.test.ts` |

### Refusals

| Oracle | Held by |
|---|---|
| 42 invalid library fixtures, each with the error code the validators must give (both validators) | `schema/vectors/invalid/*/expected.json`; `pipeline/tests/test_library.py`, `web/src/library/validate.test.ts`, `parity.test.ts` |
| The `rejections` vector: commands the engine must refuse, with the code | `schema/engine-vectors/rejections.json` |
| Four bad-input SEED entries (future schema version, no equilibrium, zero step, zero outer step) | `oracles/seed/entries/raft-bad-*.json` |
| Scenario files, session files and commands against their schemas | `web/src/runtime/scenario.test.ts`, `schema/*.schema.json`, `pipeline/tests/test_contracts.py` |

## What has no oracle

- **Spatial power shapes and the 3D view.** The shapes are the transport model's fission tallies; nothing measured is compared with them. The separable-shape error is only checked against the transport cases the library was made from.
- **Temperature feedback in the PWR library and in the TRIGA libraries.** The comparisons that exist fail (BEAVRS: 1.6 to 2.0 pcm/°F too negative in the transport model, and the library does not follow the rods; TRIGA: the power defect is 0.45 to 0.47 of the measured one; the pin-cell deficit is unexplained). Protocol 13 tested only the fuel Doppler part, in a pin cell, against another code: 15 of 15 computed cases are within 10 %, with a +5.8 % UO2 deficit, so fuel Doppler does not explain the BEAVRS error (which has the opposite sign); the TRIGA 15 to 18 % (ZrH fuel) is not covered by it.
- **Combined rod worth** beyond the benchmark insertion order, and any rod combination not in a sweep case: the library sums single-bank tables and is measured to fail with several banks in.
- **Kinetics parameters** (β, Λ, the decay constants) against a measurement; they are transport results (OpenMC's IFP) and cited data.
- **Instrument noise, faults, scenario scoring, the AI operator.** These are checked for behaviour (determinism, refusal, a fixed-rule baseline comparison in `docs/validation/ai-operator-baseline.md`), not against a physical reference; the baseline comparison is not an oracle.
- **Anything with source `assumed`** in a library: the plant (trip setpoints, rod speed, scram profile, instruments, heat transfer of the PWR, the neutron source).
- **The data not distributed** (the pulse database, the steady power numbers, the core 134 tables): the protocols that use them are documented and their results are in `docs/validation/`, but a fresh clone skips their tests (29 tests) and cannot repeat them.
