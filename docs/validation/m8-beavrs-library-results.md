# M8 BEAVRS hot zero power: the library against the cycle 1 physics tests: results (2026-10-10)

Protocol: `m8-beavrs-library-protocol.md` (twelfth protocol; not blind, with its predictions written first). Library: `libraries/pwr-beavrs-hzp-openmc`, git `3842ace`, manifest SHA-256 `e9103694…ae35` (checked by the script), Python reference engine 0.4.0. Script: `validation/m8_beavrs_library.py`, run once (`python -m validation.m8_beavrs_library`, a few seconds). Full output: `validation/m8_beavrs_library_report.json`. Every metric is reported. Nothing was changed after seeing the results; the library is unchanged.

## Result in one paragraph

**The library reproduces the critical boron only where one bank, or none, has moved: all rods out (+8.2 ppm, good) and D in (+21.6 ppm, good). With more banks in it fails, and increasingly so: +49.9 ppm (C and D in, z +2.2), +91.5 ppm (A to D in, z +4.0) and +157.0 ppm (seven banks in, z +6.8).** The sequential bank worths fail for five of the seven banks (C −32 %, B −29 %, A −58 %, SD −32 %, SC −55 %); only D (−3.5 %) and SE (−8 %) are good, and the total of the seven is 4075 pcm against 6042 measured (−32.5 %, z −16). The temperature coefficient fails at both states (−3.57 pcm/°F against −1.75 and −8.01). Against its own transport source, the library is off by +420, +1106 and +1953 pcm with C and D, four banks and seven banks in, and by +1203 and +2243 pcm at the boron of the measured critical states S4 and S7. Decision items 1 to 4 and 6 apply.

**Predictions of the protocol: all held.** Written before the run: S2 about +50, S4 about +93, S7 about +163 ppm (found +49.9, +91.5, +157.0); worths as the single-bank tables (found exactly those); total about 4075 (found 4075); temperature coefficient about −3.6 (found −3.57, the same at both states). The small differences at S4 and S7 are because the prediction used the sweep's cases at the measured boron, while the run solves for the critical boron.

## A: critical boron (library minus measured; positive = the library needs more boron)

| State | Library critical (ppm) | Measured (ppm) | Error (ppm) | z | Label | Within 50 ppm |
|---|---|---|---|---|---|---|
| S0, all rods out | 983.2 | 975 | +8.2 ± 0.1 | +0.37 | good | yes |
| S1, D in | 923.6 | 902 | +21.6 ± 2.7 | +0.97 | good | yes |
| S2, C and D in | 859.9 | 810 | +49.9 ± 4.0 | +2.23 | fails | yes (by 0.1 ppm) |
| S4, A to D in | 777.5 | 686 | +91.5 ± 5.6 | +4.03 | fails | no |
| S7, seven banks in | 665.0 | 508 | +157.0 ± 7.6 | +6.75 | fails | no |

The model error is the tables' statistical error only (the protocol's rule); it does not include the reference reactivity's 25 pcm (about 2 ppm). S0 and S1 equal the transport model's own errors (+8.0, +21.1) to within 0.5 ppm, as expected for a single bank.

## B: sequential bank worths

| Bank | Measured (pcm) | Library (pcm) | Difference | z | Label |
|---|---|---|---|---|---|
| D | 788 | 760 | −28 (−3.5 %) | −0.61 | good |
| C | 1203 | 816 | −387 (−32.2 %) | −5.63 | fails |
| B | 1171 | 827 | −344 (−29.4 %) | −4.07 | fails |
| A | 548 | 230 | −318 (−58.1 %) | −3.30 | fails |
| SE | 461 | 422 | −39 (−8.4 %) | −0.36 | good |
| SD | 772 | 525 | −247 (−32.0 %) | −2.05 | fails |
| SC | 1099 | 495 | −604 (−55.0 %) | −4.61 | fails |
| Total of seven | 6042 (σ 77) | 4075 | −1967 (−32.5 %) | −16.29 | fails |

The library's worth of a bank is its single-bank worth, from the benchmark configuration with nothing else inserted. The measured worths are sequential (each bank with the earlier ones already in), and are larger.

## C: isothermal temperature coefficient

| State | Measured (pcm/°F) | Library (pcm/°F) | z | Label |
|---|---|---|---|---|
| S0, all rods out | −1.75 ± 0.54 | −3.57 | −2.54 | fails |
| S2, C and D in | −8.01 ± 0.54 | −3.57 | +4.58 | fails |

The two library values are the same because its temperature tables do not depend on the rods. The transport model's coefficients (−3.31 and −10.04 pcm/°F) differ with the rods, and the library's S0 value (−3.57) is close to the transport one (the difference is the secant of the library's piecewise-linear tables over ±30 K against the transport model's own cases).

## F: the library minus its transport source

| Case (state) | Library (pcm) | Transport (pcm) | Difference | Exceeds the limit |
|---|---|---|---|---|
| R-D-0 (S1 at 975 ppm) | −659 | −659 | 0 | no |
| J-W2 (S2) | −1475 | −1895 | +420 | yes |
| J-W4 (S4) | −2531 | −3638 | +1106 | yes |
| J-W7 (S7) | −3974 | −5927 | +1953 | yes |
| J-B4 (S4 at 686 ppm) | +1174 | −29 | +1203 | yes |
| J-B7 (S7 at 508 ppm) | +2055 | −188 | +2243 | yes |

The limit is the larger of 100 pcm and three times the transport error (about 80 pcm). The sign is the same in all cases: with several banks in, the library is less negative than transport, which is why its critical boron is too high. The summed worth is smaller than the real combined worth by 1.27 times (C and D), 1.42 (four banks) and 1.48 (seven banks); the ratio is the real combined worth, the reference reactivity included, over the summed one.

## Decision (protocol)

1. **Critical boron:** two of five (S0, S1). The library's claim stays at the reference configuration, plus D in; the README and `supported-envelope.md` carry these differences.
2. **Bank worths:** C, B, A, SD and SC fail, and the total fails: **the library's rod worth model is not validated for combined insertion.** No refit.
3. **Temperature coefficient:** fails at both states; the temperature feedback stays not validated; the S2 failure comes with the library having no rod dependence in its temperature tables.
4. **Summed tables against their source:** more than the limit at five states. See the next section.
5. Nothing was left uncomputed.
6. The library stays `experimental`.

## Reading (interpretation, separate from the protocol's labels)

1. **The physics of the transport model is intact; the loss is in the format.** The transport model reproduces critical boron at S1 to S7 (eleventh protocol, all five good). The library loses that entirely from the second bank on, because it adds the banks' single-bank worths, and the real combined worth is 1.3 to 1.5 times the sum here (1.27, 1.42 and 1.48). The mechanism (a bank is worth more when the others are in, because the flux shifts to it and flattens) is the usual one, but nothing here tests it.
2. **The size and direction are regular**: the ratio of combined to summed worth grows with the number of banks (1.27, 1.42, 1.48), not at random.
3. **Smallest format changes that would remove it (named, not built; each is a separate decision, and each needs new transport cases):** (a) a **correction table on the summed rod worth**: the real rod reactivity as a function of the sum of the single-bank worths, one table from the cases already in the sweep (the three joint cases plus the singles), which would fit the benchmark insertion order but not any order; (b) **pair terms** for shadowing between banks (21 pairs, many new cases), which is more general and more costly; (c) for the temperature coefficient, a **scale by the summed rod worth** (the transport ratio of the ITC at S2 to S0 is 3.0). Each would raise the question of what the library claims outside the benchmark's insertion order, which no measurement here covers.
4. **What this means for the dilution lesson:** none; it uses the reference configuration (+8.2 ppm against the measurement, good). A lesson with banks moving (a bank-withdrawal startup) is not supported by this library.

## Limits

Seven worths treated as independent; the same measured table as the eleventh protocol; the library's statistical error excludes the reference reactivity's; the temperature coefficient of the library is a ±30 K secant of piecewise-linear tables; the S2 library coefficient is evaluated at 975 ppm (the library has no boron or rod dependence in it).

## Erratum (2026-10-10, from the Codex review of the milestone)

The as-run model error of a **difference** (the sequential worths, the total, the ITC) was the quadrature of the two states' errors, which counts the tables the two states share twice (the protocol said "treated as independent", which is right for different tables and wrong for one table at two states). With the shared tables cancelled (`Model.sigma_between`; reported in the report file as `erratum`), the model errors are smaller and the z values grow in magnitude, **no label changes, no decision changes**: C −5.63 → −8.06, B −4.07 → −7.35, A −3.30 → −7.42, SD −2.05 → −5.39, SC −4.61 → −12.90, SE −0.36 → −0.88 (still good), D −0.61 (same), total −16.29 (same), ITC at S0 −2.54 (same) and at S2 +4.58 → +6.19. The tables above are the as-run numbers; the errata are not refits. (The same independent-treatment is in the eleventh protocol's worths, where the two states also share tables; its labels were not recomputed.)

