import { describe, expect, it } from "vitest";
import { agentRig, startSupervised } from "./agent-harness";
import { send } from "./test-helpers";

describe("supervisor loop (headless, stub agent)", () => {
  it("asks the agent for a decision once supervision is on, with typed candidates", async () => {
    const rig = await agentRig(() => null);
    await startSupervised(rig);
    await rig.run(500);
    expect(rig.requests.length).toBeGreaterThan(0);
    expect(rig.requests[0]!.candidates.map((c) => c.id)).toEqual(["hold", "reduce", "scram"]);
  });

  it("HOLD engages the controller: after a disturbance it drives the regulating rod against it", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "hold" : null));
    await startSupervised(rig);
    await rig.run(300);
    // disturbance: an operator withdraws the shim rod, so power climbs above the held target
    await send(rig.rt, { kind: "command", clientSeq: 1, clientId: "operator", cmd: { type: "rod.move", rod: "shim", direction: "out" } });
    await rig.run(3000);
    const sup = rig.cmds("supervisor").filter(([, c]) => c.rod === "regulating");
    console.log("supervisor cmds:", JSON.stringify(sup.slice(0, 6)), "power", rig.snap().truth.power);
    expect(sup.length).toBeGreaterThan(0);
    expect(sup[0]![1].direction).toBe("in");
  });

  it("SCRAM candidate scrams the reactor", async () => {
    const rig = await agentRig((_r, n) => (n === 0 ? "scram" : null));
    await startSupervised(rig);
    await rig.run(500);
    expect(rig.cmds("supervisor").some(([, c]) => c.type === "scram")).toBe(true);
  });

  it("a reply for another session/epoch must be ignored", async () => {
    const rig = await agentRig((r) => ({
      protocolVersion: 1, sessionId: "other-session", temporalEpoch: r.temporalEpoch + 5, connectionId: "x",
      requestId: r.requestId, observationStep: r.observationStep, status: "ok", candidateId: "scram",
    }));
    await startSupervised(rig);
    await rig.run(500);
    expect(rig.cmds("supervisor").some(([, c]) => c.type === "scram")).toBe(false);
  });
});
