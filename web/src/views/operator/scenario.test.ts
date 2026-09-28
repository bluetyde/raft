import { describe, expect, it } from "vitest";
import type { ScenarioView } from "../../runtime/protocol";
import { Annunciator } from "./annunciator";
import { allowedTypes, formatElapsed, goalLine, scoreText } from "./scenario";

function view(over: Partial<ScenarioView> = {}): ScenarioView {
  return {
    id: "s",
    title: "Scram and restart",
    brief: "b",
    hints: [],
    allow: ["rod.move", "scram"],
    faultsVisible: false,
    outerDt: 0.01,
    goals: [
      { id: "a", text: "Hold steady power", status: "met", t: 754.2 },
      { id: "b", text: "Scram the reactor", status: "open", t: null },
    ],
    events: [],
    score: { met: 1, failed: 0, total: 2, trips: 0, lastGoalT: 754.2 },
    done: false,
    endedAt: null,
    ...over,
  };
}

describe("operator scenario strip (SC2, D7a)", () => {
  it("formats the elapsed sim time", () => {
    expect(formatElapsed(0)).toBe("0:00");
    expect(formatElapsed(59.9)).toBe("0:59");
    expect(formatElapsed(754.2)).toBe("12:34");
    expect(formatElapsed(3725)).toBe("1:02:05");
  });

  it("writes each goal with its status and time", () => {
    const v = view();
    expect(goalLine(v.goals[0]!)).toBe("✓ Hold steady power (at 12:34)");
    expect(goalLine(v.goals[1]!)).toBe("○ Scram the reactor");
    expect(goalLine({ id: "c", text: "Restart", status: "failed", t: 900 })).toBe("✗ Restart (failed at 15:00)");
    expect(goalLine({ id: "d", text: "Later", status: "waiting", t: null })).toBe("· Later");
  });

  it("gives the score only when the scenario is done", () => {
    expect(scoreText(view())).toBeNull();
    expect(scoreText(view({ done: true, score: { met: 2, failed: 0, total: 2, trips: 1, lastGoalT: 1200 } }))).toBe(
      "Score: 2 of 2 goals met, 1 unexpected trip, last goal at 20:00.",
    );
    expect(scoreText(view({ done: true, endedAt: 800, score: { met: 0, failed: 2, total: 2, trips: 0, lastGoalT: null } }))).toBe(
      "Score: 0 of 2 goals met, 0 unexpected trips. The instructor ended the scenario.",
    );
  });

  it("knows the allowed controls, and allows everything without a scenario", () => {
    expect([...allowedTypes(view())!]).toEqual(["rod.move", "scram"]);
    expect(allowedTypes(null)).toBeNull();
  });
});

describe("instructor-fault tile (M6 D4b, for a scenario with faultsVisible)", () => {
  it("exists only when visible, and follows the alarm sequence", () => {
    const a = new Annunciator(["manual"], ["linear"], []);
    const tile = () => a.list().find((t) => t.id === "instructor:fault");
    a.instructorFault(false, true);
    expect(tile()).toBeUndefined();
    a.instructorFault(true, false);
    expect(tile()).toMatchObject({ kind: "instructor", state: "off" });
    a.instructorFault(true, true);
    expect(tile()!.state).toBe("flashing");
    a.acknowledge();
    expect(tile()!.state).toBe("lit");
    a.instructorFault(true, false);
    expect(tile()!.state).toBe("off");
    a.instructorFault(false, false);
    expect(tile()).toBeUndefined();
  });
});
