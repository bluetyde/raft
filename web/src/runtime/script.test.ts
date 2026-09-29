import { describe, expect, it } from "vitest";
import { agentRig } from "./agent-harness";
import { SCRIPT_FORMAT, UNSUPPORTED_ACTIONS, validateScript } from "./script";
import { loadedRuntime, send } from "./test-helpers";

const file = (events: unknown[], name = "drill") => ({ format: SCRIPT_FORMAT, version: 1, name, events });

async function rtWithIds() {
  const { host, rt } = await loadedRuntime();
  const lib = rt.engine!.lib;
  return { host, rt, lib, instrument: lib.instruments[0].id as string, pump: lib.pumps[0] as string };
}

describe("instructor script: validation", () => {
  it("accepts supported actions with minutes or seconds", async () => {
    const { lib, instrument, pump } = await rtWithIds();
    const s = file([
      { atMinutes: 5, action: "instrument.stuck", instrument },
      { atSeconds: 90, action: "reactivity.step", deltaRho: 0.0005 },
      { atMinutes: 12, action: "pump.trip", pump },
      { atMinutes: 20, action: "scram" },
    ]);
    expect(validateScript(s, lib)).toEqual([]);
  });

  it("refuses accidents the engine cannot model, by name", async () => {
    const { lib } = await rtWithIds();
    for (const a of ["loca", "pipe.burst", "steamline.break"]) {
      const issues = validateScript(file([{ atMinutes: 3, action: a }]), lib);
      expect(issues.map((i) => i.code)).toEqual(["E_SCRIPT_UNSUPPORTED"]);
      expect(issues[0]!.message).toBe(UNSUPPORTED_ACTIONS[a]);
    }
  });

  it("refuses faults the command contract does not list, and bad times, ids and params", async () => {
    const { lib } = await rtWithIds();
    const codes = (events: unknown[]) => validateScript(file(events), lib).map((i) => i.code);
    expect(codes([{ atMinutes: 1, action: "instrument.drift", instrument: "x", rate: 1 }])).toEqual(["E_SCRIPT_UNSUPPORTED"]);
    expect(codes([{ atMinutes: -1, action: "scram" }])).toEqual(["E_SCRIPT_TIME"]);
    expect(codes([{ action: "scram" }])).toEqual(["E_SCRIPT_TIME"]);
    expect(codes([{ atMinutes: 1, atSeconds: 60, action: "scram" }])).toEqual(["E_SCRIPT_TIME"]);
    expect(codes([{ atMinutes: 1, action: "instrument.stuck", instrument: "nope" }])).toEqual(["E_SCRIPT_PARAM"]);
    expect(codes([{ atMinutes: 1, action: "pump.trip", pump: "nope" }])).toEqual(["E_SCRIPT_PARAM"]);
    expect(codes([{ atMinutes: 1, action: "reactivity.step" }])).toEqual(["E_SCRIPT_PARAM"]);
    expect(codes([{ atMinutes: 1, action: "explode" }])).toEqual(["E_SCRIPT_ACTION"]);
    expect(codes([])).toEqual(["E_SCRIPT_EVENTS"]);
    expect(validateScript({ format: "other" }, lib)[0]!.code).toBe("E_SCRIPT_FIELD");
  });
});

describe("instructor script: runtime", () => {
  it("submits each event at its time as a command from 'script', in time order", async () => {
    const { rt, host, instrument, pump } = await rtWithIds();
    await send(rt, {
      kind: "script.load",
      script: file([
        { atSeconds: 0.05, action: "pump.trip", pump },
        { atSeconds: 0, action: "instrument.stuck", instrument, note: "stuck at once" },
      ]),
    });
    expect(host.last("script")!.script!.events.map((e) => [e.step, e.note])).toEqual([[0, "stuck at once"], [5, "pump.trip"]]);
    await send(rt, { kind: "step", n: 10 });
    const log = rt.engine!.commandLog.filter((c: any) => c.clientId === "script");
    expect(log.map((c: any) => [c.step, c.cmd.type])).toEqual([[0, "fault.instrument"], [5, "pump.set"]]);
    expect(host.last("timeline")!.marks.some((m) => m.label.startsWith("script:"))).toBe(true);
  });

  it("an invalid script is rejected as a whole and changes nothing", async () => {
    const { rt, host } = await rtWithIds();
    await send(rt, { kind: "script.load", script: file([{ atMinutes: 1, action: "loca" }]) });
    expect(host.last("error")!.code).toBe("E_SCRIPT_UNSUPPORTED");
    expect(host.last("script")!.script).toBeNull(); // nothing was loaded
    await send(rt, { kind: "step", n: 5 });
    expect(rt.engine!.commandLog.some((c: any) => c.clientId === "script")).toBe(false);
  });

  it("replays after a rewind: events after the rewind step fire again", async () => {
    const { rt, instrument } = await rtWithIds();
    await send(rt, { kind: "script.load", script: file([{ atSeconds: 0.05, action: "instrument.stuck", instrument }]) });
    await send(rt, { kind: "step", n: 10 });
    await send(rt, { kind: "rewind", step: 2 });
    expect(rt.engine!.commandLog.some((c: any) => c.clientId === "script")).toBe(false);
    await send(rt, { kind: "step", n: 10 });
    expect(rt.engine!.commandLog.filter((c: any) => c.clientId === "script").map((c: any) => c.step)).toEqual([5]);
  });

  it("rejects an event already in the past, and a second script after one has run", async () => {
    const { rt, host, instrument } = await rtWithIds();
    await send(rt, { kind: "step", n: 20 });
    await send(rt, { kind: "script.load", script: file([{ atSeconds: 0, action: "instrument.stuck", instrument }]) });
    expect(host.last("error")!.code).toBe("E_SCRIPT_PAST");
    await send(rt, { kind: "script.load", script: file([{ atSeconds: 1, action: "instrument.stuck", instrument }]) });
    await send(rt, { kind: "step", n: 100 });
    await send(rt, { kind: "script.load", script: file([{ atSeconds: 5, action: "scram" }]) });
    expect(host.last("error")!.code).toBe("E_SCRIPT_ACTIVE");
  });

  it("an operator window may not load a script, and 'script' is not a client id", async () => {
    const { rt, host } = await rtWithIds();
    rt.connect("op");
    rt.receive({ kind: "attach", role: "operator" }, "op");
    await rt.idle();
    rt.receive({ kind: "script.load", script: null }, "op");
    await rt.idle();
    expect(host.last("error")!.code).toBe("E_ROLE");
    await send(rt, { kind: "command", clientSeq: 1, clientId: "script", cmd: { type: "scram" } });
    expect(host.last("ack")!.status).toBe("rejected");
  });

  it("a script works alongside supervision (the rig from the supervisor tests)", async () => {
    const rig = await agentRig(() => null);
    const lib = rig.rt.engine!.lib;
    await send(rig.rt, { kind: "script.load", script: file([{ atSeconds: 0, action: "instrument.stuck", instrument: lib.instruments[0].id }]) });
    expect(rig.cmds("script").length).toBe(1);
  });
});

describe("shipped example script", () => {
  it("is valid for the TRIGA library", async () => {
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const { repoRoot } = await import("../sim/testing");
    const { host, rt } = await loadedRuntime({}, { source: { kind: "files", files: (await import("./test-helpers")).readFolder(join(repoRoot, "libraries", "triga-jsi-242")) } });
    void host;
    for (const name of ["loss-of-flow-drill", "raise-then-lower"]) {
      const s = JSON.parse(readFileSync(join(repoRoot, "web", "src", "app", "scripts", `${name}.json`), "utf8"));
      expect(validateScript(s, rt.engine!.lib), name).toEqual([]);
    }
  });
});

describe("instructor script: AI operator goal", () => {
  it("goal events steer the premise at their time, without any engine command", async () => {
    const rig = await agentRig(() => "hold");
    await send(rig.rt, {
      kind: "script.load",
      script: file([
        { atSeconds: 0.5, action: "goal.set", powerW: 5 },
        { atSeconds: 1.5, action: "goal.clear" },
      ]),
    });
    await send(rig.rt, { kind: "supervisor.enable" });
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(3000);
    const has = (fn: (p: string) => boolean) => rig.requests.some((r) => fn(r.premise));
    expect(rig.requests[0]!.premise).toContain("GOAL: hold the current power");
    expect(has((p) => p.includes("bring power to 5.00e+0 W"))).toBe(true);
    expect(rig.requests.at(-1)!.premise).toContain("GOAL: hold the current power");
    expect(rig.cmds("script")).toEqual([]);
  });

  it("rejects a goal without a positive power", async () => {
    const { lib } = await rtWithIds();
    expect(validateScript(file([{ atSeconds: 0, action: "goal.set" }]), lib).map((i) => i.code)).toEqual(["E_SCRIPT_PARAM"]);
    expect(validateScript(file([{ atSeconds: 0, action: "goal.set", powerW: -1 }]), lib).map((i) => i.code)).toEqual(["E_SCRIPT_PARAM"]);
  });
});
