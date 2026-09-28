/**
 * The operator's scenario strip (docs/m5-scenarios-design.md, D7a): the brief, the goals, hints, the elapsed time
 * and the final score. It shows the worker's scenario view only: goal statuses and times, never truth values.
 */

import type { ScenarioView } from "../../runtime/protocol";

/** Sim time as m:ss, or h:mm:ss from one hour. */
export function formatElapsed(t: number): string {
  const s = Math.max(0, Math.floor(t));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

const MARK = { waiting: "·", open: "○", met: "✓", failed: "✗" } as const;

export function goalLine(g: ScenarioView["goals"][number]): string {
  const when = g.t === null ? "" : g.status === "met" ? ` (at ${formatElapsed(g.t)})` : g.status === "failed" ? ` (failed at ${formatElapsed(g.t)})` : "";
  return `${MARK[g.status]} ${g.text}${when}`;
}

/** The final score, or null while the scenario runs. Gentle, as plan 05 asks: goals met, trips caused and time taken. */
export function scoreText(v: ScenarioView): string | null {
  if (!v.done) return null;
  const s = v.score;
  const time = s.lastGoalT === null ? "" : `, last goal at ${formatElapsed(s.lastGoalT)}`;
  const ended = v.endedAt !== null ? " The instructor ended the scenario." : "";
  return `Score: ${s.met} of ${s.total} goals met, ${s.trips} unexpected ${s.trips === 1 ? "trip" : "trips"}${time}.${ended}`;
}

/** The command types a scenario allows, or null when no scenario runs (everything is allowed). */
export function allowedTypes(v: ScenarioView | null): Set<string> | null {
  return v ? new Set(v.allow) : null;
}
