import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadSyntheticCore, repoRoot } from "../sim/testing";
import { describeReason, evaluateValidity, resolveEnvelope, validateEnvelope, type EnvelopeSpec } from "./envelope";
import { agentRig } from "./agent-harness";
import { Runtime } from "./runtime";
import { FakeHost, readFolder, send } from "./test-helpers";

const spec = (over: Partial<EnvelopeSpec> = {}): EnvelopeSpec => ({
  summary: "low power",
  power: { fromTrip: "power-high", times: 0.15, source: "test" },
  fuelTemp: { max: 400, source: "test" },
  modes: ["steady"],
  ...over,
});

describe("envelope validation and resolution", () => {
  it("every limit needs a source or comes from the library; unknown trips are refused", async () => {
    const lib = await loadSyntheticCore();
    expect(validateEnvelope(spec(), lib)).toEqual([]);
    expect(validateEnvelope(spec({ power: { fromTrip: "power-high", times: 0.15, source: "" } }), lib).map((i) => i.code)).toEqual(["E_SCN_SOURCE"]);
    expect(validateEnvelope(spec({ power: { fromTrip: "no-such-trip", times: 0.15, source: "x" } }), lib).map((i) => i.code)).toEqual(["E_SCN_ENVELOPE"]);
    expect(validateEnvelope(spec({ fuelTemp: { max: 400, source: " " } }), lib).map((i) => i.code)).toEqual(["E_SCN_SOURCE"]);
  });

  it("resolves the power limit from the trip setpoint", async () => {
    const lib = await loadSyntheticCore();
    const trip = (lib.trips as any[]).find((t) => t.id === "power-high").predicate.value;
    expect(resolveEnvelope(spec(), lib).powerMaxW).toBeCloseTo(trip * 0.15, 6);
  });
});

describe("known limits", () => {
  it("each needs text and a source, and is always shown; they keep a supported state at caution", async () => {
    const lib = await loadSyntheticCore();
    expect(validateEnvelope(spec({ knownLimits: [{ text: "x", source: "" }] }), lib).map((i) => i.code)).toEqual(["E_SCN_SOURCE"]);
    expect(validateEnvelope(spec({ knownLimits: [{ text: " ", source: "s" }] }), lib).map((i) => i.code)).toEqual(["E_SCN_ENVELOPE"]);
    const env = { summary: "s", powerMaxW: 100, powerSource: "p", fuelTempMaxK: null, fuelTempSource: null, modes: null, knownLimits: ["the model disagrees with measurement"] };
    const v = evaluateValidity({ status: "supported", reasons: [] }, env, { power: 1, fuelTemp: 300, mode: "steady" });
    expect(v.level).toBe("caution");
    expect(v.messages).toContain("the model disagrees with measurement");
  });
});

describe("validity view", () => {
  const env = { summary: "s", powerMaxW: 100, powerSource: "p", fuelTempMaxK: 400, fuelTempSource: "t", modes: ["steady"], knownLimits: [] };
  const unvalidated = { status: "unvalidated", reasons: ["R_LIBRARY_EXPERIMENTAL", "R_JOINT_UNCHECKED"] };

  it("caution while the model is unvalidated and the state is inside the envelope", () => {
    const v = evaluateValidity(unvalidated, env, { power: 10, fuelTemp: 300, mode: "steady" });
    expect(v).toMatchObject({ level: "caution", envelope: "inside" });
    expect(v.messages.join(" ")).toContain("not been checked against measured");
  });

  it("warning, with the lesson's own limits first, when the state leaves the envelope", () => {
    const v = evaluateValidity(unvalidated, env, { power: 500, fuelTemp: 450, mode: "pulse" });
    expect(v.level).toBe("warning");
    expect(v.envelope).toBe("outside");
    expect(v.messages[0]).toContain("above this lesson's limit");
    expect(v.messages.filter((m) => m.includes("limit") || m.includes("covers")).length).toBe(3);
  });

  it("warning when the engine says the state is outside the data range; ok only when supported and inside", () => {
    expect(evaluateValidity({ status: "outOfDomain", reasons: ["R_DOMAIN_TFUEL"] }, null, { power: 1, fuelTemp: 300, mode: "steady" })).toMatchObject({
      level: "warning",
      envelope: "none",
    });
    expect(evaluateValidity({ status: "supported", reasons: [] }, env, { power: 1, fuelTemp: 300, mode: "steady" }).level).toBe("ok");
  });
});

describe("runtime: validity message and the AI's power ceiling", () => {
  const scenario = (envelope?: EnvelopeSpec) => ({
    ...JSON.parse(readFileSync(join(repoRoot, "web", "src", "app", "scenarios", "synthetic-power-ascension.json"), "utf8")),
    id: "env-test",
    ...(envelope ? { envelope } : {}),
  });

  it("posts the view, and never offers a raise past the lesson's limit", async () => {
    const free = await agentRig(() => "hold", { scenario: scenario() });
    const p = free.snap().truth.power as number;
    const trip = (free.rt.engine!.lib.trips as any[]).find((t) => t.id === "power-high").predicate.value;
    await send(free.rt, { kind: "supervisor.enable" });
    await send(free.rt, { kind: "time", rate: 1, paused: false });
    await free.run(1500);
    // without a lesson limit the 50 % trip ceiling allows a doubling from this power
    expect(free.requests.some((r) => r.candidates.some((c) => c.id === "raise"))).toBe(true);

    // a lesson whose limit is 1.5 x the present power: doubling would pass it
    const rig = await agentRig(() => "hold", { scenario: scenario({ summary: "x", power: { fromTrip: "power-high", times: (p * 1.5) / trip, source: "test" } }) });
    await send(rig.rt, { kind: "supervisor.enable" });
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(1500);
    expect(rig.requests.length).toBeGreaterThan(0);
    expect(rig.requests.every((r) => !r.candidates.some((c) => c.id === "raise"))).toBe(true);
    expect(rig.validity()).toMatchObject({ envelope: "inside", summary: "x" });
  });

  it("an instructor goal above the limit is clamped, and the status says so", async () => {
    const free = await agentRig(() => "hold", { scenario: scenario() });
    const p = free.snap().truth.power as number;
    const trip = (free.rt.engine!.lib.trips as any[]).find((t) => t.id === "power-high").predicate.value;
    const rig = await agentRig(() => "hold", { scenario: scenario({ summary: "x", power: { fromTrip: "power-high", times: (p * 3) / trip, source: "test" } }) });
    await send(rig.rt, { kind: "supervisor.goal", powerW: p * 100 });
    await send(rig.rt, { kind: "supervisor.enable" });
    await send(rig.rt, { kind: "time", rate: 1, paused: false });
    await rig.run(800);
    const s = rig.supervision()!;
    expect(s.goal).toBeCloseTo(p * 100, 9);
    expect(s.goalLimit).toBeCloseTo(p * 3, 9);
    expect(rig.requests[0]!.premise).toContain(`bring power to ${(p * 3).toExponential(2)} W`);
  });
});

describe("the shipped lesson: low-power ascension on the OpenMC TRIGA 242 library", () => {
  it("starts inside the envelope with a caution (not a data-range warning), and the AI can run it", async () => {
    const files = readFolder(join(repoRoot, "libraries", "triga-jsi-242-openmc"));
    const lesson = JSON.parse(readFileSync(join(repoRoot, "web", "src", "app", "scenarios", "triga-242-openmc-low-power-ascension.json"), "utf8"));
    const host = new FakeHost();
    const rt = new Runtime(host);
    rt.receive({ kind: "load", protocol: 1, source: { kind: "files", files }, scenario: lesson });
    await rt.idle();
    expect(rt.engine, JSON.stringify(host.last("loadFailed"))).not.toBeNull();
    // withdraw the large rods a little and let the clock run for a minute of simulation time
    let seq = 1;
    for (const rod of ["safety", "shim"]) rt.receive({ kind: "command", clientSeq: seq++, clientId: "operator", cmd: { type: "rod.move", rod, direction: "out" } });
    await send(rt, { kind: "step", n: 3000 });
    const v = host.last("validity")!.view;
    expect(v.envelope).toBe("inside");
    expect(v.level).toBe("caution");
    expect(v.messages.some((m) => m.includes("outside the range the data covers"))).toBe(false); // the sink-temperature artefact is gone
    expect(v.messages.join(" ")).toContain("not been checked against measured");
    expect(v.summary).toContain("low-power ascension");
    // a window that subscribed late asks again and gets the current view
    host.drain();
    await send(rt, { kind: "resync" });
    expect(host.last("validity")!.view).toEqual(v);
  });
});

describe("the reasons the banner shows", () => {
  it("names the rod-shadowing and boron limits in words, not as a rod called INTERACTION", () => {
    expect(describeReason("R_DOMAIN_ROD_INTERACTION")).toMatch(/shadowing each other/);
    expect(describeReason("R_DOMAIN_ROD_INTERACTION")).not.toMatch(/INTERACTION rod/);
    expect(describeReason("R_DOMAIN_BORON")).toBe("Boron is outside the range the data covers.");
    expect(describeReason("R_DOMAIN_ROD_SAFETY")).toBe("The SAFETY rod is outside the range the data covers.");
    expect(describeReason("R_JOINT_UNCHECKED")).not.toMatch(/added as if/);
  });
});
