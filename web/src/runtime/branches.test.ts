import { describe, expect, it } from "vitest";
import { Engine } from "../sim/engine";
import { comparable, loadSyntheticCore } from "../sim/testing";
import { buildBranch, marksBefore } from "./branches";
import { CheckpointStore } from "./history";
import type { SessionFile } from "./protocol";
import { MAX_BRANCHES } from "./protocol";
import type { Runtime } from "./runtime";
import { traceCsv, traceHeader, traceRow } from "./trace";
import { loadedRuntime, send, type FakeHost } from "./test-helpers";

const INIT = { rods: { regulating: 0.6584003609387292, safety: 1.0, transient: 0.0 } };

let seq = 1;
async function cmd(rt: Runtime, c: Record<string, unknown>, clientId = "test") {
  await send(rt, { kind: "command", clientSeq: seq++, clientId, cmd: c });
}
const state = (rt: Runtime) => comparable(rt.engine!.checkpoint());
const timeline = (host: FakeHost) => host.last("timeline")!;

/** Branch A: rod out at step 0, a stuck log channel at step 600, run to step 1500 (checkpoints at 0 and 1000). */
async function branchA() {
  const { host, rt } = await loadedRuntime({}, { init: INIT, seed: 3 });
  await cmd(rt, { type: "rod.move", rod: "transient", direction: "out" });
  await send(rt, { kind: "step", n: 600 });
  await cmd(rt, { type: "fault.instrument", instrument: "log", kind: "stuck" }, "instructor");
  await send(rt, { kind: "step", n: 900 });
  return { host, rt, endA: state(rt) };
}

describe("branches (D1a)", () => {
  it("a rewind keeps the old timeline as a branch, and a switch back gives its end state again", async () => {
    const { host, rt, endA } = await branchA();
    await send(rt, { kind: "rewind", step: 1200 });
    let tl = timeline(host);
    expect(tl.current).toMatchObject({ id: 2, parent: 1, forkStep: 1200 });
    expect(tl.branches).toHaveLength(1);
    // amendment 4: fork step and command count next to the final values
    expect(tl.branches[0]).toMatchObject({ id: 1, parent: null, forkStep: 0, endStep: 1500, commandCount: 2 });
    expect(tl.branches[0]!.final.t).toBeCloseTo(15, 9);

    // a different action on the new branch
    await cmd(rt, { type: "scram" });
    await send(rt, { kind: "step", n: 100 });
    const endB = state(rt);
    expect(endB).not.toEqual(endA);

    // the clock message after a rewind names the new step (the rate and pause did not change)
    expect(host.last("clock")!.step).toBe(1300);
    await send(rt, { kind: "branch.switch", id: 1 });
    expect(host.last("rewound")!.step).toBe(1500);
    expect(host.last("clock")!.step).toBe(1500);
    expect(state(rt)).toEqual(endA);
    // the rewind stored a checkpoint at step 1200, before the scram, so both timelines share it and the replay starts there
    expect(rt.lastSwitchFrom).toBe(1200);
    tl = timeline(host);
    expect(tl.current).toMatchObject({ id: 1, parent: null, forkStep: 0 });
    expect(tl.branches.map((b) => [b.id, b.parent, b.forkStep, b.commandCount])).toEqual([[2, 1, 1200, 3]]);

    await send(rt, { kind: "branch.switch", id: 2 });
    expect(state(rt)).toEqual(endB);
  });

  it("the shared-checkpoint path gives the same state as a replay from step 0", async () => {
    const { host, rt, endA } = await branchA();
    await send(rt, { kind: "session.export" });
    const fileA = host.last("session")!.file;
    await send(rt, { kind: "rewind", step: 1200 });
    await cmd(rt, { type: "scram" });
    await send(rt, { kind: "step", n: 50 });
    await send(rt, { kind: "branch.switch", id: 1 });
    expect(rt.lastSwitchFrom).toBeGreaterThan(0);
    const lib = await loadSyntheticCore();
    const fromZero = Engine.replay(lib, fileA.session, fileA.endStep);
    expect(state(rt)).toEqual(comparable(fromZero.checkpoint()));
    expect(state(rt)).toEqual(endA);
  });

  it("a switch starts from the latest shared checkpoint, not from a later one of the other branch", async () => {
    const { rt, endA } = await branchA();
    await send(rt, { kind: "rewind", step: 300 }); // stores a checkpoint at 300, shared with A
    await cmd(rt, { type: "rod.move", rod: "transient", direction: "stop" });
    await send(rt, { kind: "step", n: 800 }); // makes a checkpoint at 1000 on this branch, not shared
    await send(rt, { kind: "branch.switch", id: 1 });
    expect(rt.lastSwitchFrom).toBe(300);
    expect(state(rt)).toEqual(endA);
  });

  it("with no shared checkpoint at all, buildBranch replays from step 0 and gives the same state", async () => {
    const { host, rt, endA } = await branchA();
    await send(rt, { kind: "session.export" });
    const file = host.last("session")!.file;
    const lib = await loadSyntheticCore();
    const built = buildBranch(lib, rt.engine!, new CheckpointStore(8), file, (st, x) => {
      if (x.stepIndex % 1000 === 0) st.add(x.checkpoint());
    });
    expect(built.fromStep).toBe(0);
    expect(comparable(built.engine.checkpoint())).toEqual(endA);
    expect(built.store.steps()).toEqual([0, 1000]);
  });

  it("a switch to an unknown branch is an error, and a rewind to the current step makes no branch", async () => {
    const { host, rt } = await branchA();
    await send(rt, { kind: "branch.switch", id: 99 });
    expect(host.last("error")).toMatchObject({ request: "branch.switch", code: "E_NO_BRANCH" });
    await send(rt, { kind: "rewind", step: 1500 });
    expect(timeline(host).branches).toHaveLength(0);
  });

  it(`keeps at most ${MAX_BRANCHES} branches, and the oldest goes first`, async () => {
    const { host, rt } = await loadedRuntime();
    for (let i = 0; i < MAX_BRANCHES + 3; i++) {
      await send(rt, { kind: "step", n: 2 });
      await send(rt, { kind: "rewind", step: 1 });
    }
    const ids = timeline(host).branches.map((b) => b.id);
    expect(ids).toHaveLength(MAX_BRANCHES);
    expect(ids[0]).toBe(4);
    expect(timeline(host).current.id).toBe(MAX_BRANCHES + 4);
  });
});

describe("marks", () => {
  it("come from trips, rejected commands and accepted faults; a rewind drops later ones; a switch restores them", async () => {
    const { host, rt } = await loadedRuntime({}, { init: INIT, seed: 1 });
    await cmd(rt, { type: "fault.instrument", instrument: "log", kind: "dead" }, "instructor");
    await cmd(rt, { type: "rod.move", rod: "nope", direction: "out" });
    await send(rt, { kind: "step", n: 1 });
    await cmd(rt, { type: "rod.move", rod: "transient", direction: "out" });
    await send(rt, { kind: "step", n: 2000 }); // the period trip comes at about 17 s
    const before = timeline(host).marks;
    expect(before.map((m) => m.kind)).toEqual(["fault", "rejected", "trip"]);
    expect(before[0]!.label).toBe("log: dead");
    expect(before[1]!.label).toBe("test: REJ_UNKNOWN_ROD");
    await send(rt, { kind: "rewind", step: 1000 });
    expect(timeline(host).marks.map((m) => m.kind)).toEqual(["fault", "rejected"]);
    await send(rt, { kind: "branch.switch", id: 1 });
    expect(timeline(host).marks).toEqual(before);
    // an import of the same session finds the same marks in its replay
    await send(rt, { kind: "session.export" });
    await send(rt, { kind: "session.import", file: host.last("session")!.file });
    expect(timeline(host).marks).toEqual(before);
  });

  it("after a rewind to t, command marks at t go (the commands are still queued) and trips at t stay", () => {
    const marks = [
      { kind: "fault" as const, t: 1, label: "a" },
      { kind: "rejected" as const, t: 2, label: "b" },
      { kind: "trip" as const, t: 2, label: "c" },
      { kind: "trip" as const, t: 2.5, label: "d" },
    ];
    expect(marksBefore(marks, 2, 0.01).map((m) => m.label)).toEqual(["a", "c"]);
  });
});

describe("annotations and session files version 2 (D6)", () => {
  it("are added and deleted, move to the old branch on a rewind, and travel in the session file", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "step", n: 100 });
    await send(rt, { kind: "annotate", text: "  rod starts out  " });
    await send(rt, { kind: "annotate", text: "early note", step: 10 });
    await send(rt, { kind: "annotate", text: "to delete" });
    let notes = timeline(host).annotations;
    expect(notes.map((a) => [a.step, a.text])).toEqual([
      [10, "early note"],
      [100, "rod starts out"],
      [100, "to delete"],
    ]);
    expect(notes[0]!.t).toBeCloseTo(0.1, 12);
    await send(rt, { kind: "annotation.delete", id: notes[2]!.id });
    expect(timeline(host).annotations).toHaveLength(2);

    await send(rt, { kind: "annotate", text: "" });
    expect(host.last("error")).toMatchObject({ request: "annotate", code: "E_BAD_ARGUMENT" });
    await send(rt, { kind: "annotate", text: "future", step: 101 });
    expect(host.last("error")!.message).toContain("[0, 100]");

    await send(rt, { kind: "session.export" });
    const file = host.last("session")!.file;
    expect(file.version).toBe(3); // version 3 since M5 scenarios; without a scenario it has no scenario field
    expect(file.scenario).toBeUndefined();
    expect(file.annotations!.map((a) => a.text)).toEqual(["early note", "rod starts out"]);
    expect(file.branch).toEqual({ id: 1, parent: null, forkStep: 0 });

    await send(rt, { kind: "rewind", step: 50 });
    notes = timeline(host).annotations;
    expect(notes.map((a) => a.text)).toEqual(["early note"]);
    expect(timeline(host).branches[0]!.annotationCount).toBe(2);

    await send(rt, { kind: "session.import", file });
    expect(timeline(host).annotations.map((a) => a.text)).toEqual(["early note", "rod starts out"]);
    expect(timeline(host).current.parent).toBeNull();
    // the replaced timeline is kept as a branch too
    expect(timeline(host).branches.map((b) => b.id)).toEqual([1, 2]);
  });

  it("a version 1 file still imports", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "step", n: 20 });
    await send(rt, { kind: "session.export" });
    const { annotations: _a, branch: _b, ...rest } = host.last("session")!.file;
    const v1 = { ...rest, version: 1 } as SessionFile;
    await send(rt, { kind: "session.import", file: v1 });
    expect(host.last("error")).toBeUndefined();
    expect(rt.engine!.stepIndex).toBe(20);
    expect(timeline(host).annotations).toEqual([]);
  });

  it("a version 2 file (notes and branch, no scenario) still imports", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "step", n: 20 });
    await send(rt, { kind: "annotate", text: "v2 note" });
    await send(rt, { kind: "session.export" });
    const v2 = { ...host.last("session")!.file, version: 2 } as SessionFile;
    await send(rt, { kind: "session.import", file: v2 });
    expect(host.last("error")).toBeUndefined();
    expect(timeline(host).annotations.map((a) => a.text)).toEqual(["v2 note"]);
  });

  it("a file with malformed annotations does not import", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "session.export" });
    const file = { ...host.last("session")!.file, annotations: [{ step: "x" }] } as unknown as SessionFile;
    await send(rt, { kind: "session.import", file });
    expect(host.last("error")).toMatchObject({ request: "session.import", code: "E_SESSION" });
  });
});

describe("review fixes (M6 Codex review, 2026-10-07)", () => {
  it("a rewind to the step of a SCRAM drops the manual trip mark, which the queued command makes again", async () => {
    const { host, rt } = await loadedRuntime({}, { init: INIT, seed: 3 });
    await send(rt, { kind: "step", n: 10 });
    await cmd(rt, { type: "scram" });
    await send(rt, { kind: "step", n: 20 });
    expect(timeline(host).marks.filter((m) => m.label === "trip manual")).toHaveLength(1);
    await send(rt, { kind: "rewind", step: 10 });
    expect(timeline(host).marks.filter((m) => m.label === "trip manual")).toHaveLength(0);
    await send(rt, { kind: "step", n: 1 });
    expect(timeline(host).marks.filter((m) => m.label === "trip manual")).toHaveLength(1); // once, not twice
    // trips that are not from a command stay at the boundary
    const marks = [{ kind: "trip" as const, t: 1, label: "trip highPower" }];
    expect(marksBefore(marks, 1, 0.01)).toHaveLength(1);
  });

  it("an import keeps the replaced timeline when it holds only a note", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "session.export" });
    const file = host.last("session")!.file;
    await send(rt, { kind: "annotate", text: "briefing" }); // step 0, no steps, no commands
    await send(rt, { kind: "session.import", file });
    expect(timeline(host).branches).toHaveLength(1);
    expect(timeline(host).branches[0]!.annotationCount).toBe(1);
  });

  it("an import refuses a note after the end or with a time that is not its step's", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "step", n: 20 });
    await send(rt, { kind: "session.export" });
    const file = host.last("session")!.file;
    const late = { ...file, annotations: [{ id: 1, step: 1000, t: 10, text: "future" }] } as SessionFile;
    await send(rt, { kind: "session.import", file: late });
    expect(host.last("error")).toMatchObject({ request: "session.import", code: "E_SESSION" });
    const off = { ...file, annotations: [{ id: 1, step: 5, t: 500, text: "wrong time" }] } as SessionFile;
    await send(rt, { kind: "session.import", file: off });
    expect(host.last("error")!.message).toContain("not step 5");
    const ok = { ...file, annotations: [{ id: 1, step: 5, t: 5 * file.session.pins.config.outerDt, text: "fine" }] } as SessionFile;
    await send(rt, { kind: "session.import", file: ok });
    expect(timeline(host).annotations.map((a) => a.text)).toEqual(["fine"]);
  });

  it("the rewound message carries the outer step and says whether the timeline was replaced", async () => {
    const { host, rt } = await loadedRuntime();
    await send(rt, { kind: "step", n: 20 });
    await send(rt, { kind: "rewind", step: 10 });
    expect(host.last("rewound")).toMatchObject({ outerDt: 0.01, replaced: false });
    await send(rt, { kind: "session.export" });
    await send(rt, { kind: "session.import", file: host.last("session")!.file });
    expect(host.last("rewound")).toMatchObject({ outerDt: 0.01, replaced: true });
    await send(rt, { kind: "branch.switch", id: 1 });
    expect(host.last("rewound")).toMatchObject({ replaced: true });
  });
});

describe("CSV traces (D6a)", () => {
  it("equal a step-by-step run's snapshots at the sampled steps", async () => {
    const { host, rt } = await branchA();
    await send(rt, { kind: "session.export" });
    const file = host.last("session")!.file;
    const lib = await loadSyntheticCore();
    const lines = traceCsv(lib, file, 0.1).trimEnd().split("\n");
    expect(lines[0]).toBe(traceHeader(lib).join(","));
    expect(lines).toHaveLength(1 + 1 + 1500 / 10); // header, step 0, then every 10 steps

    // a separate run, step by step, with a snapshot at each sampled step
    const s = file.session;
    const e = new Engine(lib, s.init, s.seed, s.pins.config);
    const expected = [traceRow(lib, e.snapshot(false)).join(",")];
    const byStep = new Map<number, any[]>();
    for (const c of s.commands) byStep.set(c.step, [...(byStep.get(c.step) ?? []), c]);
    while (e.stepIndex < file.endStep) {
      for (const c of byStep.get(e.stepIndex) ?? []) e.submit(c.cmd, c.clientId);
      e.step();
      if (e.stepIndex % 10 === 0) expected.push(traceRow(lib, e.snapshot(false)).join(","));
    }
    expect(lines.slice(1)).toEqual(expected);
    // the stuck log channel shows: its column stops changing after step 600
    const col = traceHeader(lib).indexOf("indicated.log");
    const logAt = (row: number) => lines[row]!.split(",")[col];
    expect(logAt(1 + 70)).toBe(logAt(1 + 150));
  });

  it("samples every step when the interval is shorter than the step, and writes inf for an infinite period", async () => {
    const { host, rt } = await loadedRuntime({}, { config: { outerDt: 1 } });
    await send(rt, { kind: "step", n: 5 });
    await send(rt, { kind: "session.export" });
    const lib = await loadSyntheticCore();
    const lines = traceCsv(lib, host.last("session")!.file, 0.1).trimEnd().split("\n");
    expect(lines).toHaveLength(1 + 6);
    expect(lines[6]!.split(",")[0]).toBe("5");
  });
});
