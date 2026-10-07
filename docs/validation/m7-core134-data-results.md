# M7 core 134 feedback: ZrH data, temperature treatment and effective temperature: results, parts P and C (2026-10-06)

Protocol: `m7-core134-data-protocol.md` (ninth protocol; not blind, see its disclosure). Runs: the pin-cell sets P1 and P2 (`pipeline/openmc/results/core134_pincell_p1.json`, `_p2.json`, 200 000 particles × 300 batches, ENDF/B-VIII.0, 68 and 55 minutes). Script: `validation/m7_core134_data.py`, run once (`python -m validation.m7_core134_data`). Full output: `validation/m7_core134_data_report.json`. **Part D (the ENDF/B-VII.1 data) was not run when this note was first written (the download was not yet approved); it was run on 2026-10-07 and is reported in the update at the end. The text above is the state before it.** Every metric of the parts run is reported. Nothing was changed after seeing the results, and no library was changed.

## Result in one paragraph

**OpenMC's temperature treatment does not explain the shortfall (P): the pin cell's ratio to the Serpent reference is 0.80–0.84 at 400, 500 and 600 K (spread 0.036, "constant") and the curve between tabulated temperatures is smooth. The uniform fuel temperature of the library is a partial explanation (C): the reactivity-effective fuel temperature exceeds the volume mean by a factor of 1.16 in the primary calculation (range 1.04–1.27), which removes 31 % of the step 7 shortfall and brings every step of the what-if to good or plausible, with step 7 at the edge of the plausible band (500 against 666 pcm, 25 % short).** A residual of 69 % of the shortfall remains (166 of 242 pcm at step 7); the data evaluation (D) is untested. The decision follows the protocol: the effective temperature is a known limit of the model and a transport test with per-element temperatures is the next protocol; the data question stays open until the download is decided. No library changes.

## P: the pin cell (reactivity change against 294 K, pcm ± standard error)

| T (K) | P1 (interpolation) | Reference (Serpent, ENDF/B-VII.0) | Ratio R | P2 (snap to nearest) | P1 − P2 |
|---|---|---|---|---|---|
| 330 | −180 ± 10 | | | +11 ± 10 | −190 ± 14, effect |
| 372 | −409 ± 10 | | | −418 ± 10 | +9 ± 14, none |
| 400 | −558 ± 10 | −694 | **0.804 ± 0.014** | −418 ± 10 | −140 ± 14, effect |
| 500 | −1310 ± 10 | −1612 | **0.813 ± 0.014** | −1423 ± 10 | +113 ± 14, effect |
| 600 | −2170 ± 11 | −2583 | **0.840 ± 0.014** | (not run) | |

- **P1 metric: R(400, 500, 600) = 0.804, 0.813, 0.840; spread 0.036 ≤ 0.08: constant.** The deficit against the reference is about 16–20 % at all three temperatures, including 600 K where every datum is tabulated and no interpolation takes place (as the earlier 40 000-particle report had already shown: 0.82, 0.82, 0.84).
- **Smoothness:** the change at 330 K is 0.322 of that at 400 K (linear expectation 0.340, departure 5 %) and at 372 K 0.733 (expectation 0.736, 0.4 %): smooth.
- **P2 (snap to nearest) differs from P1 by more than 2σ at 330, 400 and 500 K, as it must:** a snapped run takes the nuclide data at 294 K (for 330, 372 and 400 K) or 600 K (for 500 K) and the thermal scattering tables at 296 K (330 K) or the tabulated temperature (372 K snaps to 400 K). The staircase pattern is what the table shows; at 372 K, where the thermal scattering table is the 400 K one and the nuclides are at 294 K, P2 equals P1 within 9 ± 14 pcm.
- **Reading (interpretation, not a protocol label):** the snapped runs separate the two data sets. P2 at 400 K (exact ZrH tables, no Doppler broadening beyond 294 K) is −418 pcm, so the interpolated Doppler contribution in P1 at 400 K is about 140 pcm (a quarter of the change). P2 at 500 K has the full 600 K Doppler broadening: 113 pcm more loss than P1's interpolation (a fraction of 0.673 of it), implying a Doppler-only effect of about 350 pcm at 600 K, of which linear interpolation gives 120 pcm at 400 K. A √T law for the Doppler effect would give about 134 pcm at 400 K, 14 pcm (2.5 % of the change) more. The interpolation of the nuclide data is therefore a small effect, not the 40 % shortfall.

## D: the ENDF/B-VII.1 data

**Not run.** It needs the ENDF/B-VII.1 HDF5 library from `openmc.org/official-data-libraries` (of the order of a gigabyte), which is not downloaded without the user's approval of the file, its source and its size. The what-ifs W2 and W3 depend on it and are not computed.

## C: the effective fuel temperature factor κ (core 134 library shapes; 45 elements, 15 in-core axial bins, 48 fuel positions)

| Weights F^p V, p | Exponent n | κ full | κ radial only | κ axial only |
|---|---|---|---|---|
| 2 (primary) | 0.22 (primary) | **1.159** (partial) | 1.080 | 1.068 |
| 2 | 0 | 1.193 | 1.096 | 1.081 |
| 1 | 0.22 | 1.085 | 1.044 | 1.037 |
| 1 | 0 | 1.103 | 1.053 | 1.045 |
| 3 | 0.22 | 1.220 | 1.109 | 1.092 |
| 3 | 0 | 1.268 | 1.132 | 1.111 |

- **C1 label: partial** (1.05 ≤ κ < 1.35) for the primary and for 15 of the 18 combinations; three are "none" (the radial-only or axial-only parts with p = 1: 1.044, 1.037 and 1.045). The range is 1.037–1.268. The radial and axial parts multiply approximately (1.08 × 1.07 = 1.16).
- The hand estimate in the protocol (about 1.13) was close.

## W: the what-if with the effective temperature (reactivity loss at the steps of Table IX, model/measured pcm; primary line TB, γ_B, linear water warming)

| Step | W0 (library as it is) | W1 (mean fuel rise × 1.159) |
|---|---|---|
| 1 | 41/50 good | 49/50 good |
| 2 | 92/119 plausible | 109/119 good |
| 3 | 162/218 fails | 192/218 plausible |
| 4 | 249/345 fails | 294/345 plausible |
| 5 | 315/461 fails | 371/461 plausible |
| 6 | 373/564 fails | 440/564 plausible |
| 7 | 424/666 fails | 500/666 plausible (24.9 % short, at the edge of the band) |
| Aggregate | fails (best plausible) | plausible (worst plausible, best plausible) |
| Step 7 shortfall removed | 0 % | **31 %** |

## Decision (protocol)

1. **P1 constant and P2 smooth in the sense of the protocol:** OpenMC's temperature treatment is not responsible for the shortfall. (The first table interval's resolution was excluded by the seventh protocol.)
2. **Part D not run (no download approved):** the data evaluation is untested; W2 and W3 are not computed.
3. **C1 partial (κ = 1.16):** the library's uniform fuel temperature is a known limit of the model; it removes 31 % of the step 7 shortfall. **The next protocol is a transport test with per-element fuel temperatures** (and axial where practical): κ here is a proxy that assumes the reactivity weights are a power of the local power density.
4. **W3 is not computed, so a residual remains:** 69 % of the step 7 shortfall (166 of 242 pcm) after the effective temperature alone. The what-if W1 reads plausible at every step in the primary line, with step 7 at the edge of the band; read as "close to the edge of the stated scale", not as an explanation.
5. **Nothing in any library changes**; all stay `experimental`.
6. **Not tried after seeing the results (per the protocol):** other evaluations, treatments, weights, exponents or particle counts than those listed, a fit of anything.

## Notes on the run

- The script's first run printed decision item 4 from W1 when W3 was not computed, where the protocol says that not computed is a residual; the item was corrected before this note was written (and the test updated). The numbers are those of the one analysis run.
- The P2 set also contains the 294 K run (its baseline for the differences), a clarification stated in the script.
- The bin below the core is left out of part C (the regular elements hold no fuel there, and the nominal volume it carries would distort the means).

## Limits, repeated

The pin cell is an equivalent unit cell, not the core, and the reference is another code and evaluation; ratios at 400 K carry 1.4 %; part C is a proxy for the transport effect and uses the model's own shape arrays; a "partial" label says how much of the shortfall a candidate could remove, not that it does; the 31 % is a what-if with a fixed κ for all steps, though κ depends weakly on the power shape and on the temperature level.

## Update 2026-10-07: part D run (the ENDF/B-VII.1 download was approved)

The ENDF/B-VII.1 OpenMC library (`endfb71.tar.xz`, 1 697 275 216 bytes, from the OpenMC data page, extracted to WSL `/root/nuclear_data/endfb-vii.1-extract`) has the same thermal scattering names and temperature grids for the ZrH (296, 400, 500, 600, 700, 800, 1000, 1200 K) and the same nuclide temperatures as the ENDF/B-VIII.0 library. The pin cell of part P (P1 settings, 200 000 particles × 300 batches, 46 minutes) was run with it at 294, 400, 500 and 600 K (`pipeline/openmc/results/core134_pincell_vii1.json`), and `validation/m7_core134_data.py` was run again with that file present; the P and C results are identical to those above.

| T (K) | VII.1 (pcm ± σ) | VIII.0 (P1) | Reference (Serpent, ENDF/B-VII.0) | R VII.1 | R VIII.0 | Δρ VII.1 / Δρ VIII.0 |
|---|---|---|---|---|---|---|
| 400 | −567 ± 10 | −558 | −694 | 0.817 | 0.804 | 1.016 |
| 500 | −1333 ± 9 | −1310 | −1612 | 0.827 | 0.813 | 1.018 |
| 600 | −2203 ± 10 | −2170 | −2583 | 0.853 | 0.840 | 1.015 |

- **D1 label: not the explanation.** The ratios with VII.1 are 0.817, 0.827 and 0.853 (mean 0.832); none is within 0.95–1.05, and the mean rises by 0.013 over VIII.0, below the 0.05 of the "part" band. **The pin cell is 15–18 % weaker than the reference with either evaluation**, and the older evaluation gives a fuel feedback only 1.5–1.8 % stronger (D2). So the difference from the reference does not come from the VII.1 to VIII.0 change of the ZrH and nuclide data; what remains is the code and the cell (Serpent against OpenMC, and the details of the equivalent cell), not tested here.
- **W2 (fuel table × 1.016): not an explanation by itself:** step 7 432 pcm (3 % of the shortfall removed), labels as W0.
- **W3 (the effective temperature of part C and the VII.1 factor together):** primary plausible at every step, best good; step 7 **509 pcm against 666 (24 % short, at the edge of the plausible band), 35 % of the step 7 shortfall removed**; steps 1–2 good, 3–7 plausible.
- **Decision items revised:** (2) the ENDF/B-VII.1 data do not explain the pin-cell deficit. (4) By the protocol's rule W3 is "good or plausible", so the data evaluation and the temperature distribution together are said to explain the weak feedback. **That rule is a weak statement here:** 65 % of the step 7 shortfall (157 of 242 pcm) remains and step 7 sits at the edge of the band; the effective temperature accounts for nearly all of what W3 removes (31 of the 35 %).
- **Not changed:** no library; the transport test of the per-element temperatures (tenth protocol, running) tests κ in transport.
