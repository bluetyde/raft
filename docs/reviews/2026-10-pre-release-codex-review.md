# Pre-release review by a second model (2026-10)

Before a first public release the whole repository was reviewed by Codex (OpenAI), because a different model catches what the author's model is blind to. This note says how it was done, what came out and what was done about it. The raw review texts are not included because they carry paths from the temporary clones the reviewer used.

## Method

- 20 separate reviews, each over one part of the repository (engines, library pipeline in three parts, other pipeline code, provenance and documentation in two parts, runtime in three parts, security boundaries in two parts, validation scripts in four parts, views in two parts). Each was kept under the size one review can take.
- Each review used one narrow auditor: consistency (documents and code that disagree), silent failure (errors that are swallowed), security boundary (input and network) or specification gap (a protocol that the code does not follow).
- The author checked each finding against the code before changing anything; some were judged not worth a change (below).

## What was found, by area, and what was done

| Area | Typical findings | Done |
|---|---|---|
| Engines (Python and TypeScript) | Non-finite states and zero or negative step settings were accepted; the boron window was enforced in one engine only; the two engines differed in fault handling | Guards and the window in both engines, engine version 0.7.1, new tests that fail when the guard is removed |
| Library validators and exporters | Gaps in the checks (axes, intervals, complete rod deltas, negative uncertainties, unsafe relative paths); the TRIGA exporter listed held-out cases that had failed; the BEAVRS exporter omitted the shape limit | Both validators tightened (63 invalid fixtures), exporters corrected, libraries rebuilt, errata in the results notes |
| Assistant server | Listened on all interfaces, accepted any web page, unbounded requests | Local only by default, origin check, size and count limits, one inference at a time, pinned requirements |
| Runtime and client | Session import unbounded; a failing server read as a missing file; waiting requests never rejected when the worker stopped; supervision could be taken over by a second window; a branch switch lost the scenario end | Fixed, with tests |
| Views | Panels kept receiving updates after they closed; the assistant could wait for ever; pump faults and sensor excursions not shown; export errors swallowed | Fixed, with tests |
| Validation scripts | Several analyses followed the protocol loosely (a volume mean without some bins, a decision read on the primary line instead of the worst over sensitivities, a case not computed hiding in a summary, core 246 dollars divided by core 242's delayed fraction) | Scripts corrected and rerun on the stored data; none of the reported decisions changed; every number that moved is in an erratum at the end of its results note |
| Provenance and documentation | Claims in the README and library notes that went beyond the evidence | Reworded; the README now says how the project was made, including the use of AI tools |

## Open after this review

- Some runtime edge cases are not changed: a rewind while the AI is moving a rod, goals dated in the past, a goal and a script finishing on the same step, the timeout clock while paused, the default duration of a hold goal. They are not expected to change a physics result; they can produce a surprising lesson score. They are listed in `TODO.md`.
- The older `triga-jsi-242` library (mostly assumed values) is still shipped, because two lessons were tuned to it and moving them to the OpenMC library means retuning them. The README says what it is.
- The measured-data comparisons for the TRIGA cores cannot be rerun by a reader of this repository, because the data are not redistributed; the validation notes quote what they used.
- A reviewer reading the code cannot replace a physicist reading the physics. No library is validated.
