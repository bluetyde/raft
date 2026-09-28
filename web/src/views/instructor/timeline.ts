/**
 * The instructor timeline (docs/m6-instructor-design.md §3): markers for trips, rejected commands, faults,
 * notes and the branch point, and the mapping between a point on the bar and an engine step.
 * The marks and notes come from the worker (`timeline` message), so every window shows the same timeline.
 */

import type { Annotation, Mark } from "../../runtime/protocol";

export type MarkerKind = Mark["kind"] | "note" | "fork";

export interface Marker {
  kind: MarkerKind;
  t: number;
  label: string;
}

export class Timeline {
  private list: Marker[] = [];
  /** The latest sim time the timeline covers (the current time of the session). */
  endT = 0;

  markers(): readonly Marker[] {
    return this.list;
  }

  /** Replace the markers: the worker's marks, the notes, and the point where this branch forked (if it did). */
  set(marks: readonly Mark[], notes: readonly Annotation[], forkT: number | null): void {
    this.list = [
      ...marks.map((m) => ({ ...m })),
      ...notes.map((a) => ({ kind: "note" as const, t: a.t, label: a.text })),
      ...(forkT !== null ? [{ kind: "fork" as const, t: forkT, label: "branch point" }] : []),
    ].sort((a, b) => a.t - b.t);
    for (const m of this.list) this.setEnd(m.t);
  }

  /** After a rewind or a branch switch to `t`: the timeline now ends there. */
  rewoundTo(t: number): void {
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
}
