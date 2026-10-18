import { describe, expect, it } from "vitest";
import { CheckpointError, Engine } from "../sim/engine";
import { loadSyntheticCore } from "../sim/testing";
import { checkSessionFile, MAX_SESSION_COMMANDS, MAX_SESSION_STEPS, replayCommands, sessionFile } from "./history";

/** The session import and replay guards found by the whole-repo review. */

const INIT = { rods: { safety: 0, regulating: 0, transient: 0 }, power: { mode: "given", value: 1.0 }, poisons: { mode: "zero" } };

async function setup() {
  const lib = await loadSyntheticCore();
  const e = new Engine(lib, { ...INIT }, 1);
  return { lib, e };
}

const cmd = (seq: number, step: number) => ({ seq, step, clientId: "t", cmd: { type: "fault.reactivity", deltaRho: 1e-6 } });

describe("replay", () => {
  it("applies every logged command, or says which it did not", async () => {
    const { e } = await setup();
    replayCommands(e, [cmd(1, 2), cmd(2, 5)], 10);
    expect(e.stepIndex).toBe(10);
    expect(e.nextSeq).toBe(3);
    const { e: e2 } = await setup();
    replayCommands(e2, [cmd(1, 2), cmd(2, 50)], 10);                         // dated after the end of the replay: not due yet, so it waits (a rewind relies on this)
    expect(e2.nextSeq).toBe(2);
    const { e: e3 } = await setup();
    e3.halted = null;
    const forged = [cmd(1, 2), { ...cmd(2, 3), step: 3 }];
    forged[1]!.step = 3;
    replayCommands(e3, forged, 10);
    expect(e3.nextSeq).toBe(3);
  });

  it("refuses a log whose later command is dated before an earlier one", async () => {
    const { e } = await setup();
    expect(() => replayCommands(e, [cmd(1, 5), cmd(2, 0)], 10)).toThrow(/seq 2 is at step 0, before seq 1 at step 5/);
  });
});

describe("a session file", () => {
  async function file() {
    const { lib, e } = await setup();
    e.submit({ type: "fault.reactivity", deltaRho: 1e-6 });
    e.advance(0.5);
    return { lib, f: JSON.parse(JSON.stringify(sessionFile(e))) };
  }

  it("is accepted as exported", async () => {
    const { lib, f } = await file();
    expect(checkSessionFile(f, lib)).toBeTruthy();
  });

  it("must not ask for an unbounded replay or carry more than the limit of commands", async () => {
    const { lib, f } = await file();
    f.endStep = MAX_SESSION_STEPS + 1;
    expect(() => checkSessionFile(f, lib)).toThrow(/beyond the 1000000 steps/);
    f.endStep = MAX_SESSION_STEPS;                                          // at the limit: not refused for its length
    expect(() => checkSessionFile(f, lib)).not.toThrow(/beyond/);
    const { f: g } = await file();
    g.session.commands = Array.from({ length: MAX_SESSION_COMMANDS + 1 }, (_, i) => cmd(i + 1, 0));
    expect(() => checkSessionFile(g, lib)).toThrow(/more than the 100000/);
  });

  it("must have well formed commands dated inside the run", async () => {
    const { lib, f } = await file();
    for (const bad of [{ ...cmd(1, f.endStep + 1) }, { ...cmd(1, -1) }, { ...cmd(1.5, 0) }, { seq: 1, step: 0, clientId: "t" }, { ...cmd(1, 0), step: "0" }]) {
      const g = JSON.parse(JSON.stringify(f));
      g.session.commands = [bad];
      expect(() => checkSessionFile(g, lib), JSON.stringify(bad)).toThrow(CheckpointError);
    }
  });
});
