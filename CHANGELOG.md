# Changelog

RAFT follows [semantic versioning](https://semver.org/) for the app and the library format as a pair: a change that makes an existing library invalid or changes an engine result is a new minor version while the format is 0.x. The reference engine has its own number (it moves when a golden vector changes) and is pinned by the vectors.

## 0.1.0 (the first public release; not yet tagged)

Experimental and educational. No library is marked validated.

**Simulator**
- Point kinetics with six delayed-neutron groups, a lumped fuel and coolant node, and reactivity as a sum of tables from a library; a Python reference engine (`physics_ref`) and a TypeScript engine (`web/src/sim`) that agree on 11 golden vectors. Engine 0.7.1.
- Library format 0.1.0 (`docs/library-format.md`) with capabilities: lumped thermal v1 and v2 (hA depends on the temperature difference), soluble boron, rod interaction v1 (a correction on the summed rod worth) and rod interaction v2 (each rod's worth scaled by the others, "shadowing"). A validator in Python and TypeScript (55 invalid fixtures). A checked state in `domain.jointChecked` can carry a boron window, so a state checked at one concentration is not reported as checked at another.
- A runtime with a worker, two-window sessions, replay and rewind, an operator panel (instruments, annunciator, rods, boron, SCRAM), an instructor panel (time, scenarios, faults, notes, branches, export), and a 3D core view.
- Scenarios with goals, a score and an envelope that says what a lesson claims.
- An optional local assistant (`jev-server/`, not needed for anything else).

**Libraries** (`libraries/`)
- TRIGA Mark II (Jožef Stefan Institute) cores 242 and 246 built with OpenMC, core 134 (not in the app), an earlier core 242 library, and a synthetic test core.
- PWR at hot zero power (BEAVRS cycle 1), 193 assemblies, nine rod banks, boron, with a rod-shadowing correction fitted to 12 transport cases and checked against 20 held-out cases (19 converged).

**Lessons**
- TRIGA: low-power ascension, scram and restart.
- PWR: approach to criticality by boron dilution, and by bank withdrawal (banks D and C in, 900 ppm).

**Validation** (`docs/validation/`, `docs/oracles.md`)
- Sixteen dated protocols, each written before its run, each run once, nothing refitted: TRIGA power ascension, heat transfer, hot element and core 134; BEAVRS hot zero power against the measured physics tests; the Doppler-defect benchmark (Mosteller, 15 of 15 computed cases within 10 %); the rod-worth work (a single-axis table failed against held-out cases; the shadowing model passed 9 of 13; the near-critical lesson states 6 of 7).
- What failed is recorded with what passed: the temperature coefficient of the PWR library does not follow the rods, and the TRIGA fuel feedback is 15 to 18 % weak.

**Not in this release**: power operation, xenon worth, decay heat, pulse mode for the PWR, and anything validated.
