/**
 * The instructor timeline (docs/m6-instructor-design.md §3): markers for trips, rejected commands and
 * faults, and the mapping between a point on the bar and an engine step.
 */

export type MarkerKind = "trip" | "rejected" | "fault";

export interface Marker {
  kind: MarkerKind;
  t: number;
  label: string;
}

/** The commands the instructor view marks as faults. */
export function isFaultCommand(type: unknown): boolean {
  return type === "fault.instrument" || type === "fault.reactivity" || type === "pump.set";
}

export class Timeline {
  private list: Marker[] = [];
  /** The latest sim time the timeline covers (the current time of the session). */
  endT = 0;

  markers(): readonly Marker[] {
    return this.list;
  }

  /** Add markers for the trips and rejected commands in a batch of engine events. */
  onEvents(events: Record<string, any>[]): void {
    for (const e of events) {
      if (e["type"] === "trip") this.add({ kind: "trip", t: e["t"], label: `trip ${e["id"]}` });
      else if (e["type"] === "command" && e["status"] === "rejected") {
        this.add({ kind: "rejected", t: e["t"], label: `${e["clientId"]}: ${e["reason"]}` });
      }
    }
  }

  /** Add a marker for a fault command that the instructor sent and the engine accepted. */
  onFault(t: number, label: string): void {
    this.add({ kind: "fault", t, label });
  }

  /** After a rewind to `t`: markers after it belong to the old timeline. */
  rewoundTo(t: number): void {
    this.list = this.list.filter((m) => m.t <= t + 1e-9);
    this.endT = t;
  }

  /** Clear all markers (a new session). */
  reset(): void {
    this.list = [];
    this.endT = 0;
  }

  setEnd(t: number): void {
    this.endT = Math.max(this.endT, t);
  }

  /** Where a time sits on the bar, from 0 (step 0) to 1 (the end). */
  position(t: number): number {
    return this.endT > 0 ? Math.min(1, Math.max(0, t / this.endT)) : 0;
  }

  /** The engine step for a point on the bar (0 to 1), rounded to the nearest step. */
  stepAt(fraction: number, outerDt: number): number {
    const endStep = Math.round(this.endT / outerDt);
    return Math.min(endStep, Math.max(0, Math.round(Math.min(1, Math.max(0, fraction)) * endStep)));
  }

  private add(m: Marker): void {
    this.list.push(m);
    this.setEnd(m.t);
  }
}
