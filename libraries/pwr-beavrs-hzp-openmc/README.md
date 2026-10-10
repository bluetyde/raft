# pwr-beavrs-hzp-openmc

A PWR at **hot zero power** (566.5 K, 15.5 MPa water, no decay heat), built with OpenMC 0.15.3 and ENDF/B-VIII.0 from the BEAVRS benchmark cycle 1 model (MIT, `mit-crpg/BEAVRS`). Status `experimental`. Exporter: `python -m pipeline.library.export_beavrs`; sweep: `pipeline/openmc/beavrs_sweep.py` (45 cases); plan: `docs/m8-beavrs-exporter-plan.md`; comparison with the measured hot zero power data: `docs/validation/m8-beavrs-hzp-results.md`.

**Use it for zero-power physics only** (the shipped lesson is approach to criticality by dilution, `web/src/app/scenarios/pwr-beavrs-hzp-dilution.json`), near the benchmark rod configuration (all banks out, bank D at step 213). Soluble boron works there, and the critical concentration is 983 ppm in both engines. With several banks in, the library is not reliable (below). A trip scrams the rods at about 1.7 MW (0.05 % of full power).

## What comes from transport (source `transport`)

- Reactivity tables for nine banks (A, B, C, D, SA to SE; ids are lowercase, `a` to `se`), fuel temperature, coolant temperature (water temperature and density together) and boron; the reference is the benchmark configuration (bank D at step 213 of 228, all others out) at 975 ppm, where the model is at +101 pcm (kept as it is, no calibration).
- Delayed-neutron fractions (sum 700.7 pcm) and the generation time (29.3 µs) from an iterated-fission-probability run.
- Fission power shapes: 193 assemblies by 10 axial bins; one delta array per bank and one for fuel temperature. The shape does not change with coolant temperature or boron.

## What is assumed (source `assumed`)

Rod speed (72 steps/min) and the scram profile (about 2 s); fuel heat capacity; coolant mass (260 t) and heat capacity; fuel to coolant heat transfer (8.5 MW/K); the steam generator (its sink is the reference temperature, so it removes nothing at zero power); poison data; the neutron source (2 W/s); the instrument ranges, lags and noise; the trip set points (109 % of 3411 MW, 1.7 MW on the log channel, a 10 s period); boron range (0 to 2000 ppm) and rate (0.1 ppm/s). The fuel mass (93 t) is computed from the benchmark's pellet size and a density of 10.3 g/cm3. Delayed-group decay constants are the ENDF/B-VIII.0 values for U-235, not Keepin's.

## Known limits

- **Temperature feedback is not validated**: the model's isothermal temperature coefficient is 1.6 to 2.0 pcm/°F too negative against the benchmark measurement.
- **Compared with the measured physics tests** (twelfth protocol, `docs/validation/m8-beavrs-library-results.md`): critical boron is good with all rods out (+8 ppm) and with D in (+22 ppm), and fails with more banks in (+50, +92 and +157 ppm with C and D, A to D, and seven banks in); five of the seven sequential bank worths fail (the total is 4075 pcm against 6042 measured); the temperature coefficient fails at both states (−3.6 pcm/°F against −1.75 and −8.01), and is the same whatever the rods.
- **Rod banks are not additive.** The tables are summed as if each bank acted alone. Against the transport runs with several banks in, the sum is not negative enough by 420 pcm (banks C and D in), 1106 pcm (A to D in) and 1953 pcm (seven banks in). With boron changed too (A to D in at 686 ppm, seven banks in at 508 ppm) the library is 1203 and 2243 pcm too high where transport is near critical (-29 and -188 pcm), so its critical boron would be about 95 and 180 ppm too high. No joint state met the acceptance limit (100 pcm and one mean bin), so `domain.jointChecked` is empty and every state with more than one bank away from the reference is `unvalidated`. In the same states the summed shapes also go negative in 6 (four banks) and 19 (seven banks) bins. `pipeline/openmc/results/beavrs_export_report.json` has the figures for every case.
- Xenon worth is zero (not computed); there is no decay heat and no pressure; the library has no pulse mode.
- The 3D model shows the vessel barrel, 193 assemblies and 53 absorber assemblies as boxes and cylinders, not the pins.

BEAVRS notice: `pipeline/openmc/data/BEAVRS-LICENSE`.
