# M8 step 5, the dilution-to-critical lesson: plan (2026-10-10)

The supported lesson of the PWR library `pwr-beavrs-hzp-openmc`: **approach to criticality by dilution at hot zero power**. Status: plan only; nothing built. The lesson is one scenario file plus tests and notes; it needs no engine change and no new envelope kind.

## 1. What the lesson is

The reactor starts shut down by boron alone: all banks at the benchmark configuration (bank D at step 213, the others out), 1100 ppm, 566.5 K, source in the core. The operator lowers the boron concentration with `boron.set` (the plant moves it at most 0.1 ppm/s) until the reactor is critical, then stops the rise and holds. The rods are not part of the lesson (`controls.allow`: `boron.set`, `scram`), which keeps every state at the one rod configuration the library reproduces (the summed bank tables are not reliable with several banks in; `libraries/pwr-beavrs-hzp-openmc/README.md`).

What the learner should see: the log channel rises slowly while the reactor is far subcritical (the source multiplication, `P = S·Λ/|ρ|`), faster as it nears critical, and then exponentially once past it; the period shortens; the startup-rate trip (`period-short`, 10 s, assumed) scrams the reactor if the dilution goes on. The right answer is to stop diluting when the power rises faster than expected, then add a little boron back to hold.

## 2. Numbers from a run of the library (Python reference engine, outer step 1 s, boron target 900 ppm, 2026-10-10)

| Start boron | Source-level power | Critical (ρ = 0) | Power at critical | Trip |
|---|---|---|---|---|
| 1100 ppm (ρ −1435 pcm) | 4.1 mW | 983.2 ppm, after 1170 s (19.5 min) | 0.09 W | `period-short` at about 967 ppm, 22 W and a 13 s period at 1330 s, scram by about 1350 s |
| 1500 ppm (ρ −6295 pcm) | 0.9 mW | same 983.2 ppm, after 5200 s (87 min) | 0.15 W | same |

So from 1100 ppm the whole lesson is about 20 minutes at 1×, and the student has about 160 s between critical and the trip at full dilution rate. The 1.7 MW `zero-power-limit` trip is never the one that acts in a dilution. Power thresholds relate to reactivity like this (from the same run): above 0.05 W means within about 100 pcm (8 ppm) of critical; above 0.3 W means about +50 pcm; above 2 W means about +150 pcm (a 21 s period).

## 3. The scenario file `web/src/app/scenarios/pwr-beavrs-hzp-dilution.json`

- `library: pwr-beavrs-hzp-openmc`, `outerDt: 1` (no pulses; the coarse step is allowed), `seed: 1`, `init: { rods: "reference", boron: 1100 }` (source equilibrium works because ρ < 0), `controls.allow: ["boron.set", "scram"]`, no events, no `expectTrips`.
- Goals (the log channel, `indicated.log`, in W; the numbers carry `source: "this lesson, from the run in section 2"`):
  1. **approach**: raise the power above 0.05 W (about ten times the starting level), within 2400 s.
  2. **critical**: raise it above 0.3 W, after 1, within 600 s. (This is the critical goal; the check cannot use ρ, which no instrument shows.)
  3. **hold**: hold the power between 0.3 W and 30 W for 5 minutes, after 2, within 900 s. Stopping the dilution is not enough (the power keeps rising a little past critical); the learner has to put some boron back.
  4. **boron** (scored, uses the one boron-valued signal a goal may read, `truth.boron`): the boron concentration is between 970 and 990 ppm at the end of the hold (critical is 983.2 in the library; the benchmark's measured critical boron at this configuration is 975 ppm; the band covers both).
  Failure of goal 3 by a trip is visible as the annunciator and the failed goal.
- `envelope`: summary "Approach to criticality by dilution and a hold at zero power; rods stay at the benchmark configuration; boron 900 to 1300 ppm; no power operation"; power limit from the `zero-power-limit` trip times 6e-5 (about 100 W, source: this lesson); fuel temperature 575 K (source: hot zero power, the fuel stays within a few K of 566.5); modes `["steady"]`; `knownLimits`: the temperature feedback is not validated (isothermal coefficient 1.6 to 2.0 pcm/°F too negative against the benchmark, `m8-beavrs-hzp-results.md`), the dilution rate, the trip setpoints and the neutron source strength are assumed (they set the pace and the starting power, not the critical concentration), and the library's critical boron is 8 ppm above the measured one.
- `brief` and `hints` in plain words (what the log channel shows, why the period shortens, "the rods do not move in this lesson", "boron moves at 0.1 ppm/s up or down").

## 4. Work, in order

1. **Scenario file** and its entry in the shipped-scenarios test (every shipped file is checked against its library).
2. **Three scripted runs as tests** (the runtime pattern of `scenario-runtime.test.ts` and `boron-runtime.test.ts`): a careful run (dilute to 985, watch, back off, hold) meets goals 1 to 4; a reckless run (target 900) trips `period-short` and fails goal 3; an idle run fails goal 1 on time. Each run once, thresholds fixed beforehand in this plan, a failed check is reported, not tuned away.
3. **Browser check**: load the scenario, run it at 1× and at a faster time rate, look at the log chart, the period, the goals and the banner; screenshot for the notes.
4. **Notes**: an entry in `docs/validation/supported-envelope.md` (replace "no supported lesson yet" in the PWR section: the lesson, what it claims — the critical concentration at this one rod configuration, within 8 ppm of the measured one, from the library — and what it does not), the library README, `TODO.md`, the shared log.
5. **Codex review** of the scenario and tests.

About half a day for 1 to 4.

## 5. Not in this step, and open points

- The **AI Copilot** has no boron action, so it cannot do this lesson; the scenario has no AI goal. Adding a boron action to the policy is a separate job (the classifier's action list and its training are fixed).
- The lesson claims nothing about temperature feedback, power operation, xenon, decay heat or pressure; the library stays `experimental`.
- A **1/M plot** (inverse source-range rate against boron, the real practice for predicting the critical concentration) would teach more than the goals do. It needs a new chart, so it is not in this step; `TODO.md` gets a line.
- Step 6 (a comparison of the two libraries) is a separate protocol and is not started here.

## 6. Decisions I need from you

1. **Start boron**: 1100 ppm (20 minutes, recommended) or 1200 (30 minutes, a deeper start).
2. **Goal 4** (the scored boron band 970 to 990 ppm): keep (recommended; it makes the learner estimate the critical concentration) or drop (goals 1 to 3 only, which test the handling but not the estimate).
3. **Hold length**: 5 minutes (recommended) or 2 minutes as in the TRIGA lesson.
