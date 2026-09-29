import { describe, expect, it } from "vitest";
import { agentRig, startSupervised, type AgentRig } from "./agent-harness";
import type { DecisionResponse } from "./protocol";
import { send } from "./test-helpers";

const envelope = (r: any, over: Partial<DecisionResponse> = {}): DecisionResponse => ({
  protocolVersion: 1, sessionId: r.sessionId, temporalEpoch: r.temporalEpoch, connectionId: r.connectionId,
  requestId: r.requestId, observationStep: r.observationStep, status: "ok", ...over,
});
const scrams = (rig: AgentRig) => rig.cmds("supervisor").some(([, c]) => c.type === "scram");
const reduceText = (rig: AgentRig, i: number) => rig.requests[i]!.candidates.find((c) => c.id === "reduce")?.text;

describe("supervisor loop (headless, stub agent)", () => {
  it("asks for a decision with typed candidates, armed at the approved power", async () => {
    const rig = await agentRig(() => null);
    await startSupervised(rig);
    await rig.run(500);
    expect(rig.requests[0]!.candidates.map((c) => c.id)).toEqual(["hold", "reduce", "stop", "scram"]);
  });

  it("HOLD keeps the target and drives the regulating rod against a disturbance", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "hold" : null));
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(300); // let the start-up transient settle before approving the target
    await send(rig.rt, { kind: "supervisor.enable" });
    await send(rig.rt, { kind: "command", clientSeq: 1, clientId: "operator", cmd: { type: "rod.move", rod: "shim", direction: "out" } });
    await rig.run(3000);
    const sup = rig.cmds("supervisor").filter(([, c]) => c.rod === "regulating");
    expect(sup.length).toBeGreaterThan(0);
    expect(sup[0]![1].direction).toBe("in");
    // a hold reply never re-arms: the lowered-target text stays the same
    expect(reduceText(rig, 1)).toBe(reduceText(rig, 0));
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

  it("SCRAM candidate scrams the reactor", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "scram" : null));
    await startSupervised(rig);
    await rig.run(500);
    expect(scrams(rig)).toBe(true);
  });

  it("a reply for another session/epoch is ignored", async () => {
    const rig = await agentRig((r) => envelope(r, { sessionId: "other", temporalEpoch: r.temporalEpoch + 5, candidateId: "scram" }));
    await startSupervised(rig);
    await rig.run(500);
    expect(scrams(rig)).toBe(false);
  });

  it("a reply from a window that does not own supervision is ignored", async () => {
    const rig = await agentRig(() => null);
    await startSupervised(rig);
    await rig.run(200);
    const r = rig.requests[0]!;
    rig.rt.receive({ kind: "decision_response", response: envelope(r, { candidateId: "scram" }) }, "other-window");
    await rig.rt.idle();
    expect(scrams(rig)).toBe(false);
  });

  it("shadow and error replies complete the request without acting or timing out", async () => {
    const rig = await agentRig((r, n) => envelope(r, n % 2 ? { status: "error", errorCode: "INTERNAL_ERROR" } : { status: "shadow", candidateId: "scram" }));
    await startSupervised(rig);
    await rig.run(6000); // well past the 2 s wall limit
    expect(scrams(rig)).toBe(false);
    expect(rig.requests.length).toBeGreaterThan(3); // requests keep flowing: nothing tripped a timeout
  });

  it("disabling supervision stops the rod the controller was moving", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "hold" : null));
    await startSupervised(rig);
    await rig.run(300);
    await send(rig.rt, { kind: "command", clientSeq: 1, clientId: "operator", cmd: { type: "rod.move", rod: "shim", direction: "out" } });
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
