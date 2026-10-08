import { describe, expect, it } from "vitest";
import { OPERATOR_FORBIDDEN } from "./protocol";
import { Runtime } from "./runtime";
import { FakeHost, readFolder, send } from "./test-helpers";
import { fixturesDir } from "../sim/testing";
import { validateCommand } from "../contracts/validate";
import { join } from "node:path";

async function boronRuntime() {
  const host = new FakeHost();
  const rt = new Runtime(host);
  rt.receive({ kind: "load", protocol: 1, source: { kind: "files", files: readFolder(join(fixturesDir, "synthetic-core-boron")) } });
  await rt.idle();
  if (!rt.engine) throw new Error(`load failed: ${JSON.stringify(host.last("loadFailed"))}`);
  return { host, rt };
}

describe("soluble boron in the runtime", () => {
  it("a boron.set from the operator is accepted, the concentration moves, and it replays from the session", async () => {
    const { host, rt } = await boronRuntime();
    expect(OPERATOR_FORBIDDEN).not.toContain("boron.set");                 // boron is the operator's lever, unlike the fault commands
    expect(validateCommand({ type: "boron.set", ppm: 900 })).toEqual([]);
    expect(validateCommand({ type: "boron.set", ppm: "lots" }).length).toBeGreaterThan(0);
    await send(rt, { kind: "command", clientSeq: 1, clientId: "operator", cmd: { type: "boron.set", ppm: 990 } });
    await send(rt, { kind: "step", n: 2000 });                             // 20 s at 0.5 ppm/s: 10 ppm, the target
    expect(host.last("ack")).toMatchObject({ clientSeq: 1, status: "accepted" });
    const truth = rt.engine!.snapshot().truth;
    expect(truth.boron).toBeCloseTo(990, 9);
    expect(truth.boronTarget).toBeNull();
    await send(rt, { kind: "session.export" });
    const file = host.last("session")!.file;
    await send(rt, { kind: "session.import", file });
    expect(host.last("error")).toBeUndefined();
    expect(rt.engine!.snapshot().truth.boron).toBeCloseTo(990, 9);          // the command is in the log and replays on its own
  });

  it("a rewind restores the concentration of that step", async () => {
    const { rt } = await boronRuntime();
    await send(rt, { kind: "command", clientSeq: 1, clientId: "operator", cmd: { type: "boron.set", ppm: 900 } });
    await send(rt, { kind: "step", n: 1000 });                             // 10 s: 995 ppm
    await send(rt, { kind: "step", n: 1000 });                             // 20 s: 990 ppm
    await send(rt, { kind: "rewind", step: 1000 });
    expect(rt.engine!.snapshot().truth.boron).toBeCloseTo(995, 9);
  });
});
