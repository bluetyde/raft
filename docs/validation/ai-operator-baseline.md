# AI operator against a fixed-rule baseline (written 2026-10-07, before the runs except one)

RAFT makes **no claim** that the AI operator (Mica, through the supervisor) does better than anything: the README, `TODO.md` and the docs say only that it runs live (about 60 ms per decision, no errors). This note exists so that no such claim is made without a baseline, after the deep-dive check of `yoyogo96/nuclear-reactor-ai-control`, whose "traditional vs AI" table had no baseline behind it. It reports what the two policies do in one setup. It is not a validation and it supports no sentence like "the AI is better".

## What is compared

Both policies answer the same decision requests of the same runtime (`web/src/runtime/live-mica.test.ts`, run with `JEV_LIVE=1`), which already limits every choice: the runtime builds the candidate list and the policy only picks from it (`supervisor.ts`, `runtime.ts`).

- **model:** Mica (`sky7350/Mica-v0.1-4B`, Q5_K_M, GPU) through `jev-server/server.py`.
- **baseline:** a fixed rule with no model: advance when offered, in the order raise, engage, withdraw, hold, wait, stop; it never lowers the target, inserts a rod or scrams. It answers at once.

## Setup (identical for both)

TRIGA library `triga-jsi-242` (the older M1 library, as the existing live test uses). Start-up by the operator script (`JEV_STARTUP=15`: safety, shim and regulating rods out at 20× for 15 s of wall time), then the supervisor enabled with the goal **10 × the start power**, sim rate 5, 40 s of wall time, and half-way through an instructor reactivity insertion of +3e-5 dk/k. Seeds 1, 2, 3. Each policy is run **once per seed**, 6 runs.

## Metrics (reported as they are, no bands)

Sim time from the supervisor's enabling to 0.9 × the goal; the maximum power over the goal; the trips latched at the end; the number of decisions, the choices, the rod commands the supervisor issued; errors.

## Disclosure and limits

- **One baseline run was seen before this note** (seed 1, written to the results file as that seed's baseline run): it reached the goal 52 s after the supervisor was enabled, overshot to 3.9 × the goal, and the period-short trip latched after the disturbance.
- The loop runs in **wall-clock time**, so simulated time per decision depends on the machine's load (other agents run here); the model answers in tens of milliseconds, the baseline in none. At sim rate 5 that is a fraction of a second of simulated time per decision.
- Three seeds are too few for a difference to mean much; they show whether the two policies behave alike at all. The disturbance is a step of reactivity that can trip `period-short` at once on any policy (known, `m6-instructor-design.md`).
- Not compared: any human operator, the PID alone, other libraries, or other goals.

## Results

Runs: `validation/data/ai-operator-baseline/runs.jsonl` (6 lines, each run once; the seed-1 baseline is the probe run described above). Sim time is from the supervisor being enabled (about 300 s into the simulation) for about 200 s.

| Policy | Seed | To 0.9 × goal (sim s) | Max power / goal | Trip latched at end | Decisions (errors) | Choices | Supervisor rod commands |
|---|---|---|---|---|---|---|---|
| baseline | 1 | 52.0 | 3.94 | period-short | 40 (0) | raise 5, hold 35 | 19 |
| baseline | 2 | 53.3 | 3.94 | period-short | 40 (0) | raise 5, hold 35 | 19 |
| baseline | 3 | 52.4 | 3.94 | period-short | 40 (0) | raise 5, hold 35 | 19 |
| model (Mica) | 1 | 51.8 | 1.17 | period-short | 40 (0) | raise 5, hold 24, stop 8, reduce 3 | 40 |
| model (Mica) | 2 | 50.8 | 1.25 | period-short | 40 (0) | raise 3, hold 31, stop 5, reduce 1 | 28 |
| model (Mica) | 3 | 51.8 | 1.09 | period-short | 40 (0) | raise 3, hold 33, stop 3, reduce 1 | 21 |

## Reading

1. **Time to the goal is the same** (51–53 s) for both policies in this setup.
2. **The model overshoots the goal much less** (1.1–1.25 × against 3.9 ×), by using `stop` and `reduce` that the baseline never picks, at the cost of more rod commands (21–40 against 19).
3. **All six runs ended with `period-short` latched.** The mid-run disturbance (+3e-5 dk/k, a step) trips the true-period trip at once on every policy (the known behaviour in `m6-instructor-design.md`), so this setup says nothing about whether either policy avoids a trip.
4. **What this does not show.** The baseline is deliberately naive (it never lowers, inserts or stops), so beating it is a low bar; a PID-only run (no supervisor choices) was not made. The baseline's overshoot is identical to three digits across seeds (the seed changes only instrument noise and the baseline is otherwise deterministic), which also means three seeds give no spread for it. One library, one goal, one disturbance, wall-clock timing. The model's lower overshoot is a fact about this setup, not a ranking of the operator.
5. **Wording rule.** Nothing in the README or the docs may say the AI operator is better, safer or more accurate than manual operation or a controller. If a claim is wanted, the missing runs are: a PID-only baseline, a disturbance that does not itself trip the reactor, more goals, and a human or scripted-operator reference.

Reproduce: start `jev-server` (`jev-server/venv/Scripts/python.exe jev-server/server.py`), then in `web/`: `JEV_LIVE=1 JEV_POLICY=baseline|model JEV_STARTUP=15 JEV_GOAL_X=10 JEV_SEED=n JEV_SECONDS=40 JEV_RATE=5 JEV_OUT=path npx vitest run src/runtime/live-mica.test.ts` (the baseline needs no server).
