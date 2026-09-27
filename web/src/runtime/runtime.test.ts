import { afterEach, describe, expect, it, vi } from "vitest";
import { Engine } from "../sim/engine";
import { comparable, loadSyntheticCore } from "../sim/testing";
import { nearCriticalRods } from "../sim/vectors";
import { CheckpointStore } from "./history";
import { Runtime } from "./runtime";
import { FakeHost, invalidDir, loadedRuntime, readFolder, send, syntheticCoreDir } from "./test-helpers";

afterEach(() => {
  vi.restoreAllMocks();
});

/** Make every engine step cost `ms` of the fake host's wall time. */
function slowSteps(host: FakeHost, ms: number): void {
  const orig = Engine.prototype.step;
  vi.spyOn(Engine.prototype, "step").mockImplementation(function (this: Engine) {
    orig.call(this);
    host.t += ms;
  });
}

const DT = 0.01; // the synthetic core runs with the engine's default outerDt

describe("loading", () => {
  it("loads the synthetic core paused at step 0 and reports pins", async () => {
    const { host, rt } = await loadedRuntime();
    const loaded = host.last("loaded")!;
    expect(loaded.libraryId).toBe("synthetic-core");
    expect(loaded.outerDt).toBe(DT);
    expect(loaded.pins.libraryDigest).toBe(loaded.digest);
    expect(rt.engine!.stepIndex).toBe(0);
    expect(host.last("clock")!.paused).toBe(true);
    expect(host.of("snapshot")).toHaveLength(1);
    expect(host.last("history")!.checkpointSteps).toEqual([0]);
  });

  it.each([
    ["digest-mismatch", "E_DIGEST_MISMATCH"],
    ["bad-json", "E_JSON"],
  ])("a malformed library (%s) gives loadFailed with the validator's code", async (fixture, code) => {
    const host = new FakeHost();
    const rt = new Runtime(host);
    await send(rt, { kind: "load", protocol: 1, source: { kind: "files", files: readFolder(invalidDir(fixture)) } });
    expect(rt.engine).toBeNull();
    expect(host.of("loaded")).toHaveLength(0);
    expect(host.last("loadFailed")!.issues.map((i) => i.code)).toContain(code);
  });

  it("a failed load keeps the previous engine, paused, and says so", async () => {
    const { host, rt } = await loadedRuntime();
    const before = rt.engine;
    await send(rt, { kind: "time", paused: false });
    host.advance(100);
    await send(rt, { kind: "load", protocol: 1, source: { kind: "files", files: readFolder(invalidDir("bad-json")) } });
    expect(rt.engine).toBe(before);
    expect(host.last("clock")!.paused).toBe(true);
    const at = rt.engine!.stepIndex;
    host.advance(500);
    expect(rt.engine!.stepIndex).toBe(at);
  });

  it("an impossible initial state gives loadFailed with the engine's E_INIT code", async () => {
    const host = new FakeHost();
    const rt = new Runtime(host);
    const files = readFolder(syntheticCoreDir);
    await send(rt, {
      kind: "load",
      protocol: 1,
      source: { kind: "files", files },
      init: { power: { mode: "critical-equilibrium", value: 1 } },
    });
    expect(host.last("loadFailed")!.issues[0]!.code).toBe("E_INIT_NO_EQUILIBRIUM");
  });

  it("uses the session's outerDt from the load config (D1: T2)", async () => {
    const { host, rt } = await loadedRuntime({}, { config: { outerDt: 0.5 } });
    expect(host.last("loaded")!.outerDt).toBe(0.5);
    await send(rt, { kind: "step", n: 4 });
    expect(rt.engine!.t).toBe(2);
  });
});

describe("clock", () => {
  it.each([1, 10, 100])("follows rate x wall time at rate %d and never runs ahead", async (rate) => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "time", rate, paused: false });
    for (let i = 0; i < 10; i++) {
      host.advance(100);
      expect(rt.engine!.t).toBeLessThanOrEqual((rate * host.t) / 1000 + 1e-9);
    }
    expect(rt.engine!.t).toBeCloseTo(rate * 1, 1);
    expect(host.last("clock")!.achievedRate).toBeCloseTo(rate, -Math.log10(rate) + 1);
    expect(host.last("clock")!.limited).toBeNull();
  });

  it("with a slow engine it runs slower, skips no step, and reports limited: cpu", async () => {
    const { host, rt } = await loadedRuntime();
    slowSteps(host, 1); // 1 ms per 10 ms step: at most 10x
    await send(rt, { kind: "time", rate: 100, paused: false });
    host.advance(3000);
    const clock = host.last("clock")!;
    expect(clock.limited).toBe("cpu");
    expect(clock.achievedRate).toBeGreaterThan(8);
    expect(clock.achievedRate).toBeLessThan(10.5);
    // every step ran: the engine's own diagnostics count one outer step per call
    expect(rt.engine!.t).toBeCloseTo(rt.engine!.stepIndex * DT, 9);
    expect(rt.engine!.stepIndex).toBeGreaterThan(2400);
  });

  it("does not step while paused, and step n runs exactly n steps", async () => {
    const { host, rt } = await loadedRuntime();
    host.advance(1000);
    expect(rt.engine!.stepIndex).toBe(0);
    await send(rt, { kind: "step", n: 7 });
    expect(rt.engine!.stepIndex).toBe(7);
    await send(rt, { kind: "time", paused: false });
    await send(rt, { kind: "step", n: 1 });
    expect(host.last("error")).toMatchObject({ request: "step", code: "E_RUNNING" });
    await send(rt, { kind: "time", paused: true });
    const at = rt.engine!.stepIndex;
    host.advance(1000);
    expect(rt.engine!.stepIndex).toBe(at);
  });

  it("a rate change keeps sim time continuous", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "time", rate: 1, paused: false });
    host.advance(500);
    const t0 = rt.engine!.t;
    await send(rt, { kind: "time", rate: 10 });
    host.advance(10);
    expect(rt.engine!.t - t0).toBeLessThanOrEqual(0.1 + 1e-9);
    host.advance(490);
    expect(rt.engine!.t).toBeCloseTo(t0 + 5, 1);
  });

  it("rejects a bad rate", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "time", rate: 0 });
    expect(host.last("error")).toMatchObject({ request: "time", code: "E_BAD_RATE" });
  });
});

describe("commands", () => {
  it("before a load: REJ_NO_LIBRARY", async () => {
    const host = new FakeHost();
    const rt = new Runtime(host);
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "scram" } });
    expect(host.last("ack")).toMatchObject({ clientSeq: 1, seq: null, status: "rejected", reason: "REJ_NO_LIBRARY" });
  });

  it("a structural error: REJ_SCHEMA at once, and the engine never sees it", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "command", clientSeq: 5, clientId: "op", cmd: { type: "rod.move", rod: "safety" } });
    expect(host.last("ack")).toMatchObject({ clientSeq: 5, seq: null, status: "rejected", reason: "REJ_SCHEMA" });
    expect(rt.engine!.commandLog).toHaveLength(0);
    expect(host.of("queued")).toHaveLength(0);
  });

  it("while paused (D2: a): queued at the boundary, applied and acknowledged on the next step", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "step", n: 3 });
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "rod.move", rod: "regulating", direction: "out" } });
    expect(host.last("queued")).toMatchObject({ clientSeq: 1, seq: 1, step: 3 });
    expect(host.of("ack")).toHaveLength(0);
    host.advance(1000);
    expect(host.of("ack")).toHaveLength(0);
    await send(rt, { kind: "step", n: 1 });
    expect(host.last("ack")).toMatchObject({ clientSeq: 1, seq: 1, status: "accepted", reason: null });
    expect(host.last("ack")!.t).toBeCloseTo(3 * DT, 12);
    expect(rt.engine!.snapshot().truth.rods.regulating.moving).toBe("out");
  });

  it("passes the engine's reject reason through unchanged", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "command", clientSeq: 9, clientId: "op", cmd: { type: "rod.move", rod: "ghost", direction: "out" } });
    await send(rt, { kind: "step", n: 1 });
    expect(host.last("ack")).toMatchObject({ clientSeq: 9, status: "rejected", reason: "REJ_UNKNOWN_ROD" });
  });

  it("while running: applied at the next boundary the worker reaches", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "time", rate: 1, paused: false });
    host.advance(205);
    const step = rt.engine!.stepIndex;
    await send(rt, { kind: "command", clientSeq: 2, clientId: "op", cmd: { type: "scram" } });
    host.advance(50);
    expect(host.last("queued")!.step).toBe(step);
    expect(host.last("ack")).toMatchObject({ clientSeq: 2, status: "accepted" });
    expect(host.last("ack")!.t).toBeCloseTo(step * DT, 12);
  });
});

describe("determinism (main oracle)", () => {
  it("a session with rates, pauses, commands and a rewind ends in the same state as Engine.replay and a plain loop", async () => {
    const L = await loadSyntheticCore();
    const init = { rods: nearCriticalRods(L, -0.0005) };
    const { host, rt } = await loadedRuntime({ checkpointEveryS: 0.5 }, { init, seed: 7 });
    const cmd = (clientSeq: number, c: Record<string, unknown>) =>
      send(rt, { kind: "command", clientSeq, clientId: "op", cmd: c });

    await send(rt, { kind: "time", rate: 1, paused: false });
    host.advance(137);
    await cmd(1, { type: "rod.move", rod: "transient", direction: "out" });
    await send(rt, { kind: "time", rate: 7 });
    host.advance(333);
    await cmd(2, { type: "fault.instrument", instrument: "log", kind: "stuck" });
    await send(rt, { kind: "time", paused: true });
    await cmd(3, { type: "rod.move", rod: "transient", direction: "stop" });
    await send(rt, { kind: "step", n: 13 });
    await send(rt, { kind: "time", rate: 3, paused: false });
    host.advance(420);
    await cmd(4, { type: "rod.move", rod: "regulating", direction: "in" });
    host.advance(250);
    await send(rt, { kind: "time", paused: true });
    // rewind to a step between commands 3 and 4, then continue with a different action
    const q = host.of("queued");
    const back = Math.floor((q[2]!.step + q[3]!.step) / 2);
    await send(rt, { kind: "rewind", step: back });
    expect(rt.engine!.stepIndex).toBe(back);
    await cmd(5, { type: "scram" });
    await send(rt, { kind: "time", rate: 20, paused: false });
    host.advance(300);
    await send(rt, { kind: "time", paused: true });

    const e = rt.engine!;
    const log = e.commandLog;
    expect(log.map((c: any) => c.cmd.type)).toEqual(["rod.move", "fault.instrument", "rod.move", "scram"]);

    const replayed = Engine.replay(L, e.session(), e.stepIndex);
    expect(comparable(replayed.checkpoint())).toEqual(comparable(e.checkpoint()));

    const plain = new Engine(L, init, 7);
    let k = 0;
    while (plain.stepIndex < e.stepIndex) {
      while (k < log.length && log[k].step === plain.stepIndex) plain.submit(log[k].cmd, log[k].clientId), k++;
      plain.step();
    }
    expect(comparable(plain.checkpoint())).toEqual(comparable(e.checkpoint()));
  });
});

describe("history", () => {
  it("a stored checkpoint without its log rebuilds to exactly the original", async () => {
    const { rt } = await loadedRuntime();
    for (let i = 0; i < 5; i++) {
      await send(rt, { kind: "command", clientSeq: i, clientId: "op", cmd: { type: "rod.move", rod: "regulating", direction: i % 2 ? "in" : "out" } });
      await send(rt, { kind: "step", n: 3 });
    }
    const e = rt.engine!;
    const store = new CheckpointStore(4);
    const original = e.checkpoint();
    store.add(original);
    // later commands must not leak into the rebuilt checkpoint
    e.submit({ type: "scram" }, "op");
    expect(store.atOrBefore(e.stepIndex, e.commandLog)).toEqual(original);
  });

  it("thinning keeps the first and the latest checkpoints within the limit", () => {
    const store = new CheckpointStore(8);
    for (let s = 0; s <= 100; s++) store.add({ stepIndex: s, nextSeq: 1, commandLog: [] });
    const steps = store.steps();
    expect(steps.length).toBeLessThanOrEqual(8);
    expect(steps[0]).toBe(0);
    expect(steps.at(-1)).toBe(100);
    expect(store.thinned).toBe(true);
  });

  it("rewind gives the state the run had at that step, and truncates later commands (D3: a)", async () => {
    const { host, rt } = await loadedRuntime({ checkpointEveryS: 0.3 });
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "rod.move", rod: "transient", direction: "out" } });
    await send(rt, { kind: "step", n: 50 });
    const at50 = rt.engine!.checkpoint();
    await send(rt, { kind: "step", n: 7 });
    await send(rt, { kind: "command", clientSeq: 2, clientId: "op", cmd: { type: "rod.move", rod: "transient", direction: "stop" } });
    await send(rt, { kind: "step", n: 80 });
    await send(rt, { kind: "command", clientSeq: 3, clientId: "op", cmd: { type: "scram" } }); // still pending

    // between commands: exactly the state the run had at step 50
    await send(rt, { kind: "rewind", step: 50 });
    expect(comparable(rt.engine!.checkpoint())).toEqual(comparable(at50));
    // the rewind point cannot move forward again: command 2's timeline is gone
    await send(rt, { kind: "rewind", step: 57 });
    expect(host.last("error")).toMatchObject({ request: "rewind", code: "E_BAD_ARGUMENT" });
    expect(host.last("ack")).toMatchObject({ clientSeq: 3, status: "rejected", reason: "REJ_REWOUND" });
    const rewound = host.last("rewound")!;
    expect(rewound.step).toBe(50);
    expect(rewound.previous.endStep).toBe(137);
    expect(rewound.previous.session.commands).toHaveLength(3);
    expect(Math.max(...host.last("history")!.checkpointSteps)).toBeLessThanOrEqual(50);
    expect(host.last("snapshot")!.shape).toBeInstanceOf(Float32Array);
  });

  it("rewind to a step where a command was sent keeps that command queued, like Engine.replay", async () => {
    const L = await loadSyntheticCore();
    const { host, rt } = await loadedRuntime({ checkpointEveryS: 0.3 });
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "rod.move", rod: "transient", direction: "out" } });
    await send(rt, { kind: "step", n: 57 });
    await send(rt, { kind: "command", clientSeq: 2, clientId: "op", cmd: { type: "rod.move", rod: "transient", direction: "stop" } });
    await send(rt, { kind: "step", n: 80 });
    await send(rt, { kind: "rewind", step: 57 });
    const previous = host.last("rewound")!.previous;
    expect(comparable(rt.engine!.checkpoint())).toEqual(comparable(Engine.replay(L, previous.session, 57).checkpoint()));
    expect(rt.engine!.pending.map((c: any) => c.seq)).toEqual([2]);
  });

  it("rewind to the current step keeps a pending command", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "step", n: 20 });
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "scram" } });
    await send(rt, { kind: "rewind", step: 20 });
    await send(rt, { kind: "step", n: 1 });
    expect(host.last("ack")).toMatchObject({ clientSeq: 1, status: "accepted" });
  });

  it("rejects a rewind into the future", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "rewind", step: 5 });
    expect(host.last("error")).toMatchObject({ request: "rewind", code: "E_BAD_ARGUMENT" });
  });

  it("session export then import gives the same state; a wrong digest is refused", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "rod.move", rod: "transient", direction: "out" } });
    await send(rt, { kind: "step", n: 40 });
    await send(rt, { kind: "command", clientSeq: 2, clientId: "op", cmd: { type: "scram" } });
    await send(rt, { kind: "step", n: 25 });
    await send(rt, { kind: "session.export" });
    const file = host.last("session")!.file;
    const before = rt.engine!.checkpoint();

    const other = await loadedRuntime();
    await send(other.rt, { kind: "session.import", file });
    expect(comparable(other.rt.engine!.checkpoint())).toEqual(comparable(before));
    expect(other.host.last("history")!.checkpointSteps[0]).toBe(0);

    const bad = structuredClone(file);
    bad.session.pins.libraryDigest = "0".repeat(64);
    const at = other.rt.engine!;
    await send(other.rt, { kind: "session.import", file: bad });
    expect(other.host.last("error")).toMatchObject({ request: "session.import", code: "E_SESSION" });
    expect(other.rt.engine).toBe(at);
  });
});

describe("snapshot and event stream", () => {
  it("coalesces snapshots until frameAck but sends every event in order", async () => {
    const { host, rt } = await loadedRuntime();
    host.out = [];
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "rod.move", rod: "transient", direction: "out" } });
    await send(rt, { kind: "time", rate: 10, paused: false });
    for (let i = 0; i < 4; i++) {
      host.advance(100);
      await send(rt, { kind: "command", clientSeq: 10 + i, clientId: "op", cmd: { type: "fault.reactivity", deltaRho: 0 } });
    }
    host.advance(100);
    // the load snapshot was never acknowledged, so nothing more was sent
    expect(host.of("snapshot")).toHaveLength(0);
    const events = host.of("events").flatMap((m) => m.events);
    expect(events.filter((ev) => ev.type === "command").map((ev) => ev.seq)).toEqual([1, 2, 3, 4, 5]);
    expect(host.of("ack").map((a) => a.clientSeq)).toEqual([1, 10, 11, 12, 13]);
    await send(rt, { kind: "frameAck" });
    expect(host.of("snapshot")).toHaveLength(1);
    expect(host.last("snapshot")!.snapshot.t).toBeCloseTo(rt.engine!.t, 12);
  });

  it("sends at most snapshotHz snapshots per wall second when the main thread keeps up", async () => {
    const { host, rt } = await loadedRuntime({ snapshotHz: 20 });
    await send(rt, { kind: "frameAck" });
    host.out = [];
    await send(rt, { kind: "time", rate: 1, paused: false });
    for (let i = 0; i < 100; i++) {
      host.advance(10);
      if (host.out.at(-1)?.kind === "snapshot") await send(rt, { kind: "frameAck" });
    }
    const n = host.of("snapshot").length;
    expect(n).toBeGreaterThanOrEqual(15);
    expect(n).toBeLessThanOrEqual(21);
  });

  it("sends the shape first, then only when a rod or the fuel temperature changed enough", async () => {
    const { host, rt } = await loadedRuntime();
    const withShape = () => host.of("snapshot").filter((s) => s.shape !== undefined).length;
    expect(host.last("snapshot")!.shape).toBeInstanceOf(Float32Array);
    expect(host.last("snapshot")!.shape!.length).toBe(rt.engine!.shape().length);
    for (let i = 0; i < 3; i++) {
      await send(rt, { kind: "frameAck" });
      await send(rt, { kind: "step", n: 1 });
    }
    expect(withShape()).toBe(1);
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "rod.move", rod: "regulating", direction: "out" } });
    await send(rt, { kind: "frameAck" });
    await send(rt, { kind: "step", n: 20 }); // 20 steps x 10 ms at the rod's speed moves it well past 0.001
    expect(withShape()).toBe(2);
  });
});

describe("halt and solver faults", () => {
  it("a solver error pauses the clock, rejects commands, and a rewind recovers", async () => {
    const { host, rt } = await loadedRuntime({ checkpointEveryS: 0.1 });
    await send(rt, { kind: "step", n: 30 });
    const orig = Engine.prototype.step;
    let calls = 0;
    vi.spyOn(Engine.prototype, "step").mockImplementation(function (this: Engine) {
      if (++calls === 5) throw new Error("synthetic solver failure");
      orig.call(this);
    });
    await send(rt, { kind: "time", paused: false });
    host.advance(200);
    expect(host.last("fault")!.message).toContain("synthetic solver failure");
    expect(host.last("clock")).toMatchObject({ paused: true, limited: "solver" });
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "scram" } });
    expect(host.last("ack")).toMatchObject({ reason: "REJ_FAULTED" });
    await send(rt, { kind: "time", paused: false });
    expect(host.last("error")).toMatchObject({ code: "E_FAULTED" });
    vi.restoreAllMocks();
    await send(rt, { kind: "rewind", step: 30 });
    await send(rt, { kind: "time", paused: false });
    host.advance(100);
    expect(rt.engine!.stepIndex).toBeGreaterThan(30);
    expect(host.last("clock")!.limited).toBeNull();
  });

  it("an engine halt pauses the clock with the halt reason", async () => {
    const { host, rt } = await loadedRuntime();
    const orig = Engine.prototype.step;
    vi.spyOn(Engine.prototype, "step").mockImplementation(function (this: Engine) {
      orig.call(this);
      if (this.stepIndex === 12) this.halted = "R_TABLE_REJECT_test";
    });
    await send(rt, { kind: "time", paused: false });
    host.advance(500);
    expect(rt.engine!.stepIndex).toBe(12);
    expect(host.last("clock")).toMatchObject({ paused: true, limited: "halted", reason: "R_TABLE_REJECT_test" });
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "scram" } });
    expect(host.last("ack")).toMatchObject({ reason: "REJ_HALTED" });
  });
});

describe("instrument extremes between snapshots (M5 amendment 1)", () => {
  it("a pulse peak between snapshots arrives in `extremes`, at the value a step-by-step run sees", async () => {
    const L = await loadSyntheticCore();
    const init = { rods: nearCriticalRods(L, -0.0005), mode: "pulse" };
    const { host, rt } = await loadedRuntime({}, { init, seed: 5 });
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "rod.fire", rod: "transient" } });
    // step 60 steps (0.6 s, through the pulse) while the main thread never acknowledges a frame
    await send(rt, { kind: "frameAck" });
    host.out = [];
    for (let i = 0; i < 60; i++) await send(rt, { kind: "step", n: 1 });
    await send(rt, { kind: "frameAck" }); // now the held-back snapshot goes out, with everything since
    const snaps = host.of("snapshot");
    const maxSeen = Math.max(...snaps.map((m) => m.extremes?.["log"]?.max ?? -Infinity));

    // the same run step by step, reading every step's indicated value
    const e = new Engine(L, init, 5);
    e.submit({ type: "rod.fire", rod: "transient" }, "op");
    let maxEvery = -Infinity;
    let tAt = 0;
    for (let i = 0; i < 60; i++) {
      e.step();
      const v = e.indicated["log"];
      if (v !== null && v !== undefined && v > maxEvery) {
        maxEvery = v;
        tAt = e.t;
      }
    }
    expect(maxSeen).toBe(maxEvery);
    const x = snaps.find((m) => m.extremes?.["log"]?.max === maxEvery)!.extremes!["log"]!;
    expect(x.tMax).toBeCloseTo(tAt, 12);
    // and the plain snapshot values alone miss it (that is why extremes exist)
    const plainMax = Math.max(...snaps.map((m) => m.snapshot.indicated["log"] ?? -Infinity));
    expect(plainMax).toBeLessThan(maxEvery);
  });

  it("a rewind drops extremes from the discarded timeline", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "fault.reactivity", deltaRho: 0.004 } });
    await send(rt, { kind: "step", n: 50 }); // snapshot held back: extremes pile up
    await send(rt, { kind: "rewind", step: 0 });
    await send(rt, { kind: "frameAck" });
    const last = host.last("snapshot")!;
    expect(last.snapshot.t).toBe(0);
    expect(last.extremes).toEqual({});
  });
});
