/**
 * Messages between the main thread and the runtime worker (docs/c6-runtime-design.md section 4).
 * Types only. The worker is the only authority for simulation state.
 */

import type { Issue } from "../library/validate";

export const PROTOCOL_VERSION = 1;

export const SESSION_FORMAT = "virtual-reactor-session";
/** Version 2 adds annotations and the branch (docs/m6-instructor-design.md, D6). Version 1 files still import. */
export const SESSION_VERSION = 2;
export const SESSION_VERSIONS: readonly number[] = [1, 2];

/** Where the worker reads a library folder from. `files` maps manifest-relative paths to bytes. */
export type LibrarySource =
  | { kind: "url"; base: string }
  | { kind: "files"; files: Record<string, ArrayBuffer> };

/** A session file: `engine.session()` plus the step it ends at (the engine's session has no end step). */
export interface SessionFile {
  format: typeof SESSION_FORMAT;
  version: 1 | 2;
  endStep: number;
  session: Record<string, any>;
  /** Version 2: notes on the timeline. Replay ignores them. */
  annotations?: Annotation[];
  /** Version 2: where this timeline came from, in the runtime that wrote the file. */
  branch?: BranchInfo;
}

/** A note on the timeline, at an engine step. */
export interface Annotation {
  id: number;
  step: number;
  t: number;
  text: string;
}

/** A timeline marker that the runtime derives from engine events. */
export interface Mark {
  kind: "trip" | "rejected" | "fault";
  t: number;
  label: string;
}

/** A branch's place in the tree: `parent` is null for the first timeline of a load or an import. */
export interface BranchInfo {
  id: number;
  parent: number | null;
  forkStep: number;
}

/** A branch as the compare table shows it (amendment 4: fork step and command count next to the final values). */
export interface BranchSummary extends BranchInfo {
  endStep: number;
  commandCount: number;
  annotationCount: number;
  final: {
    t: number;
    power: number;
    fuelTemp: number;
    coolantTemp: number;
    xenon: number;
    tripped: boolean;
    latched: string[];
  };
}

/** The most branches the runtime keeps. At the limit, the oldest goes first. */
export const MAX_BRANCHES = 32;

/**
 * The longest outer step at which pulses are allowed (docs/m6-instructor-design.md, amendment 1).
 * A session with a longer step is "coarse": it rejects pulse mode and rod firing with REJ_COARSE_STEP.
 */
export const PULSE_MAX_OUTER_DT = 0.01;

export function isCoarse(outerDt: number): boolean {
  return outerDt > PULSE_MAX_OUTER_DT * (1 + 1e-9);
}

/** Texts for the rejection reasons that the runtime (not the engine) gives. */
export const RUNTIME_REJECTIONS: Record<string, string> = {
  REJ_COARSE_STEP: `pulse mode and rod firing need an outer step of ${PULSE_MAX_OUTER_DT * 1000} ms or less, and this session's step is longer`,
};

/** The faults active in the engine after a step (instrument faults by id, and the total inserted reactivity). */
export interface ActiveFaults {
  instruments: Record<string, string>;
  extraRho: number;
}

/**
 * What a window may do (docs/m6-instructor-design.md, D2a and amendment 3). The worker enforces it.
 * "full" is the one window of a dedicated worker, or a window with both panels.
 */
export type Role = "full" | "instructor" | "operator";
export const ROLES: readonly Role[] = ["full", "instructor", "operator"];

/** Requests an operator window may not send. It may also not send fault commands (`fault.*`). */
export const OPERATOR_FORBIDDEN: readonly ToWorker["kind"][] = [
  "load",
  "time",
  "step",
  "rewind",
  "session.import",
  "branch.switch",
  "annotate",
  "annotation.delete",
];

/** Why the clock runs slower than requested, or is stopped. */
export type ClockLimit = "cpu" | "halted" | "solver" | null;

export type ToWorker =
  | {
      kind: "load";
      protocol: number;
      source: LibrarySource;
      init?: Record<string, any>;
      seed?: number;
      config?: Record<string, any>;
    }
  | { kind: "command"; clientSeq: number; clientId: string; cmd: unknown }
  | { kind: "time"; rate?: number; paused?: boolean }
  | { kind: "step"; n: number }
  | { kind: "rewind"; step: number }
  | { kind: "session.export" }
  | { kind: "session.import"; file: SessionFile }
  | { kind: "annotate"; text: string; step?: number }
  | { kind: "annotation.delete"; id: number }
  | { kind: "branch.switch"; id: number }
  /** A window says which role it has. A shared worker needs it before any other message. */
  | { kind: "attach"; role: Role }
  /** A window closes (sent on pagehide), so the worker stops sending to it. */
  | { kind: "detach" }
  | { kind: "frameAck" };

/** The lowest and highest non-null reading of one instrument over some steps, with their sim times. */
export interface Extreme {
  min: number;
  tMin: number;
  max: number;
  tMax: number;
}

export interface LoadedInfo {
  libraryId: string;
  digest: string;
  pins: Record<string, any>;
  outerDt: number;
}

export type FromWorker =
  | ({ kind: "loaded"; protocol: number } & LoadedInfo)
  /** The answer to `attach`: the role, and what is loaded now (null if nothing). */
  | { kind: "attached"; role: Role; loaded: LoadedInfo | null }
  | { kind: "loadFailed"; protocol: number; issues: Issue[] }
  | { kind: "queued"; clientSeq: number; seq: number; step: number; t: number }
  | {
      kind: "ack";
      clientSeq: number;
      seq: number | null;
      status: "accepted" | "rejected";
      reason: string | null;
      t: number;
    }
  | {
      kind: "snapshot";
      snapshot: Record<string, any>;
      shape?: Float32Array;
      /** Each instrument's extremes over every engine step since the previous snapshot (so a chart keeps a peak between snapshots). */
      extremes?: Record<string, Extreme>;
      /** The faults active at this snapshot (for the instructor view; the operator panel does not read them). */
      faults?: ActiveFaults;
    }
  | { kind: "events"; events: Record<string, any>[] }
  | {
      kind: "clock";
      rate: number;
      achievedRate: number;
      paused: boolean;
      limited: ClockLimit;
      reason: string | null;
      t: number;
      step: number;
    }
  | { kind: "history"; checkpointSteps: number[]; thinned: boolean }
  | { kind: "rewound"; step: number; t: number; previous: SessionFile }
  | { kind: "session"; file: SessionFile }
  | {
      kind: "timeline";
      /** The current branch, with its live summary. */
      current: BranchSummary;
      /** The other branches, oldest first. */
      branches: BranchSummary[];
      marks: Mark[];
      annotations: Annotation[];
    }
  | { kind: "error"; request: ToWorker["kind"]; code: string; message: string }
  | { kind: "fault"; message: string };
