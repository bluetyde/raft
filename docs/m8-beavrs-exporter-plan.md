# M8 step 3, the BEAVRS library exporter: plan (2026-10-08)

Turns the 45-case sweep (`pipeline/openmc/results/beavrs_sweep.jsonl`, committed `21d3d7f`) into a runnable library `libraries/pwr-beavrs-hzp-openmc` that passes both validators and runs in both engines, with the boron capability (`point-kinetics/boron-v1`, engine 0.4.0). Status: built 2026-10-10 (sections 4 and 6 were carried out with the proposed defaults; rod ids are lowercase `a` to `se` because the schema pattern requires it). It follows `pipeline/library/export_openmc.py` (the TRIGA exporter) but is a new file, `pipeline/library/export_beavrs.py`, because the TRIGA one is built around four rods, a base library inherited from `build_triga`, and `core_model` constants.

## 1. What the sweep gives, and where each manifest field comes from

| Manifest field | Source | Method |
|---|---|---|
| `reference` (rods, T, boron, `rho`) | case `REF` | rods at the benchmark configuration (D at 213 of 228 steps, the rest at 228), 566.483 K, 975 ppm; `rho` = (k−1)/k = +101 pcm, kept as the transport result (step 1 found no calibration offset, so `calibration: null`); `xenon` 0 |
| `reactivity.rods[]` (nine banks: A, B, C, D, SA to SE) | cases `R-<bank>-0/76/152`, `R-D-228` | x = steps/228; ρ(x) − ρ_ref; points 0, ⅓, ⅔ and the reference (x = 1, or 0.934 for D, which also has x = 1); monotone fit with the existing `isotonic()` weighted by the statistical error, as for TRIGA; `travelCm` 360.68 (spec: 228 × 1.58193 cm) |
| `reactivity.fuelTemp` | `TF-500/700/900` + `REF` | fuel-only temperature (water unchanged); axis 500, 566.483, 700, 900 K |
| `reactivity.coolantTemp` | `TC-500/540/600/620` + `REF` | moderator temperature and density together (water at 15.5 MPa, IAPWS-IF97); axis 500, 540, 566.483, 600, 620 K; at the reference boron |
| `reactivity.boron` | `B-300/600/1300/1600` + `REF` | axis 300, 600, 975, 1300, 1600 ppm; monotone non-increasing fit; slope about −12.6 pcm/ppm (step 1) |
| `reactivity.xenon`, `poisons` | none (HZP) | flat table at zero, `poisons` values generic and labelled `assumed`; the notes say the library is for zero-power physics |
| `kinetics` | `REF` (IFP) | six β_i from `betaGroups` (sum 700.7 pcm), Λ = 29.3 µs; decay constants: see risk 1; `extSource` assumed so that all banks in at the reference boron sits near 1e-6 W |
| `shapes` | fission mesh tally of every case | 193 elements × 10 axial bins; `base` from `REF`; one `rodDelta` per bank from its `R-*` cases; `tempDelta` from `TF-*`; deltas normalised to sum zero as in the TRIGA exporter; `volumes` from 264 pins × π r² × bin height |
| `domain` | cases | rods [0, 1]; fuel 500–900 K; coolant 500–620 K; boron inside the table axis (300–1600 ppm, required by the validators since 2026-10-08); xenon [0, 1e21]; `jointChecked` from `J-W2`, `J-W4`, `J-W7` |
| `plant` | assumed, labelled | see section 3 |
| `geometry` | transcribed dimensions | see section 2 |

Self-check built into the exporter: for every sweep case it evaluates the separable model (reference + rod tables + temperatures + boron) and reports the difference from the transport ρ. For the joint cases that difference is the `rhoErr` of `jointChecked`; for `J-B4` and `J-B7` (boron away from the reference with banks in) it is reported but **not** put in `jointChecked`, which has no boron field: it is the separability check for boron × banks and goes in the report.

## 2. Data the exporter needs that is not in the sweep

A small file `pipeline/openmc/data/beavrs_core.json` with: the 193 assembly labels in benchmark notation (H8, R10, …) and their (column, row) positions in the 19 × 19 lattice (from `corebuilder`'s template; mesh order is (z, y, x) with x fastest and **y up, row r of the template at y index 18 − r**, checked on 2026-10-07), the bank of each of the 53 RCCA assemblies (SA 8, B 8, C 8, SB 8, D 5, SD 4, SC 4, SE 4, A 4), lattice pitch 21.50364 cm, active height 36.748 to 402.508 cm, pellet radius 0.39218 cm, 264 fuel pins per assembly, 193 assemblies, and the vessel radii. These are transcribed from the MIT-licensed `mit-crpg/BEAVRS` (head `1ccae04`) with its licence text kept beside the file; nothing is imported from the clone at export time.

Render geometry: one box per assembly (21.5 × 21.5 × 365.76 cm, material `fuel`, `element` = its label), one thin cylinder per RCCA assembly with `rod` = its bank (moves up by x × 360.68 cm), and a few annuli for the baffle, barrel and vessel: about 250 primitives. The viewer has not been run at that size.

## 3. Assumed values (every one carries `source: "assumed"` and is listed in the notes)

Rod drive speed and scram profile (the benchmark gives neither; generic 72 steps/min and a gravity drop of about 2 s); fuel heat capacity table and total mass (computed from the pellet dimensions and density, about 93 t UO2); coolant mass and cp (primary-system water, a 4-loop value); fuel-to-coolant `hA`; the steam-generator `heatExchanger` (UA with its sink at the reference temperature, so it removes nothing at HZP); the `boron` block (`range` 0 to 2000 ppm, `maxRatePpmPerS` 0.1); instruments (a log channel 1e-8 to 4e9 W, a linear channel to 4.1e9 W); trips (`power-high` at 109 % of 3411 MWt, a startup-rate trip, and a low-power limit that keeps the lesson at zero-power physics) and interlocks (none to start with). One mode, `steady`; one pump, `rcp`. The plant setpoints have no source in this repository, as for the TRIGA libraries.

## 4. Steps

1. **Data file and licence notice** (`beavrs_core.json`, `BEAVRS-LICENSE`), with a test that the label map reproduces the 193 positions and the 53 RCCA assemblies.
2. **Exporter** `export_beavrs.py` with a synthetic-sweep test: a planted separable model (known rod curves, temperature and boron slopes) generates fake sweep lines; the exporter's library must pass both validators, load in both engines, and reproduce the planted ρ at several states to within 1e-9. Two or three deliberate breaks of the exporter (a transposed mesh index, a sign error in the boron table, a bank mapped to the wrong rod id) must each fail a test.
3. **Run it on the real sweep**, write `libraries/pwr-beavrs-hzp-openmc` with status `experimental`, and check: both validators, `validity` reasons in the engine at the reference state, the engine's critical boron at the benchmark configuration (it should come out near 983 ppm, the transport result), and the hot-zero-power bank worths against step 1's (they should agree to the sweep's statistics).
4. **Look at it**: add the library to the web catalog and open it in the browser pane (assemblies, banks moving, boron control, instructor line). This is also the first place the operator panel's boron row is seen.
5. **Notes and docs**: a library README with the sources and every assumption; `docs/validation/supported-envelope.md` gets an HZP section (zero-power physics only, temperature feedback *not validated at HZP* from step 1, no decay heat, no pressure); log entry.
6. **Codex review** of the exporter and the library (consistency-auditor on exporter against the format; silent-failure-hunter on the exporter's error handling).

Rough effort: steps 1 to 3 about a working day, step 4 a few hours if the viewer copes with 250 primitives, steps 5 and 6 half a day.

## 5. Risks

1. **Decay constants.** OpenMC's `betaGroups` follow the delayed-group structure of the ENDF/B-VIII.0 data, while `build_triga` uses Keepin-style λ_i. The TRIGA libraries did the same (with the same caveat). Check once in WSL by reading the U-235 delayed-group decay constants from the HDF5 file; if they differ, write the data library's values (with provenance) rather than inherit.
2. **Shape noise.** Each delta array is a difference of two tallies with a few percent of error per bin; the reconstructed shape may show jitter and the `E_SHAPE_NEGATIVE` check may fire in low-power outer assemblies. Mitigation: floor tiny negatives as the TRIGA exporter does (reported, never silent), and report the noise level.
3. **The viewer at 250 primitives** is untested.
4. **The temperature feedback is wrong at HZP** (isothermal coefficient 1.6 to 2.0 pcm/°F too negative, step 1). The library cannot carry a library-specific validity reason today (reasons are defined by the engine), so the warning lives in the notes, the README and the supported-envelope page, and the interface shows the library as `experimental`. A per-library reason is a possible small extension; not in this step.
5. **Rod worth separability** (banks plus boron) is only checked at the joint states and `J-B4`, `J-B7`; the lesson should stay near those.

## 6. Decisions I need from you

1. **Rod ids**: the benchmark's bank names (`A` … `SE`), as proposed.
2. **Ship in the web catalog** (the library is MIT-derived, a few hundred kB of arrays), or keep it out until the lesson exists (step 5 of the M8 plan). Recommended: add it to the catalog now, for the browser check.
3. **Trips and instruments** as assumed in section 3, or different setpoints (these shape the lesson later; they are cheap to change).
