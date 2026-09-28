import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Engine } from "../sim/engine";
import { loadSyntheticCore, repoRoot } from "../sim/testing";
import type { ToWorker } from "./protocol";
import { MAIN_PORT, Runtime } from "./runtime";
import type { ScenarioFile } from "./scenario";
import { FakeHost, loadedRuntime, readFolder, send, syntheticCoreDir } from "./test-helpers";

const DIR = join(repoRoot, "web", "src", "app", "scenarios");
const scenario = (id: string) => JSON.parse(readFileSync(join(DIR, `${id}.json`), "utf8")) as ScenarioFile;
const trigaDir = join(repoRoot, "libraries", "triga-jsi-242");

/** A synthetic scenario with events at t = 0 (step 0) and t = 0.047 s (step 5), and every control allowed. */
function withEvents(): ScenarioFile {
  return {
    ...scenario("synthetic-power-ascension"),
    id: "test-events",
    controls: { allow: ["rod.move", "scram", "trip.reset", "mode.set", "pump.set"] },
    events: [
      { at: 0, cmd: { type: "fault.instrument", instrument: "pool-temp", kind: "stuck" }, note: "stuck thermometer" },
      { at: 0.047, cmd: { type: "rod.move", rod: "safety", direction: "out" }, note: "safety rod out" },
    ],
  };
}

let seq = 1;
const cmd = (rt: Runtime, c: Record<string, unknown>, clientId = "operator") =>
  send(rt, { kind: "command", clientSeq: seq++, clientId, cmd: c });
const state = (rt: Runtime) => {
  const { eventCount: _e, ...cp } = rt.engine!.checkpoint();
  return cp;
};

describe("scenario runtime: scripted events (D2a)", () => {
  it("submits each event at its boundary as a command from 'scenario', and marks it on the timeline", async () => {
    const { host, rt } = await loadedRuntime({}, { scenario: withEvents() });
    // the event at t = 0 is in the log at once
    expect(rt.engine!.commandLog.map((c: any) => [c.step, c.clientId, c.cmd.type])).toEqual([[0, "scenario", "fault.instrument"]]);
    await send(rt, { kind: "step", n: 10 });
    expect(rt.engine!.commandLog.map((c: any) => [c.step, c.clientId, c.cmd.type])).toEqual([
      [0, "scenario", "fault.instrument"],
      [5, "scenario", "rod.move"],
    ]);
    const marks = host.last("timeline")!.marks.filter((m) => m.kind === "scripted");
    expect(marks.map((m) => m.label)).toEqual(["scenario: pool-temp: stuck", "scenario: rod.move"]);
    expect(host.last("scenario")!.scenario!.events).toEqual([
      { step: 0, t: 0, note: "stuck thermometer" },
      { step: 5, t: 0.05, note: "safety rod out" },
    ]);
  });

  it("amendment 3: an event gets its seq when its boundary is reached, before an operator command queued first", async () => {
    const { rt, host } = await loadedRuntime({}, { scenario: withEvents() });
    await send(rt, { kind: "step", n: 4 });
    await send(rt, { kind: "time", rate: 1, paused: false });
    // the operator's command is queued now, while the engine is still at step 4 ...
    rt.receive({ kind: "command", clientSeq: 900, clientId: "operator", cmd: { type: "rod.move", rod: "regulating", direction: "out" } });
    // ... but the clock reaches the event's boundary (step 5) before the worker handles the command
    host.advance(11); // 11 ms at 1x: the clock reaches step 5 (and not step 6)
    await rt.idle();
    expect(rt.engine!.stepIndex).toBe(5);
    const at5 = rt.engine!.commandLog.filter((c: any) => c.step === 5).map((c: any) => [c.clientId, c.seq]);
    expect(at5.map(([id]) => id)).toEqual(["scenario", "operator"]);
    expect(at5[0]![1]).toBeLessThan(at5[1]![1]);
  });

  it("after a rewind before an event, submits it again, and the end state equals a run without the rewind", async () => {
    const a = await loadedRuntime({}, { scenario: withEvents() });
    await send(a.rt, { kind: "step", n: 30 });
    const end = state(a.rt);
    await send(a.rt, { kind: "rewind", step: 2 });
    expect(a.rt.engine!.commandLog.filter((c: any) => c.clientId === "scenario")).toHaveLength(1);
    await send(a.rt, { kind: "step", n: 28 });
    expect(a.rt.engine!.commandLog.filter((c: any) => c.clientId === "scenario")).toHaveLength(2);
    expect(state(a.rt)).toEqual(end);
    // and a rewind to the event's own step keeps it once
    await send(a.rt, { kind: "rewind", step: 5 });
    await send(a.rt, { kind: "step", n: 25 });
    expect(a.rt.engine!.commandLog.filter((c: any) => c.clientId === "scenario")).toHaveLength(2);
    expect(state(a.rt)).toEqual(end);
  });
});

describe("scenario runtime: allowed controls (D4a)", () => {
  it("rejects an operator's command that the scenario does not allow, but not the instructor's", async () => {
    const { host, rt } = await loadedRuntime({}, { scenario: scenario("synthetic-power-ascension") });
    await cmd(rt, { type: "mode.set", mode: "pulse" });
    await cmd(rt, { type: "mode.set", mode: "pulse" }, "explorer");
    await cmd(rt, { type: "rod.move", rod: "safety", direction: "out" });
    await cmd(rt, { type: "mode.set", mode: "steady" }, "instructor");
    await cmd(rt, { type: "scram" }, "scenario");
    await send(rt, { kind: "step", n: 1 });
    // rejections are answered at once and accepted commands after the step, so sort by clientSeq
    const acks = host.of("ack").slice(-5).sort((x, y) => x.clientSeq - y.clientSeq);
    expect(acks.map((a) => a.reason)).toEqual(["REJ_SCENARIO", "REJ_SCENARIO", null, null, "REJ_ROLE"]);
  });

  it("limits an operator window whatever clientId it uses", async () => {
    const host = new FakeHost();
    const rt = new Runtime(host);
    rt.disconnect(MAIN_PORT);
    rt.connect("A");
    rt.connect("B");
    const to = (port: string, msg: ToWorker) => {
      rt.receive(msg, port);
      return rt.idle();
    };
    await to("A", { kind: "attach", role: "full" });
    await to("A", { kind: "load", protocol: 1, source: { kind: "files", files: readFolder(syntheticCoreDir) }, scenario: scenario("synthetic-power-ascension") });
    await to("B", { kind: "attach", role: "operator" });
    await to("B", { kind: "command", clientSeq: 1, clientId: "instructor", cmd: { type: "mode.set", mode: "pulse" } });
    expect(host.seenBy("B", "ack").at(-1)).toMatchObject({ clientSeq: 1, reason: "REJ_SCENARIO" });
    // B also got the scenario on attach
    expect(host.seenBy("B", "scenario").at(-1)!.scenario!.id).toBe("synthetic-power-ascension");
  });
});

describe("scenario runtime: goals (D3a)", () => {
  it("are met on a short pulse peak, although no snapshot saw it", async () => {
    // a reference run finds the largest log reading at a step boundary during the pulse
    const lib = await loadSyntheticCore();
    const vector = JSON.parse(readFileSync(join(repoRoot, "schema", "engine-vectors", "pulse.json"), "utf8"));
    const ref = new Engine(lib, vector.init, 1, { outerDt: 0.01 });
    ref.submit({ type: "rod.fire", rod: "transient" });
    let peak = 0;
    for (let i = 0; i < 100; i++) {
      ref.step();
      peak = Math.max(peak, ref.indicated["log"] as number);
    }
    const pulse: ScenarioFile = {
      ...scenario("synthetic-power-ascension"),
      id: "test-pulse",
      init: vector.init,
      controls: { allow: [] },
      events: [{ at: 0, cmd: { type: "rod.fire", rod: "transient" } }],
      goals: [{ id: "peak", text: "see the peak", check: { signal: "indicated.log", op: "gt", value: 0.9 * peak }, source: "test: 90 % of the reference run's peak" }],
    };
    const { host, rt } = await loadedRuntime({}, { scenario: pulse });
    const snaps = host.of("snapshot").length;
    await send(rt, { kind: "step", n: 100 }); // no frame acks: the runtime sends no more snapshots
    expect(host.of("snapshot").length).toBe(snaps);
    const goal = host.last("scenario")!.scenario!.goals[0]!;
    expect(goal.status).toBe("met");
    expect(goal.t!).toBeLessThan(0.5);
  });

  it("a rewind drops results after the rewind point, and a branch switch brings them back", async () => {
    const { host, rt } = await loadedRuntime({}, { scenario: scenario("synthetic-power-ascension") });
    await cmd(rt, { type: "rod.move", rod: "safety", direction: "out" });
    await cmd(rt, { type: "rod.move", rod: "regulating", direction: "out" });
    await send(rt, { kind: "step", n: 25000 });
    const met = host.last("scenario")!.scenario!.goals;
    expect(met[0]!.status).toBe("met");
    const t = met[0]!.t!;
    // a rewind to after the first checkpoint that follows the first goal (checkpoints every 1000 steps): the goal stays met,
    // at its original time, because the tracker comes from that checkpoint (a fresh tracker would meet it again later)
    await send(rt, { kind: "rewind", step: Math.ceil(t / 10) * 1000 + 100 });
    expect(host.last("scenario")!.scenario!.goals[0]).toEqual(met[0]);
    // a rewind to before it: open again
    await send(rt, { kind: "rewind", step: Math.floor((t - 1) / 0.01) });
    expect(host.last("scenario")!.scenario!.goals[0]!.status).toBe("open");
    await send(rt, { kind: "branch.switch", id: 1 });
    expect(host.last("scenario")!.scenario!.goals).toEqual(met);
  });
});

describe("scenario runtime: the instructor ends a scenario (SC2)", () => {
  async function metFirst() {
    const r = await loadedRuntime({}, { scenario: scenario("synthetic-power-ascension") });
    await cmd(r.rt, { type: "rod.move", rod: "safety", direction: "out" });
    await cmd(r.rt, { type: "rod.move", rod: "regulating", direction: "out" });
    await send(r.rt, { kind: "step", n: 20500 }); // the first goal is met at about 194 s
    return r;
  }

  it("fails the goals not met yet, at that time, and makes the score final", async () => {
    const { host, rt } = await metFirst();
    const t = rt.engine!.t;
    await send(rt, { kind: "scenario.end" });
    const v = host.last("scenario")!.scenario!;
    expect(v.goals.map((g) => g.status)).toEqual(["met", "failed", "failed"]);
    expect(v.goals[1]!.t).toBeCloseTo(t, 9);
    expect(v).toMatchObject({ done: true, score: { met: 1, failed: 2, total: 3, trips: 0 } });
    expect(v.endedAt).toBeCloseTo(t, 9);
    expect(v.score.lastGoalT).toBe(v.goals[0]!.t);
    // the goals stay as they are while time goes on, and a second end changes nothing
    const n = host.of("scenario").length;
    await send(rt, { kind: "step", n: 2000 });
    await send(rt, { kind: "scenario.end" });
    expect(host.of("scenario").length).toBe(n);
  });

  it("a rewind to before the end undoes it; a rewind to after it keeps it", async () => {
    const { host, rt } = await metFirst();
    const endStep = rt.engine!.stepIndex;
    await send(rt, { kind: "scenario.end" });
    const ended = host.last("scenario")!.scenario!;
    await send(rt, { kind: "step", n: 1500 }); // makes a checkpoint after the end (at 22000)
    // after the end, from the checkpoint at 21000 (after it) and from the one at 20000 (before it: the replay applies the end again)
    for (const step of [endStep + 1000, endStep + 300]) {
      await send(rt, { kind: "rewind", step });
      expect(host.last("scenario")!.scenario!).toEqual(ended);
    }
    await send(rt, { kind: "rewind", step: endStep - 10 });
    const v = host.last("scenario")!.scenario!;
    expect(v.endedAt).toBeNull();
    expect(v.goals.map((g) => g.status)).toEqual(["met", "open", "waiting"]);
  });

  it("is an error without a scenario", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "scenario.end" });
    expect(host.last("error")).toMatchObject({ request: "scenario.end", code: "E_NO_SCENARIO" });
  });
});

describe("scenario runtime: session files version 3", () => {
  it("record the scenario and its resolved thresholds, and import only with the same scenario", async () => {
    const sc = withEvents();
    const { host, rt } = await loadedRuntime({}, { scenario: sc });
    await send(rt, { kind: "step", n: 20 });
    await send(rt, { kind: "session.export" });
    const file = host.last("session")!.file;
    expect(file.version).toBe(3);
    expect(file.scenario).toMatchObject({ id: "test-events", thresholds: { "one-percent": 2750, "ten-percent": 27500, hold: [13750, 41250] } });
    expect(file.scenario!.digest).toMatch(/^[0-9a-f]{64}$/);
    const end = state(rt);

    await send(rt, { kind: "session.import", file });
    expect(host.last("error")).toMatchObject({ request: "session.import", code: "E_SESSION" });
    expect(host.last("error")!.message).toContain("import it with that scenario");
    await send(rt, { kind: "session.import", file, scenario: { ...sc, title: "changed" } });
    expect(host.last("error")!.message).toContain("does not match");
    const errors = host.of("error").length;
    await send(rt, { kind: "session.import", file, scenario: sc });
    expect(host.of("error")).toHaveLength(errors);
    expect(state(rt)).toEqual(end);
    expect(host.last("scenario")!.scenario!.id).toBe("test-events");
    // the imported session goes on: the events are not submitted twice
    await send(rt, { kind: "step", n: 5 });
    expect(rt.engine!.commandLog.filter((c: any) => c.clientId === "scenario")).toHaveLength(2);
  });

  it("a load without a scenario ends the scenario", async () => {
    const { host, rt } = await loadedRuntime({}, { scenario: withEvents() });
    await send(rt, { kind: "load", protocol: 1, source: { kind: "files", files: readFolder(syntheticCoreDir) } });
    expect(host.last("scenario")!.scenario).toBeNull();
  });

  it("an invalid scenario fails the load with the validator's codes", async () => {
    const host = new FakeHost();
    const rt = new Runtime(host);
    await send(rt, { kind: "load", protocol: 1, source: { kind: "files", files: readFolder(syntheticCoreDir) }, scenario: { ...withEvents(), outerDt: 2 } });
    expect(rt.engine).toBeNull();
    expect(host.last("loadFailed")!.issues.map((i) => i.code)).toContain("E_SCN_COARSE");
  });
});

// ---- headless runs of every shipped scenario (WORKFLOWS §4), with a scripted operator ----

type Op = (c: Record<string, unknown>) => Promise<void>;

/** Run a scenario on the runtime, with `operator` acting every 0.1 s of sim time, until every goal is met or failed. */
async function play(files: Record<string, ArrayBuffer>, sc: ScenarioFile, operator: (e: Engine, goals: string[], op: Op) => Promise<void>) {
  const host = new FakeHost();
  const rt = new Runtime(host);
  await send(rt, { kind: "load", protocol: 1, source: { kind: "files", files }, scenario: sc });
  if (!rt.engine) throw new Error(JSON.stringify(host.last("loadFailed")));
  let n = 1;
  const op: Op = (c) => send(rt, { kind: "command", clientSeq: n++, clientId: "operator", cmd: c });
  const view = () => host.last("scenario")!.scenario!;
  while (!view().done && rt.engine.t < 4000) {
    await operator(rt.engine, view().goals.filter((g) => g.status === "met").map((g) => g.id), op);
    await send(rt, { kind: "step", n: 10 });
  }
  return { view: view(), rejected: host.of("ack").filter((a) => a.status === "rejected") };
}

/** Withdraw the large rods, then hold 20-30 kW with the regulating rod (the power-ascension operator). */
function ascensionOperator() {
  let started = false;
  let reg = "";
  return async (e: Engine, _goals: string[], op: Op) => {
    if (!started) {
      started = true;
      for (const r of e.lib.rods) if (r.id !== "transient" && r.id !== "regulating") await op({ type: "rod.move", rod: r.id, direction: "out" });
    }
    if (e.t < 51) return;
    const lin = e.indicated["linear"] as number;
    const per = e.snapshot().truth.period; // stands in for the operator watching the period
    let want = "stop";
    if (lin < 20000 && (per > 20 || per < 0)) want = "out";
    if (lin > 30000 || (per > 0 && per < 10)) want = "in";
    if (want !== reg) {
      reg = want;
      await op({ type: "rod.move", rod: "regulating", direction: want });
    }
  };
}

/** All rods but the transient rod out; scram when the steady hold is met; reset and restart when the period has settled. */
function scramOperator() {
  let phase = 0;
  return async (e: Engine, goals: string[], op: Op) => {
    const out = async () => {
      for (const r of e.lib.rods) if (r.id !== "transient") await op({ type: "rod.move", rod: r.id, direction: "out" });
    };
    if (phase === 0) {
      phase = 1;
      await out();
    } else if (phase === 1 && goals.includes("steady")) {
      phase = 2;
      await op({ type: "scram" });
    } else if (phase === 2 && goals.includes("negative-period")) {
      phase = 3;
      await op({ type: "trip.reset" });
      await out();
    }
  };
}

describe("headless runs of the shipped scenarios", () => {
  for (const [id, lib] of [
    ["synthetic-power-ascension", "synthetic"],
    ["triga-power-ascension", "triga"],
    ["synthetic-scram-and-restart", "synthetic"],
    ["triga-scram-and-restart", "triga"],
  ] as const) {
    it(`${id}: a scripted operator meets every goal, with no unexpected trip`, async () => {
      const files = lib === "synthetic" ? readFolder(syntheticCoreDir) : readFolder(trigaDir);
      const operator = id.includes("ascension") ? ascensionOperator() : scramOperator();
      const { view, rejected } = await play(files, scenario(id), operator);
      expect(view.goals.map((g) => [g.id, g.status])).toEqual(view.goals.map((g) => [g.id, "met"]));
      const last = Math.max(...view.goals.map((g) => g.t!));
      expect(view.score).toEqual({ met: view.goals.length, failed: 0, total: view.goals.length, trips: 0, lastGoalT: last });
      expect(view.endedAt).toBeNull();
      expect(rejected).toEqual([]);
    }, 120_000);
  }
});

