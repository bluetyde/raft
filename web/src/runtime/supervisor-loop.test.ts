import { describe, expect, it } from "vitest";
import { agentRig, startSupervised, type AgentRig } from "./agent-harness";
import type { DecisionResponse } from "./protocol";
import { send } from "./test-helpers";

const envelope = (r: any, over: Partial<DecisionResponse> = {}): DecisionResponse => ({
  protocolVersion: 1, sessionId: r.sessionId, temporalEpoch: r.temporalEpoch, connectionId: r.connectionId,
  requestId: r.requestId, observationStep: r.observationStep, status: "ok", ...over,
});
const scrams = (rig: AgentRig) => rig.cmds("supervisor").some(([, c]) => c.type === "scram");
/** Make the runtime treat the state as an emergency, so a SCRAM candidate is offered. */
const offerScram = (rig: AgentRig) => ((rig.rt as any).scramOffered = () => true);
const reduceText = (rig: AgentRig, i: number) => rig.requests[i]!.candidates.find((c) => c.id === "reduce")?.text;

describe("supervisor loop (headless, stub agent)", () => {
  it("asks for a decision with typed candidates, armed at the approved power", async () => {
    const rig = await agentRig(() => null);
    await startSupervised(rig);
    await rig.run(500);
    expect(rig.requests[0]!.candidates.map((c) => c.id)).toEqual(["hold", "raise", "reduce", "stop"]); // no SCRAM without an emergency
  });

  it("HOLD keeps the target and leaves the rod alone at steady power", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "hold" : null));
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(300); // let the start-up transient settle before approving the target
    await send(rig.rt, { kind: "supervisor.enable" });
    await rig.run(1000);
    expect(rig.cmds("supervisor").filter(([, c]) => c.rod === "regulating")).toEqual([]);
    // a hold reply never re-arms: the lowered-target text stays the same
    expect(reduceText(rig, 1)).toBe(reduceText(rig, 0));
  });

  it("a lowered target makes the controller insert the regulating rod", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "reduce" : null));
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(100);
    // lift the regulating rod off its stop, so there is room to insert it
    await send(rig.rt, { kind: "command", clientSeq: 1, clientId: "operator", cmd: { type: "rod.move", rod: "regulating", direction: "out" } });
    await rig.run(500);
    await send(rig.rt, { kind: "command", clientSeq: 2, clientId: "operator", cmd: { type: "rod.move", rod: "regulating", direction: "stop" } });
    await send(rig.rt, { kind: "supervisor.enable" });
    await rig.run(1000);
    const reg = rig.cmds("supervisor").filter(([, c]) => c.rod === "regulating");
    expect(reg.map(([, c]) => c.direction)).toContain("in");
    expect(reg.map(([, c]) => c.direction)).not.toContain("out");
  });

  it("REDUCE tracks a lower validated target and leaves the controller armed", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "reduce" : null));
    await startSupervised(rig);
    await rig.run(1000);
    const first = Number(/([\d.]+e[-+]\d+) W/.exec(reduceText(rig, 0)!)![1]);
    const second = Number(/([\d.]+e[-+]\d+) W/.exec(reduceText(rig, 1)!)![1]);
    expect(second).toBeCloseTo(first * 0.5, 9);
    expect(rig.requests[1]!.candidates.some((c) => c.id === "hold")).toBe(true);
  });

  it("STOP_MOTION stops every moving rod the library has, not a fixed list", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "stop" : null));
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(100);
    await send(rig.rt, { kind: "command", clientSeq: 1, clientId: "operator", cmd: { type: "rod.move", rod: "safety", direction: "out" } });
    await send(rig.rt, { kind: "supervisor.enable" });
    await rig.run(500);
    expect(rig.cmds("supervisor").some(([, c]) => c.rod === "safety" && c.direction === "stop")).toBe(true);
    expect(rig.snap().truth.rods.safety.moving).toBeNull();
    // the controller stays armed after a stop, so a rising reactor still has something acting on it
    await rig.run(1500);
    expect(rig.requests.at(-1)!.candidates.some((c) => c.id === "hold")).toBe(true);
  });

  it("paces requests: at most one per 500 ms, and a 2 s backoff after an error reply", async () => {
    const rig = await agentRig(() => "hold");
    await startSupervised(rig);
    await rig.run(3000);
    expect(rig.requests.length).toBeLessThanOrEqual(7);
    expect(rig.requests.length).toBeGreaterThanOrEqual(4);
    const err = await agentRig((r) => envelope(r, { status: "error", errorCode: "INTERNAL_ERROR" }));
    await startSupervised(err);
    await err.run(3000);
    expect(err.requests.length).toBeLessThanOrEqual(2); // one at once, the next only after the 2 s backoff
  });

  it("sends no request while the controller is off and there is no emergency", async () => {
    const rig = await agentRig(() => "hold");
    await startSupervised(rig);
    await rig.run(700);
    (rig.rt as any).controller.disable();
    const before = rig.requests.length;
    await rig.run(3000);
    expect(rig.requests.length).toBe(before);
  });

  it("RAISE moves the target up by the validated step, and a cooldown blocks the next one", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "raise" : null));
    await startSupervised(rig);
    await rig.run(1000);
    const raiseText = (i: number) => rig.requests[i]!.candidates.find((c) => c.id === "raise")?.text;
    const power = (t: string) => Number(/([\d.]+e[-+]\d+) W/.exec(t)![1]);
    const before = power(raiseText(0)!);
    // after the raise the controller targets `before`; the cooldown then removes the raise candidate
    expect(rig.requests[1]!.candidates.some((c) => c.id === "raise")).toBe(false);
    expect(Math.abs(power(reduceText(rig, 1)!) / (before * 0.5) - 1)).toBeLessThan(0.02); // texts show 3 digits
  });

  it("a raise is not offered above half the power-high trip setpoint", async () => {
    const rig = await agentRig(() => null);
    const c: any = (rig.rt as any).controller;
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(100);
    const trip = (rig.rt.engine!.lib.trips as any[]).find((x) => x.id === "power-high").predicate.value;
    c.enable(trip * 0.4); // doubling would pass half the trip setpoint
    await send(rig.rt, { kind: "supervisor.enable" });
    await rig.run(300);
    expect(rig.requests[0]!.candidates.some((x) => x.id === "raise")).toBe(false);
  });

  it("the premise states the operator's goal power and where power stands against it", async () => {
    const rig = await agentRig(() => "hold");
    await startSupervised(rig);
    await rig.run(200);
    expect(rig.requests[0]!.premise).toContain("GOAL: hold the current power");
    const p = rig.snap().indicated.log as number;
    for (const [goal, word] of [[p * 5, "below the goal"], [p / 5, "above the goal"], [p, "at the goal"]] as const) {
      await send(rig.rt, { kind: "supervisor.goal", powerW: goal });
      const before = rig.requests.length;
      await rig.rt.idle();
      await rig.run(700);
      const last = rig.requests.at(-1)!;
      expect(rig.requests.length).toBeGreaterThan(before - 1);
      expect(last.premise).toContain(word);
    }
  });

  it("a SCRAM is offered only when the runtime sees danger", async () => {
    const rig = await agentRig(() => null);
    await startSupervised(rig);
    await rig.run(200);
    expect(rig.requests[0]!.candidates.some((c) => c.id === "scram")).toBe(false);
    expect(rig.requests[0]!.premise).toContain("There is no emergency.");
  });

  it("SCRAM candidate scrams the reactor", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "scram" : null));
    offerScram(rig);
    await startSupervised(rig);
    await rig.run(500);
    expect(scrams(rig)).toBe(true);
  });

  it("a reply for another session/epoch is ignored", async () => {
    const rig = await agentRig((r) => envelope(r, { sessionId: "other", temporalEpoch: r.temporalEpoch + 5, candidateId: "scram" }));
    offerScram(rig);
    await startSupervised(rig);
    await rig.run(500);
    expect(scrams(rig)).toBe(false);
  });

  it("a reply from a window that does not own supervision is ignored", async () => {
    const rig = await agentRig(() => null);
    offerScram(rig);
    await startSupervised(rig);
    await rig.run(200);
    const r = rig.requests[0]!;
    rig.rt.receive({ kind: "decision_response", response: envelope(r, { candidateId: "scram" }) }, "other-window");
    await rig.rt.idle();
    expect(scrams(rig)).toBe(false);
  });

  it("shadow and error replies complete the request without acting or timing out", async () => {
    const rig = await agentRig((r, n) => envelope(r, n % 2 ? { status: "error", errorCode: "INTERNAL_ERROR" } : { status: "shadow", candidateId: "scram" }));
    offerScram(rig);
    await startSupervised(rig);
    await rig.run(6000); // well past the 2 s wall limit
    expect(scrams(rig)).toBe(false);
    expect(rig.requests.length).toBeGreaterThanOrEqual(3); // requests keep flowing (paced): nothing tripped a timeout
  });

  it("disabling supervision stops the rod the controller was moving", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "hold" : null));
    await startSupervised(rig);
    await rig.run(300);
    await send(rig.rt, { kind: "command", clientSeq: 1, clientId: "operator", cmd: { type: "rod.move", rod: "safety", direction: "out" } });
    await rig.run(1500);
    await send(rig.rt, { kind: "supervisor.disable" });
    await rig.run(200);
    const reg = rig.cmds("supervisor").filter(([, c]) => c.rod === "regulating");
    expect(reg.at(-1)![1].direction).toBe("stop");
    expect(rig.snap().truth.rods.regulating.moving).toBeNull();
  });

  it("an unanswered request times out on the wall clock even while the clock is paused", async () => {
    const rig = await agentRig(() => null);
    await send(rig.rt, { kind: "supervisor.enable" });
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(100);
    await send(rig.rt, { kind: "time", paused: true });
    const before = rig.requests.length;
    await rig.run(3000);
    await rig.run(3000);
    expect(before).toBeGreaterThan(0);
    expect(rig.requests.length).toBe(before); // supervision dropped: no new request after the timeout
  });
});

describe("supervision ownership", () => {
  it("a second window cannot take supervision over, and it ends when its owner window goes", async () => {
    const rig = await agentRig(() => null);
    rig.rt.connect("a", "operator");
    rig.rt.connect("b", "operator");
    rig.rt.receive({ kind: "supervisor.enable" }, "a");
    await rig.rt.idle();
    expect((rig.rt as any).supervisor.ownerPort).toBe("a");
    rig.host.drain();
    rig.rt.receive({ kind: "supervisor.enable" }, "b");
    await rig.rt.idle();
    const refused = rig.host.drain().find((m) => m.kind === "error");
    expect(refused).toMatchObject({ kind: "error", request: "supervisor.enable", code: "E_SUPERVISION_REFUSED" });
    expect((rig.rt as any).supervisor.ownerPort).toBe("a");
    rig.rt.disconnect("a");
    expect((rig.rt as any).supervisor.ownerPort).toBeNull();
  });
});
