# Headless runner

A command-line way to run the simulation engine without a browser, written for SEED's adapter (bluetyde/seed, `docs/inventory.md`) but usable on its own. It adds files only: `web/src/headless/` and `web/vite.headless.config.ts`. The engine, runtime, library loader and UI are unchanged.

Status (2026-10-03): working on the synthetic core library; every golden vector in `schema/engine-vectors/` runs through it and agrees within the vectors' own tolerances. Not yet used by SEED. Not validated on any library other than `schema/vectors/synthetic-core`.

## Build and use

```
cd web
npm ci
npm run build:headless          # writes web/dist-headless/raft-headless.mjs (Node 24, one file, not committed)
node dist-headless/raft-headless.mjs describe
node dist-headless/raft-headless.mjs validate <case.json>
node dist-headless/raft-headless.mjs run <case.json> --out <folder> [--run-id <id>]
node dist-headless/raft-headless.mjs replay <run folder>
```

Every verb prints one JSON object on stdout. Exit status: 0 succeeded; 1 the run ended `failed` or the replay differs; 2 the input was refused or the usage is wrong. Refusals are `{ok: false, errors: [{code, field, message}]}` and create no run folder.

## Case file (`raft-headless-case`, version 1)

The shape of an engine golden vector plus a library path, so a vector is also a case:

| Field | Meaning |
|---|---|
| `format`, `version` | `"raft-headless-case"`, `1` |
| `library` | library folder, relative to the case file, forward slashes, no `..` |
| `seed` | integer 0 to 2^53-1 |
| `init`, `config` | passed to the engine unchanged (optional, default `{}`) |
| `steps` | 1 to 2,000,000 engine steps (`outerDt` each, default 0.01 s) |
| `sampleEvery` | record a sample every N steps (first and last always) |
| `script` | up to 10,000 `{step, cmd, clientId?}`; `step` before `steps`; `clientId` defaults to `"headless"`; `cmd` is an engine command (`schema/command.schema.json`) |

Unknown fields are refused. A command the engine rejects (unknown command, tripped, interlock) is not an error: it appears in `events` with its reason.

## Run folder

```
<out>/<runId>/case.json      byte copy of the case
<out>/<runId>/results.json   samples, events, final values, pins; no clock or path, so one case gives the same bytes
<out>/<runId>/session.json   engine session (pins, seed, init, command log)
<out>/<runId>/manifest.json  written first with status "running", rewritten last with the final status and sha256 of each file
```

Statuses: `running` (a manifest that still says this belongs to an interrupted run), `completed`, `failed` (engine error, engine halt such as a rejecting table, or a non-finite sample; the partial samples are kept and the reason is recorded). A trip is an event, not an end: the run continues and the trip stays visible in `samples[].latched` and `events`.

`replay` re-runs a completed run from `session.json`, checks every file against the manifest hashes, and compares the final sample and peak exactly with `results.json`.

## Limits

- Units come from the library manifest; the runner converts nothing.
- `fault.rod` is implemented in the engine but missing from `schema/command.schema.json`, so `describe` does not list it (a pre-existing gap, not changed here).
- Cancelling is killing the process; the manifest then still says `running`.
- The runner does not read the browser runtime, scenarios, instructor scripts or the AI supervisor.
