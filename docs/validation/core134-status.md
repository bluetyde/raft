# Core 134 library: status (parked 2026-10-06)

`libraries/triga-jsi-134-openmc` is the OpenMC library of the 1994 JSI benchmark core (fresh fuel, 45 elements; Mele, Ravnik, Trkov, *Nucl. Technol.* 105 (1994)). It is **parked as a regulating-rod library**: the power ascension of that paper is not compared on it. The library is not in the web catalog and no lesson uses it. Its status stays `experimental`, and its manifest notes carry the limits below.

## What it is good for

- **The regulating rod's reactivity curve.** Total worth 2460 pcm against 2550 measured (ratio 0.965), curve shape within 0.041 of the measured one, 15 pcm from the measured worth at the critical position (`m7-core134-library-results.md`, metrics R1–R3, all good). The gate runs reproduced the same worth to +15 pcm with a different method.
- **Reactivity relative to the measured critical state.** The library carries the calibration offset (323 pcm) that makes the measured critical state critical; the offset is stable across the gate cases (+364, +323, +471 pcm for the three cases, with 70 pcm of statistical error each).

## What it is not good for

| Quantity | Finding | Where |
|---|---|---|
| Shim, safety and transient rod worths | 31 %, 12 % and 21 % too high; the safety rod's shape is off by 0.117 | `m7-core134-library-results.md` |
| Fuel temperature feedback | 37–40 % weaker than the measured reactivity loss at 60–100 °C average fuel temperature (about −6.2 pcm/K against the −8.6 the measurement needs) | `m7-core134-library-results.md`, `m7-core134-feedback-results.md` |
| Heat transfer | the base library's assumed constant `hA` 3000 W/K, not fitted: the fuel rise is 35–68 % of the measured one | `m7-core134-library-results.md` |
| Absolute reactivity | 323 pcm above critical at the measured critical rods, and about ±500 pcm of input uncertainty from the fuel composition (the paper's own estimate for the 235U content; the model moves about 200 pcm per 0.01 of fuel H/Zr) | `core134-library-gate.md` |

## What was ruled out for the feedback (all dated protocols, all run once)

- a method artefact in the reference treatment (−48 ± 44 pcm);
- a non-linear first interval (the 372 K slope is 0.95 ± 0.11 of the 400 K one);
- the fuel hydrogen content (H/Zr 1.65 against 1.60 gives the same slope, 1.05 ± 0.13);
- the thermocouple-to-mean-temperature conversion of the paper (its radial factor is reproduced from the paper's own Table VIII at 125 kW, its axial factor agrees with the model's within 1 %; the conversion that would remove the shortfall is 25 % below every independent estimate).

The shortfall is not a constant factor: the conversion it would need falls from 1.30 at step 1 to 1.04 at step 7, so the model's feedback has too little temperature dependence between 30 and 100 °C.

## What would unpark the power ascension

1. A cause for the weak feedback, found by one of these (each a dated protocol written before its run): OpenMC's treatment of the zirconium hydride thermal scattering temperatures and of the Doppler interpolation between 294, 600 and 900 K data; a test of ENDF/B-VIII.0's ZrH scattering law against the measured fuel coefficient (the 2002 isothermal and fuel coefficients are a second measurement, on core 176); a finer table with knots between 294 and 400 K and a longer sweep.
2. A fitted heat transfer for core 134 (the earlier law does not transfer: the fitted exponent is 0.64, not 0.22), written as a protocol with a held-out part of Table IX.
3. Only then the seventh comparison of the power ascension itself.

## Where the evidence is

`validation/data/jsi-core134/` (the transcribed benchmark data and its README), `docs/validation/core134-library-gate.md` (the gate and its sensitivity scan), `m7-core134-library-protocol.md`/`-results.md`, `m7-core134-feedback-protocol.md`/`-results.md`, `m7-core134-conversion-protocol.md`/`-results.md`, and the scripts `validation/m7_core134_*.py` with their reports.
