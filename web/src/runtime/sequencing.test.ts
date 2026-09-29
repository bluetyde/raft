import { describe, expect, it } from "vitest";
import { agentRig, type AgentRig } from "./agent-harness";
import type { DecisionRequest } from "./protocol";
import { send } from "./test-helpers";

const has = (r: DecisionRequest, id: string) => r.candidates.some((c) => c.id === id);
const power = (rig: AgentRig) => rig.snap().indicated.log as number;
const goal = (rig: AgentRig, powerW: number | null) => send(rig.rt, { kind: "supervisor.goal", powerW });
const supervision = (rig: AgentRig) => rig.supervision()!;

describe("AI rod sequencing (headless)", () => {
  it("withdraws one rod one step toward a higher goal, with the controller off, then waits", async () => {
    const rig = await agentRig((r, n) => (n === 0 && has(r, "withdraw") ? "withdraw" : has(r, "wait") ? "wait" : "hold"));
    await goal(rig, power(rig) * 100);
    await send(rig.rt, { kind: "supervisor.enable" });
    await send(rig.rt, { kind: "time", rate: 10, paused: false });
    await rig.run(300);
    expect(has(rig.requests[0]!, "withdraw")).toBe(true);
    expect(has(rig.requests[0]!, "transient")).toBe(false);
    const cmds = () => rig.cmds("supervisor").filter(([, c]) => c.rod !== undefined);
    expect(cmds()[0]![1]).toEqual({ type: "rod.move", rod: "safety", direction: "out" });
    expect(supervision(rig).mode).toBe("stepping");
    await rig.run(8000); // the step, then the 15 s settling time, then the next request
    // the step ended by itself: a stop for that rod, at about one step of travel
    expect(cmds().some(([, c]) => c.rod === "safety" && c.direction === "stop")).toBe(true);
    expect(rig.snap().truth.rods.safety.position).toBeGreaterThan(0.04);
    expect(rig.snap().truth.rods.safety.position).toBeLessThan(0.1);
    expect(rig.snap().truth.rods.transient.position).toBe(0);
    // while sequencing, the offer is wait, not hold: the controller is off
    const later = rig.requests.at(-1)!;
    expect(has(later, "wait")).toBe(true);
    expect(has(later, "hold")).toBe(false);
    expect(has(later, "withdraw")).toBe(true); // still below the goal: the next step is offered once power has settled
    expect(supervision(rig).mode).toBe("sequencing");
  });

  it("inserts the most withdrawn coarse rod toward a lower goal", async () => {
    const rig = await agentRig((r) => (has(r, "insert") ? "insert" : null));
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await send(rig.rt, { kind: "command", clientSeq: 1, clientId: "operator", cmd: { type: "rod.move", rod: "safety", direction: "out" } });
    await rig.run(4000);
    await send(rig.rt, { kind: "command", clientSeq: 2, clientId: "operator", cmd: { type: "rod.move", rod: "safety", direction: "stop" } });
    await rig.run(200);
    await goal(rig, power(rig) / 100);
    await send(rig.rt, { kind: "supervisor.enable" });
    await rig.run(1500);
    expect(rig.requests.some((r) => has(r, "insert"))).toBe(true);
    expect(rig.cmds("supervisor").some(([, c]) => c.rod === "safety" && c.direction === "in")).toBe(true);
  });

  it("hands over to the controller when power is at the goal", async () => {
    const rig = await agentRig((r) => (has(r, "withdraw") ? "withdraw" : has(r, "engage") ? "engage" : has(r, "wait") ? "wait" : "hold"));
    await goal(rig, power(rig) * 100);
    await send(rig.rt, { kind: "supervisor.enable" });
    await send(rig.rt, { kind: "time", rate: 10, paused: false });
    await rig.run(3000); // one step, then sequencing
    expect(supervision(rig).mode).toBe("sequencing");
    await goal(rig, power(rig)); // power is now the goal
    await rig.run(4000);
    expect(rig.requests.some((r) => has(r, "engage"))).toBe(true);
    expect(supervision(rig).mode).toBe("holding");
    expect(supervision(rig).lastAction).toContain("handed over");
  });

  it("no goal means no stepping", async () => {
    const rig = await agentRig(() => "hold");
    await send(rig.rt, { kind: "supervisor.enable" });
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(1500);
    expect(rig.requests.length).toBeGreaterThan(0);
    expect(rig.requests.some((r) => has(r, "withdraw") || has(r, "insert"))).toBe(false);
  });

  it("disabling supervision in the middle of a step stops that rod", async () => {
    const rig = await agentRig((r, n) => (n === 0 && has(r, "withdraw") ? "withdraw" : null));
    await goal(rig, power(rig) * 100);
    await send(rig.rt, { kind: "supervisor.enable" });
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(500);
    expect(supervision(rig).mode).toBe("stepping");
    await send(rig.rt, { kind: "supervisor.disable" });
    await rig.run(300);
    expect(rig.snap().truth.rods.safety.moving).toBeNull();
    expect(supervision(rig).mode).toBe("off");
  });
});

describe("supervision view (what the panels show)", () => {
  it("reports the goal in effect, its source, and the script's progress", async () => {
    const rig = await agentRig(() => "hold");
    await send(rig.rt, {
      kind: "script.load",
      script: { format: "virtual-reactor-instructor-script", version: 1, name: "s", events: [
        { atSeconds: 0.5, action: "goal.set", powerW: 5, note: "raise" },
        { atSeconds: 2, action: "goal.clear", note: "back" },
      ] },
    });
    await send(rig.rt, { kind: "supervisor.enable" });
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(1000);
    let s = supervision(rig);
    expect(s).toMatchObject({ goal: 5, goalSource: "script", scriptFired: 1, scriptTotal: 2 });
    expect(s.scriptNext).toMatchObject({ note: "back" });
    await goal(rig, 7); // a panel goal set later than the script's event wins until the next script event
    s = supervision(rig);
    expect(s).toMatchObject({ goal: 7, goalSource: "panel" });
    await rig.run(2500);
    s = supervision(rig);
    expect(s).toMatchObject({ goal: null, goalSource: "none", scriptFired: 2, scriptNext: null });
  });
});
