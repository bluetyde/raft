# Architecture review

Reviewed 2026-09-25. Scope: README, PLAN, TODO, ARCHITECTURE, WORKFLOWS, TOOLING and plans 01–09. This is a review of the proposed system, not a verification of an implementation. Recommendations below are proposals; the existing plans have not been rewritten. External tool versions, benchmark contents and source licenses were not independently rechecked.

## Assessment and assumptions

Keep the offline pipeline, versioned library and headless browser simulation. They provide useful boundaries without requiring a server. Keep the Python reference and the separation between simulated quantities and instrument readings.

Assume the first release is a local educational application with one authoritative simulation, a synthetic fixture followed by the JSI reference library, and no network service. The principal risks are inconsistent numerical contracts and overbroad model claims, rather than service scale. Finish those contracts before implementing the two language versions.

## Fix before the first physics prototype

### 1. Specify equilibrium preconditions and initialization

**Evidence:** [plan 01](plans/01-physics-core.md), Equations and Tests, includes an external source but requires constant power at zero reactivity without specifying a zero source.

At precursor equilibrium, `C_i = β_i P / (Λ λ_i)`. Substituting into the documented power equation gives `0 = ρ P / Λ + S`, so **`P = −S Λ / ρ`**, consistent with the existing source-multiplication test. At `ρ = 0`, a positive source prevents constant-power equilibrium. Keep the source-multiplication formula and specify `S = 0` for the critical steady-state test.

Define source units as W/s for this scaled formulation, equilibrium versus explicitly supplied precursor inventories, initial iodine/xenon inventories, and thermal initial conditions. A source-driven shutdown initialization must require negative reactivity; reject an equilibrium request at zero or positive reactivity. Do not silently solve every initial state as critical.

**Acceptance:** test the source-free critical equilibrium, source-driven subcritical equilibrium, and rejection of impossible equilibrium requests independently. This prevents a bad fixture becoming the Python and TypeScript reference alike.

### 2. Make the reactivity reference state explicit

**Evidence:** plan 01 defines an offset that makes the reference critical; [plan 02](plans/02-openmc-pipeline.md) derives reference reactivity from transport; [plan 03](plans/03-library-format.md) has `excess` and separate tables without a complete reference-state contract.

Store the reference rod vector, temperatures and xenon concentration, the computed reference reactivity, and any separately labeled calibration adjustment. Define each additive table as a delta from that same reference. Otherwise authors can double-count rod worth or unknowingly erase transport bias by forcing criticality.

Independent rod curves are an explicit approximation. Store the joint-state domain in which their superposition was checked, not only each rod's independent range. In-range individual axes do not establish an accurate combined state.

**Acceptance:** every table contributes zero at its reference; the reconstructed reference reactivity matches the stored value; selected joint configurations meet a declared error budget.

### 3. Define power, shape and density as different quantities

**Evidence:** plan 02 permits “fission or heating” tallies and normalizes shapes to one; [plan 04](plans/04-3d-explorer.md) calls shape times total power “power density.”

For v0, define each shape entry as a dimensionless fraction of the specified modeled power. Then `P × fraction` is bin power in W. Density additionally requires bin volume: `P × fraction / volume` in W/m³. Record bin volumes, array order, tally basis, normalization basis and which regions receive that power. Do not interchange a fission-rate shape and deposited-heating shape without a documented conversion.

The thermal equation currently deposits all P into fuel. Record that as a model assumption or provide the deposition fraction explicitly. Distinguish the kinetics power variable from total thermal power if decay heat is added; the current model has no separate decay-heat inventory.

**Acceptance:** unequal-volume synthetic bins preserve total bin power while producing the expected different densities. Energy-balance checks use the same power convention as thermal inputs.

### 4. Replace open-ended reactor generality with supported model capabilities

**Evidence:** PLAN promises new reactors through data alone; WORKFLOWS calls any required code change a bug; plan 01 deliberately fixes a limited set of equations and approximations.

Use a named model capability such as `point-kinetics/lumped-thermal-v1`. Libraries declare their required capabilities and supported operating regimes. New parameter sets within this model need no code changes; new physics models can legitimately require a new capability and implementation. Unsupported capabilities must fail loading with a clear reason.

Separate parameter coverage, approximation validity and validation evidence. Add states such as `supported`, `unvalidated` and `out-of-domain`, with reason codes. Define whether each condition pauses the run, disables a visualization or permits explicitly exploratory continuation. A rectangular range warning alone cannot express the limitations already identified in the plans.

**Trade-off:** narrower first-release claims, but an extensible format that does not pretend arbitrary thermal systems can be encoded as constants.

## Fix before the browser integration

### 5. Specify command scheduling, event ordering and protection signals

**Evidence:** ARCHITECTURE timestamps commands but defines no acknowledgement or tie-breaking rule. Plan 01 splits solver steps at events; plan 05 introduces lagged and failed instruments without defining which signals trigger protection.

Have the worker assign an accepted simulation time and monotonically increasing sequence number. Return accepted/rejected acknowledgements with command IDs and reasons. Specify ordering for simultaneous scripted events, operator commands, trip crossings and scram actions. Enforce paused-state and already-tripped behavior in the simulation.

Declare each trip's input channel, threshold direction, latching/reset behavior and event-detection semantics. Instrument updates must follow simulation time, independently of render frequency. Distinguish trips based on ideal modeled quantities from those based on modeled instrument channels; fault injection must produce the declared behavior.

Replace free-text interlock and scenario expressions with a small typed predicate format, validated signal references and supported operators. Unknown operators are errors, not ignored extensions.

**Acceptance:** a command at an outer-step boundary, a trip inside a step, simultaneous rod commands and an instrument failure all have repeatable outcomes at different display frame rates.

### 6. Make replay a versioned state contract

**Evidence:** ARCHITECTURE promises identical replay from library, seed and command log; [plan 06](plans/06-instructor.md) exports only a library ID and omits a checkpoint schema.

Pin a library content digest, engine build, solver configuration, scenario digest and initial-state definition in each session. A checkpoint must include precursor and poison inventories, thermal and rod state, controller/trip latches, instrument filter and random-generator state, scenario progress, event cursor and solver history where applicable. Branches need parent identity and fork position.

Choose either to serialize adaptive-solver history or to define canonical restart boundaries used during both original execution and replay. A multistep solver cannot generally be restored from physical variables alone with an identical numerical trajectory.

Guarantee repeatability for a pinned engine/configuration first. State explicit tolerance-based agreement across Python, TypeScript and engine versions instead of promising universal bit identity.

**Acceptance:** checkpoint restoration and replay match uninterrupted execution, including noise and event logs; branching preserves the original branch.

### 7. Complete the library's binary and interpolation contracts

**Evidence:** plan 03 sketches offsets but leaves array descriptors incomplete. Plan 02 uses additive shape deltas while plan 03 says “each shape must sum to 1.”

Distinguish normalized base shapes from signed delta arrays. Base shapes sum to one; deltas sum to zero. Reconstructed shapes must be finite, nonnegative within an explicitly chosen roundoff tolerance and normalized. Do not silently clip substantial negative values and renormalize: that would conceal a failed approximation.

Specify file digest, byte length, element type, endianness, dimensions, strides/order and offset bounds. Include a finite-number policy and checks for duplicate element IDs, mismatched geometry IDs, missing files and invalid tables. Bound imported archive sizes and require contained relative asset paths.

Define interpolation and out-of-range behavior per table. Describe uncertainty as transport sampling uncertainty unless interpolation and model errors are actually included; normalizing correlated bins does not justify treating uncertainties as independent.

Separate schema compatibility from model capabilities. During v0, accept explicitly supported versions rather than assuming every `0.x` library has compatible semantics.

**Acceptance:** Python and TypeScript accept the same valid fixtures and reject malformed offsets, unsupported capabilities and invalid reconstructions with matching reason codes.

## Fix before expensive runs or release claims

### 8. Strengthen cache identity and publication

**Evidence:** plan 02 hashes parameters, OpenMC version and settings, but merely logs model commits and a nuclear-data path.

Include model content, nuclear-data identity, relevant dependencies, tally definitions and run configuration in the cache key. A stable path is not stable content. Keep raw transport outputs distinct from derived products so extractor changes invalidate extraction without necessarily repeating transport.

Use explicit case states: pending, running, failed and completed. Publish results only after completion checks; retry failed cases with bounded attempts and recorded causes. Build libraries into staging directories and publish the manifest only after all assets and validation results pass checks.

**Acceptance:** a model or data change invalidates the relevant cache; an interrupted run cannot be consumed as complete.

### 9. Separate implementation agreement from independent validation

**Evidence:** plan 01 ports the Python solver function by function and regenerates its golden vectors. Plan 07 records higher-level regressions without establishing release eligibility.

Golden vectors catch port drift, but shared mistakes can pass both implementations. Retain analytic checks and an independently configured reference integration path. State the assumptions of approximate analytic tests and use absolute-plus-relative tolerances for near-zero quantities. Add step/tolerance convergence and checkpoint/event tests.

Match pulse measurements to the modeled configuration and conditions before comparing them; common facility identity alone does not establish comparability. Separate calibration cases from held-out measurements. Define eligibility for `synthetic`, `experimental` and `validated-for-domain` libraries. A failed comparison may remain inspectable without being labeled validated.

Numeric acceptance thresholds remain pending evidence; do not invent them in this review. Define the metrics and decision process before using results to select tolerances.

### 10. Bound runtime work and keep the first renderer small

**Evidence:** ARCHITECTURE couples a fixed 10 ms outer step with high speed-up; plan 06 targets 3600×. That combination requires **360,000 outer steps per wall second**, even before adaptive internal steps. Plan 03 specifies primitives while TOOLING prioritizes CSG reuse.

Use bounded work batches that yield to command processing. Never skip physical evolution to catch up. Show achieved simulation rate; decouple snapshot emission, plot sampling and physics advancement. Decide whether slow regimes can use larger scheduling intervals while preserving instrument and event semantics. Keep pulse extrema and integrated energy independently of 30–60 Hz display snapshots.

Start with the documented primitive renderer and isolate it behind a geometry adapter. Evaluate CSG reuse separately, including picking, cutaways, depth composition, rod transforms and overlay mapping. It should not block the first simulation slice.

Set measured budgets for library memory, load time, command latency, replay latency and solver throughput on a named reference laptop. For sizing, two float32 arrays with N states and B bins require `8 × N × B` bytes before metadata and runtime copies. Thus “a few MB” is a target to test, not a format guarantee.

## Proposed component boundary

```text
Transport results -> extractor -> validated, immutable library
                                         |
                                   loader/validator
                                         |
Commands -> scheduler -> physics + instruments + protection
                |                         |
        ordered event log          snapshots/checkpoints
                |                         |
                +------ replay -----------+--> views
```

Keep all authoritative state in one worker. Views own presentation state only. A mirrored window must detect owner loss, disable controls and report disconnection; automatic ownership migration can wait. Record library-load failures, rejected commands, solver failures, event counts, achieved rate and validation status as structured diagnostics.

## Recommended next slice

1. Resolve findings 1–4 in the physics and library contracts; write one synthetic fixture with fully defined units and initial conditions.
2. Define commands, checkpoints and binary descriptors; add valid and invalid conformance fixtures before porting.
3. Demonstrate load -> initialize -> move rod -> advance -> snapshot -> checkpoint -> replay in a headless run, then attach a minimal operator panel and primitive viewer.
4. Use the same fixture for a browser end-to-end check, including a malformed library, a trip, pause/resume and replay. Only then expand the real transport grid.

Revisit spatial/thermal model capabilities when a second reactor needs them; joint response surfaces when holdouts reject superposition; CSG when primitive coverage fails; and a server only when actual networked classroom requirements arrive. ARMI remains an optional upstream model adapter.

## Small documentation corrections

- PLAN, WORKFLOWS and plan 02 still introduce the shared `openmc-mcnp` environment; the newer log, TODO and TOOLING require the dedicated `openmc-vr` environment. Consolidate the instructions before running the pipeline.
- WORKFLOWS says to stop a server by port. Replace this with stopping only the process started by the current session, consistent with the coordination rules.
- ARCHITECTURE says SI internally but stores poison density in atoms/cm³ and geometry in cm. Document these as explicit boundary exceptions or convert them consistently; define microscopic versus macroscopic cross-section units too.
- ARCHITECTURE describes schemas as existing, although they remain planned. Mark them planned until files are present.

## Review verification

No implementation or runnable test suite exists in this project yet. This review used document cross-checking and algebra against the supplied equations. No transport runs, browser tests or end-to-end regressions were executed. Proposed acceptance checks above are future work, not passing test results.
