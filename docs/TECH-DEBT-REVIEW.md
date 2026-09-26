# Technical debt review

Reviewed 2026-09-25 using the tech-debt skill. Scope: project plans, workflows, tooling survey, TODO and the [architecture review](ARCHITECTURE-REVIEW.md).

## Assessment

The project is documentation-only: the inspected directory contains Markdown plans, with no application, dependency manifests, schema, tests or project-local `.git` directory. There is no implemented codebase to grade for duplication, coverage or dependency vulnerabilities. Missing implementation is not automatically technical debt.

Existing debt is concentrated in duplicated instructions and contracts that are not yet executable. Several implementation choices could create substantial future maintenance costs. Most contradictions identified in the architecture review were corrected during this turn. Address the remaining small documentation fixes now, then manage each design risk alongside the feature that introduces it.

Claude Code completed `review-integration` during this audit. The refreshed log, TODO and targeted document checks confirm that environment selection, process ownership, planned-schema wording and cache design were corrected; the log also records the broader contract changes. This report credits those changes and does not edit the main plans. Proposed owner roles below are responsibilities, not agent assignments or additional claims.

## Prioritized register

Scores use the skill's formula: **(impact + risk) × (6 − effort)**. Each input is 1–5; higher impact/risk and lower effort increase priority. These are judgment estimates, not measurements. Effort ranges cover the bounded remedy described below, exclude transport runtime and external-data access, and assume one contributor familiar with the project. Milestone dependencies override raw score order.

| ID | Category / status | Item and cost of leaving it | I | R | E | Score | Estimated effort | Due / owner role |
|---|---|---|---:|---:|---:|---:|---|---|
| TD-02 | Architecture / existing contract gap | Library semantics can diverge across the producer, solver and viewer, forcing migrations | 5 | 5 | 2 | 40 | 1–2 days for contract and fixtures | Before parallel implementation / format owner |
| TD-03 | Infrastructure / prospective | Machine-specific setup makes failures difficult to reproduce | 4 | 4 | 2 | 32 | 0.5–1 day | With initial scaffold / build owner |
| TD-01 | Documentation / partly resolved | Repeated operational settings and one shared dev port can drift or collide | 3 | 3 | 1 | 30 | 1–2 hours | Before concurrent web work / maintainer |
| TD-04 | Test / prospective | Regenerated golden vectors can ratify a shared solver error | 4 | 5 | 3 | 27 | 2–4 days for initial checks | With M1, enforced in M4 / physics owner |
| TD-05 | Architecture / prospective | Replay added late requires invasive state and event changes | 4 | 5 | 3 | 27 | 2–4 days for first checkpoint path | First integration slice / runtime owner |
| TD-06 | Infrastructure / prospective | Incomplete cache identity can silently reuse incompatible scientific results | 4 | 5 | 3 | 27 | 1–3 days | Before large sweeps / pipeline owner |
| TD-07 | Dependency / prospective | Copied CSG renderer becomes a second upstream maintenance obligation | 3 | 3 | 2 | 24 | 0.5–1 day for decision and boundary | At renderer selection / explorer owner |
| TD-08 | Architecture / prospective | Unbounded history and output traffic create long-session memory and latency problems | 3 | 4 | 3 | 21 | 1–3 days | With first worker and recorder / runtime owner |
| TD-09 | Documentation / partly resolved | Review tasks need closure evidence to distinguish decisions from verified behavior | 2 | 2 | 2 | 16 | 1–2 hours | With first implementation / maintainer |

## Remedies and closure evidence

### TD-01 — Consolidate operational instructions

**Evidence:** the original environment and shutdown conflicts are now corrected in the active plans. The same port, 5187, is still specified for web work without a per-session allocation rule. Environment and rendering decisions remain repeated across plans and TOOLING, increasing the chance of renewed drift.

Make WORKFLOWS the canonical location for setup and process ownership; other plans link to it. Specify a configurable port per active checkout and record the process actually launched. Retain dated tool surveys as history rather than executable setup instructions.

**Done when:** active instructions agree on the dedicated environment, own-process shutdown and port handling. Do not rewrite historical log entries. This is the quickest way to reduce coordination failures before code exists.

### TD-02 — Finish one contract before multiplying implementations

**Evidence:** ARCHITECTURE now correctly marks schemas as planned. The updated plans define units, reference-state semantics, base versus delta shapes and version support; TODO's new Contracts section tracks these. The normative specification, schema and executable fixtures are still absent. This is a dependency to finish before consumer implementations, not a reason to repeat the design review.

Create one normative library specification and machine-readable schema, with a tiny valid fixture and intentionally invalid fixtures. Reference these from plans instead of maintaining independent field definitions. Assign stable semantic validation error codes. When implementing TypeScript types, derive them from the authoritative contract where practical; semantic checks still require tests in both languages.

**Done when:** the fixture has explicit initial conditions and units, both consumers agree on accepted/rejected cases as they arrive, and no example requires guessing a field's meaning. Do not build a general schema-generation platform for this first format.

### TD-03 — Make the first scaffold reproducible

**Evidence:** TOOLING records Windows and WSL installations; TODO proposes cloning a shared conda environment. Neither is a project-owned reproducibility record. Plan 09 correctly calls for CI early, but no runnable scaffold exists yet.

At scaffold creation, declare direct Python dependencies and supported versions, capture a reproducible pipeline environment, commit the web dependency lockfile and runtime requirements, and keep nuclear-data locations configurable. Record data identities separately from paths. Make the synthetic fixture sufficient for fast CI without access to the large transport installation.

**Done when:** a clean project checkout can run its first headless test and web build using documented setup, and CI runs the same checks. This is a setup gate, not a claim that uninstalled dependencies are outdated. No package upgrade is recommended by this review.

### TD-04 — Control the cost of two physics implementations

**Evidence:** plan 01 proposes a function-by-function Python-to-TypeScript port; WORKFLOWS regenerates golden vectors whenever the Python reference changes. Independent checks are now specified by the integrated plans. The remaining maintenance risk is unreviewed expected-result regeneration and keeping those independent checks active as the two implementations evolve.

Keep the two-language boundary, but distinguish equation verification, numerical-method verification and port agreement. Add independent analytic checks and a trusted comparison integration path. Store vector provenance, solver settings and a readable before/after summary when expected results change. Require a reason for changed expectations; do not silently refresh them to make tests pass.

**Done when:** a deliberately perturbed coefficient or event time fails an independent check, expected-result changes are reviewable, and Python/TypeScript comparisons use declared tolerances. This is a proposed verification experiment, not an executed test.

### TD-05 — Establish checkpoint semantics before the instructor UI

**Evidence:** the updated ARCHITECTURE and TODO now move a headless checkpoint/replay slice ahead of full integration, and plan 06 has session pins and checkpoint contents. This addresses the design-order concern. Retain the following implementation gate so checkpoint support does not slip back to M6 with its instructor UI.

Implement a minimal serialize/restore operation with the first stateful runtime. Pin engine and library identities, specify event ordering and include all hidden state. The timeline UI and multiple saved branches can still wait until M6.

**Done when:** one small headless scenario resumed from a checkpoint matches uninterrupted execution, including instrument noise and trips. This avoids retrofitting serialization into every module after the UI is built.

### TD-06 — Preserve the integrity of expensive cached results

**Evidence:** refreshed plan 02 now specifies content hashes, nuclear-data identity, completed-case reuse, raw/derived separation and staging publication. The design gap is resolved. This item is a prospective implementation gate before expensive runs, not an outstanding request to redesign the cache.

Implement cache keys from effective model/data/run inputs, separate raw results from extraction outputs, and consume only verified completed cases. Record retries and failures; stage library assets before publication.

**Done when:** changing model content invalidates a run, changing only extraction logic rebuilds derived artifacts, and an interrupted run cannot be read as complete. These checks protect compute investment and scientific traceability before the sweep grows.

### TD-07 — Make renderer reuse a deliberate maintenance decision

**Evidence:** the integration selects primitives first behind an adapter in plan 04; TOOLING still strongly favors extracting or copying Studio's renderer. The first-stage decision is made, but future reuse ownership and the tooling recommendation need to remain consistent with it.

Start with primitives for the synthetic slice. At the reuse gate, choose either a versioned shared component or a deliberately vendored snapshot. For a copy, record upstream identity, local modifications, required notices and the procedure for evaluating upstream fixes. Keep a small geometry adapter so simulator state is not coupled to Studio's internal UI.

**Done when:** one renderer path is selected for the milestone, its ownership/update policy is recorded, and picking, cutaways, moving rods and overlays have a focused integration check. The effort estimate covers the decision and boundary, not extraction of the full renderer.

### TD-08 — Give histories and snapshots explicit resource limits

**Evidence:** ARCHITECTURE specifies frequent snapshots and periodic checkpoints; plan 06 retains old branches and permits long accelerated sessions. It does not set history quotas, eviction behavior or output backpressure.

Bound plot buffers, pending view updates and retained checkpoints. Specify what happens when a session reaches its memory/storage limit and what remains exportable. Coalesce stale display updates without dropping authoritative events. Track pulse extrema and energy independently of display sampling. Define buffer ownership before transferring binary arrays between the worker and view.

**Done when:** an accelerated synthetic session stays within a stated memory budget, controls remain responsive, and retained history can still replay. Measure this on a named test machine; do not invent a universal performance target.

### TD-09 — Close review findings through evidence

**Evidence:** the updated TODO now links to the architecture review and contains a Contracts section. That resolves the missing actionable backlog. The remaining issue is distinguishing a documented contract from implemented and verified behavior, and keeping this audit discoverable without duplicating that backlog.

Add one discoverable link to this register when updating the backlog, and map accepted findings to existing milestone tasks. Avoid copying the full findings into several documents. Use statuses such as proposed, accepted, documented, implemented and verified. Link a resolving test or decision when closing an item; documentation integration alone does not verify behavior.

**Done when:** each accepted finding has one task, a responsible area, a due milestone and closure evidence, while rejected or deferred findings have a short reason. Reconcile against the integration result before creating duplicate work.

## Phased remediation alongside feature work

1. **Before the first implementation:** turn TD-02's documented decisions into the normative specification and fixtures. Finish TD-01's port/configuration cleanup before concurrent web work. Use the existing Contracts backlog for TD-09. These changes should take a short focused pass, not become another architecture rewrite.
2. **With the synthetic prototype:** add TD-03's reproducible scaffold, TD-04's independent checks and TD-05's minimal checkpoint test. Adopt TD-08's basic bounds as the worker and recorder are introduced. Deliver a functioning load/advance/command/replay path.
3. **With real libraries and the viewer:** complete TD-06 before expensive runs, make TD-07's renderer choice, and measure TD-08 under longer sessions. Promote unresolved failures to explicit milestone blockers where appropriate.

Do not sum the effort estimates as a schedule: contract work overlaps the architecture integration, and runtime checks overlap feature implementation.

## Deliberate deferrals, not debt to remove now

- ARMI, networking, WebXR and a second renderer remain optional future work.
- The Python/TypeScript split is a justified trade-off if independent checks and contract fixtures keep it maintainable.
- A synthetic library, simple primitive geometry and a local static application are appropriate first-release choices.
- Absent deployment automation and code coverage metrics are not defects before an executable project exists. Add the relevant checks with the first code.
- No evidence currently justifies microservices, a database, a general plugin framework or a broad refactor.

## Verification and limits

Inspected the file inventory and searched the active plans for the cited instructions. Read the current coordination log and prior architecture review. No source code, installed dependency tree or runtime behavior was audited. External versions and licensing claims were not reverified. No executable or end-to-end tests could be run because the project has no implementation. Effort and priority estimates are provisional and should be updated after the first working slice.
