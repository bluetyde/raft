# Milestone 8: a second reactor of a different type (plan, 2026-10-07)

Status: the plan as written on 2026-10-07 (the choice of reactor was proposed here and then decided: the PWR from BEAVRS). Steps 0 to 6 are done (2026-10-10); this text is kept as the plan, see `TODO.md` for the state and `docs/validation/m8-beavrs-library-results.md` for the last result.

## 1. What M8 must show

M8 tests the claim the project rests on: *any reactor is a library, and the simulation and view code do not change.* One TRIGA library pair cannot test that, because the code grew up around it. So M8 has two outcomes, both useful:

1. **The library builds and runs with no code change.** The claim holds for that reactor.
2. **Something forces a change.** The change is the finding. It is recorded (TODO: "record anything that forced a code change"), made as a small, named extension of the library format (as the hA law was), and the TRIGA libraries keep working unchanged.

M8 does not try to make a full plant simulator. It ends when the second reactor has a library through the same pipeline, one supported lesson, and an M7-style comparison with open measured data.

## 2. What the format and the engine can describe today

One point-kinetics core (6 delayed groups), one lumped fuel node, one lumped coolant node, reactivity as a sum of tables (rods, fuel temperature, coolant temperature, xenon), a heat exchanger with one pump, no decay heat, no flow, no void, no soluble absorber, no precursor movement. Trips, interlocks and instruments are data. A reactor of another type needs only what is in that list, or a named extension.

## 3. Candidates

| Reactor | Open data for a comparison | What it would force | Fit to the lumped model |
|---|---|---|---|
| **PWR, BEAVRS cycle 1 hot zero power** (MIT benchmark, 193 assemblies) | Yes: the specification carries measured HZP critical boron, control bank worths and temperature coefficients; OpenMC inputs are published (licence and model to check, step 0) | **Soluble boron** (a new reactivity axis, a command and a control), **decay heat** (for any trip lesson), a heavier OpenMC model | Good for startup physics; weak for transients (no loop, no flow) |
| **HTR-10 or HTTR (pebble or prismatic HTGR)** | IAEA-TECDOC-1382 for HTR-10 is free; the full benchmark handbooks are licensed (not usable, as for ICSBEP) | Decay heat (the characteristic lesson is passive heat removal), TRISO double heterogeneity in OpenMC | Very good: large graphite heat capacity fits one fuel node and one coolant node |
| **EBR-II (sodium fast reactor)** | IAEA-TECDOC-1819 (SHRT-45R) is public; startup physics benchmarks are in licensed handbooks | Flow-dependent coolant (the lesson is loss of flow), decay heat, hex-lattice model (fits ARMI, plan 08) | Weak: feedback comes from expansion and bowing, not two temperatures |
| **MSRE (molten salt)** | ORNL reports are public | Precursors that leave the core: a real engine change | Does not fit; breaks "no code change" by design |
| **Another pool reactor** (plate fuel, for example) | Mostly the same sources | Nothing | Fits, but it is not a different type |

## 4. Recommendation: a PWR from BEAVRS, hot zero power

- It is the type most training simulators exist for, and the one the project will be asked about first.
- BEAVRS has the most open measured data of the candidates (critical boron, bank worths, isothermal coefficient), so the M7 method (protocols written before runs, bands, one run each, errata, no refits) applies with no new licence.
- Hot zero power is inside what the engine already does (low power, near-isothermal, no decay heat needed). The one thing it forces is **soluble boron**, which is also the PWR lesson that matters most: approach to criticality by dilution.
- It keeps M8 honest: the boron extension is real work in the format, the engine, the runtime and the operator panel, and the plan below puts it behind a gate so it can be refused.

If you prefer to test the claim with the **smallest possible forced change**, the HTR-10 is the runner-up (only decay heat is missing, and a first library can ship without it, with a visible limit). It costs more in OpenMC (TRISO). The decision is yours; the steps below are written for the PWR and mostly carry over.

## 5. Steps and gates

**Step 0: feasibility (no library yet).** Check the BEAVRS licence and what is in the repository (OpenMC model, measured data tables, the exact HZP states). Run the OpenMC model once on this machine (WSL, `openmc-vr`) at a few hundred thousand particles and record the time and the statistical error of k. Gate: a full-core k-effective at the reference HZP state within the benchmark's own scatter of the measured critical boron, at an error below about 30 pcm per case in a time that makes a sweep of about 20 cases possible. If not, fall back to a single assembly or a reflected 2D slice, and say so; if still not, choose the HTR-10.

**Step 1: protocol (before any sweep).** A dated document, as in M7: which states are computed (reference, boron axis, two or three control bank positions, fuel and moderator temperature points around HZP), which measured values are compared, the bands, and what counts as a pass. Disclosure of anything already seen in step 0.

**Step 2: format fit check.** Write down, for this reactor, every quantity the format cannot hold. Expected list: boron axis, decay heat, a plant with several loops. For each, one of: *refuse* (leave out, show a validity warning), *fold in* (an existing field can carry it, with the note saying how), or *extend* (a named change). Gate for each *extend*: the TRIGA libraries and the golden vectors must pass unchanged, the Python and TS engines must still agree, and the change gets a capability string so older libraries are not affected (as `lumped-thermal-v2` did for the hA law).

**Step 3: pipeline.** The sweep and export for the new core through the existing scripts (`pipeline/openmc/`, `pipeline/library/`), with a record of every line of pipeline code that had to change for it. The library stays `experimental`.

**Step 4: the boron extension, if step 2 says extend.** Library: `reactivity.boron` table (axis ppm), `reference.boron`. Engine (Python first, then TS, then the vectors): a boron state, a rate-limited `boron.set` command, reactivity added to the sum. Runtime and views: a command, one control on the operator panel, one line on the instructor panel. The engine tests include a planted-reactivity case and a replay case (boron commands in a session file must replay).

**Step 5: one supported lesson.** For the PWR: approach to criticality by dilution at hot zero power, with a goal and a trip. With the same visible validity warnings as the TRIGA lesson, and an entry in `docs/validation/supported-envelope.md`.

**Step 6: comparison with the measurements** (the M7 protocol of step 1, run once, results note, errata not refits).

**Step 7: Codex review** of the milestone's merged diff before closing it, as the other milestones.

## 6. What stays out of M8

Transients with flow, a loop model, decay heat after trip, void, a full plant. Each is a candidate for a later milestone. M8 may state, in the results, which of them the second reactor would need first.

## 7. Risks

- **Full-core transport time.** Step 0 measures it. This is the main risk to the PWR route.
- **A lumped model of a PWR is crude.** The library will carry broad validity warnings, as the TRIGA ones do; what is validated is the startup physics, not a plant transient.
- **The boron extension grows.** It is the only forced change expected, and it is gated (step 2). If it grows beyond a table, a command and a control, stop and decide again.
- **Data licence.** BEAVRS's licence and any reused OpenMC scripts must be checked before anything is copied into the repository (M9 checks every file again).

## 8. Decisions needed

1. The reactor: the PWR (BEAVRS HZP) as recommended, or the HTR-10.
2. Whether step 4 (boron) may be started if step 2 finds it necessary, or stops for a new decision first. Suggested: stops for a decision, since it changes the format.
