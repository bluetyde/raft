import { describe, expect, it } from "vitest";
import { OPERATOR_FORBIDDEN, type ToWorker } from "./protocol";
import { MAIN_PORT, Runtime } from "./runtime";
import { FakeHost, readFolder, send, syntheticCoreDir } from "./test-helpers";

const INIT = { rods: { regulating: 0.6584003609387292, safety: 1.0, transient: 0.0 } };

/** A shared-worker runtime with two windows: "A" (full, it loads the core) and "B" (operator). */
async function twoWindows() {
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
  await to("A", { kind: "load", protocol: 1, source: { kind: "files", files: readFolder(syntheticCoreDir) }, init: INIT });
  await to("B", { kind: "attach", role: "operator" });
  return { host, rt, to };
}

describe("two windows on one runtime (D2a)", () => {
  it("a window attaches and gets the loaded session and the current state at once", async () => {
    const { host } = await twoWindows();
    const attached = host.seenBy("B", "attached");
    expect(attached).toHaveLength(1);
    expect(attached[0]).toMatchObject({ role: "operator", loaded: { libraryId: "synthetic-core", outerDt: 0.01 } });
    // B was not attached during the load, but it has a snapshot, a clock, the history and the timeline now
    for (const kind of ["snapshot", "clock", "history", "timeline"] as const) expect(host.seenBy("B", kind).length).toBeGreaterThan(0);
    // the attach reply went only to B
    expect(host.seenBy("A", "attached").map((m) => m.role)).toEqual(["full"]);
  });

  it("a window that has not attached can only attach", async () => {
    const host = new FakeHost();
    const rt = new Runtime(host);
    rt.disconnect(MAIN_PORT);
    rt.connect("C");
    rt.receive({ kind: "time", paused: false }, "C");
    await rt.idle();
    expect(host.seenBy("C", "error")[0]).toMatchObject({ request: "time", code: "E_NOT_ATTACHED" });
    rt.receive({ kind: "attach", role: "boss" as never }, "C");
    await rt.idle();
    expect(host.seenBy("C", "error")[1]).toMatchObject({ request: "attach", code: "E_BAD_ARGUMENT" });
  });

  it("replies go to the window that asked, so the same clientSeq in two windows does not mix", async () => {
    const { host, to } = await twoWindows();
    await to("A", { kind: "command", clientSeq: 1, clientId: "instructor", cmd: { type: "rod.move", rod: "transient", direction: "out" } });
    await to("B", { kind: "command", clientSeq: 1, clientId: "operator", cmd: { type: "rod.move", rod: "nope", direction: "out" } });
    await to("A", { kind: "step", n: 1 });
    const ackA = host.seenBy("A", "ack");
    const ackB = host.seenBy("B", "ack");
    expect(ackA).toHaveLength(1);
    expect(ackB).toHaveLength(1);
    expect(ackA[0]).toMatchObject({ clientSeq: 1, status: "accepted" });
    expect(ackB[0]).toMatchObject({ clientSeq: 1, status: "rejected", reason: "REJ_UNKNOWN_ROD" });
    expect(host.seenBy("A", "queued")).toHaveLength(1);
    // events and the timeline go to both windows
    expect(host.seenBy("B", "events").flatMap((m) => m.events).filter((e) => e.type === "command")).toHaveLength(2);
  });

  it("each window has its own frame pacing: a window that does not ack does not hold up the other", async () => {
    const { host, to } = await twoWindows();
    const before = host.seenBy("B", "snapshot").length;
    for (let i = 0; i < 3; i++) {
      await to("A", { kind: "step", n: 5 });
      await to("A", { kind: "frameAck" });
    }
    expect(host.seenBy("A", "snapshot").at(-1)!.snapshot.t).toBeCloseTo(0.15, 9);
    // B acked nothing, so it got no new snapshot after its first
    expect(host.seenBy("B", "snapshot")).toHaveLength(before);
    await to("B", { kind: "frameAck" });
    const last = host.seenBy("B", "snapshot").at(-1)!;
    expect(last.snapshot.t).toBeCloseTo(0.15, 9);
    // and its extremes cover every step it missed, not only the last one
    const lows = host.seenBy("A", "snapshot").slice(-3).map((m) => m.extremes!["linear"]!.min);
    expect(last.extremes!["linear"]!.min).toBe(Math.min(...lows));
  });

  it("amendment 3: an operator window cannot send time, rewind or fault commands", async () => {
    const { host, rt, to } = await twoWindows();
    const forbidden: ToWorker[] = [
      { kind: "time", paused: false },
      { kind: "step", n: 1 },
      { kind: "rewind", step: 0 },
      { kind: "branch.switch", id: 1 },
      { kind: "annotate", text: "x" },
      { kind: "annotation.delete", id: 1 },
      { kind: "load", protocol: 1, source: { kind: "files", files: {} } },
      { kind: "session.import", file: {} as never },
      { kind: "scenario.end" },
      { kind: "script.load", script: null },
      { kind: "supervisor.goal", powerW: null },
    ];
    expect(forbidden.map((m) => m.kind).sort()).toEqual([...OPERATOR_FORBIDDEN].sort());
    for (const m of forbidden) await to("B", m);
    const errors = host.seenBy("B", "error");
    expect(errors.map((e) => [e.request, e.code])).toEqual(forbidden.map((m) => [m.kind, "E_ROLE"]));
    expect(host.seenBy("A", "error")).toHaveLength(0);
    expect(rt.engine!.stepIndex).toBe(0);

    await to("B", { kind: "command", clientSeq: 7, clientId: "operator", cmd: { type: "fault.instrument", instrument: "log", kind: "stuck" } });
    await to("B", { kind: "command", clientSeq: 8, clientId: "operator", cmd: { type: "fault.reactivity", deltaRho: 1e-4 } });
    expect(host.seenBy("B", "ack").map((a) => [a.clientSeq, a.reason])).toEqual([
      [7, "REJ_ROLE"],
      [8, "REJ_ROLE"],
    ]);
    // the operator's own controls still work, and it may read the session
    await to("B", { kind: "command", clientSeq: 9, clientId: "operator", cmd: { type: "scram" } });
    await to("B", { kind: "session.export" });
    expect(host.seenBy("B", "session")).toHaveLength(1);
    await to("A", { kind: "step", n: 1 });
    expect(host.seenBy("B", "ack").at(-1)).toMatchObject({ clientSeq: 9, status: "accepted" });
    expect(rt.engine!.commandLog.map((c: any) => c.cmd.type)).toEqual(["scram"]);
    // the same fault from the instructor's window is accepted
    await to("A", { kind: "command", clientSeq: 2, clientId: "instructor", cmd: { type: "fault.instrument", instrument: "log", kind: "stuck" } });
    await to("A", { kind: "step", n: 1 });
    expect(host.seenBy("A", "ack").at(-1)).toMatchObject({ clientSeq: 2, status: "accepted" });
  });

  it("an instructor window may send everything", async () => {
    const { host, to } = await twoWindows();
    await to("B", { kind: "attach", role: "instructor" });
    await to("B", { kind: "step", n: 3 });
    await to("B", { kind: "annotate", text: "ok" });
    expect(host.seenBy("B", "error")).toHaveLength(0);
  });

  it("a detached window gets nothing more, and its pending acks are dropped", async () => {
    const { host, rt, to } = await twoWindows();
    await to("B", { kind: "command", clientSeq: 1, clientId: "operator", cmd: { type: "scram" } });
    await to("B", { kind: "detach" });
    const n = host.sent.length;
    await to("A", { kind: "step", n: 2 });
    await to("B", { kind: "frameAck" });
    expect(host.sent.slice(n).filter((x) => x.to === "B")).toHaveLength(0);
    expect(rt.windows().map((w) => w.id)).toEqual(["A"]);
    // the scram still applies: the session does not depend on the window that sent it
    expect(rt.engine!.snapshot().tripped).toBe(true);
  });

  it("a dedicated worker keeps its one window, role full, with no attach needed", async () => {
    const host = new FakeHost();
    const rt = new Runtime(host);
    await send(rt, { kind: "load", protocol: 1, source: { kind: "files", files: readFolder(syntheticCoreDir) } });
    await send(rt, { kind: "time", rate: 10 });
    expect(host.of("error")).toHaveLength(0);
    expect(rt.windows()).toEqual([{ id: MAIN_PORT, role: "full" }]);
  });
});
