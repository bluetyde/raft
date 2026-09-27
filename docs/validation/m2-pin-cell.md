# M2 step 1: fuel pin, fuel temperature reactivity (2026-09-27)

Model: `pipeline/openmc/pin_cell.py` with open data only (`pipeline/openmc/data/jsi_standard_fuel.json`: svajger2024 Table 1 fuel element,
core-average water-to-fuel ratio from its section 4.2). A square cell, 5.0885 cm across, with reflective sides and infinite height; only the fuel
temperature changes. OpenMC 0.15.3, ENDF/B-VIII.0; 40,000 particles × 300 batches (50 inactive) per point; report `pipeline/openmc/pin_cell_report.json`.

Reference: svajger2024 Table 2 (full 3-D model of core 133, Serpent 2.1.27, ENDF/B-VII.0 with exactly broadened fuel data). Only temperature
*differences* are comparable: the reference is a whole core and this is a unit cell (k∞ = 1.359 at 294 K here).

| T (K) | Δρ here (pcm) | Δρ reference (pcm) | ratio | α here (pcm/K) | α reference (pcm/K) |
|---|---|---|---|---|---|
| 400 | −572 | −694 | 0.82 | −5.4 | −6.5 |
| 500 | −1315 | −1612 | 0.82 | −7.4 | −9.2 |
| 600 | −2170 | −2583 | 0.84 | −8.6 | −9.7 |
| 700 | −3024 | −3551 | 0.85 | −8.5 | −9.7 |
| 800 | −3891 | −4533 | 0.86 | −8.7 | −9.8 |

(1σ about ±25 pcm per Δρ; α is the secant over each 100 K step.)

**Reading.** The shape is reproduced: α steepens from 294 K to about 500 K and then levels off. The magnitude is a nearly constant 82–86% of the
reference. Likely contributors, not yet separated:
1. unit cell vs whole core: no leakage here, while in the core a hotter, harder spectrum also raises leakage, which adds negative reactivity;
2. ENDF/B-VIII.0 vs VII.0: the H-in-ZrH thermal scattering evaluation changed substantially in VIII.0;
3. temperature interpolation of nuclide data between 294, 600 and 900 K here (no multipole data in the local library), where the reference broadened exactly.

**Next:** the full-core model separates (1) from (2)–(3). A pin-cell run with ENDF/B-VII.1 data, if an open HDF5 library is obtained, would isolate (2).
Known gaps in the inputs: the cladding composition is recalled (SS304), not checked against the cited compendium; the air gap is modelled as void.
