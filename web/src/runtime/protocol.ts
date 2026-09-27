/**
 * Messages between the main thread and the runtime worker (docs/c6-runtime-design.md section 4).
 * Types only. The worker is the only authority for simulation state.
 */

import type { Issue } from "../library/validate";

export const PROTOCOL_VERSION = 1;

export const SESSION_FORMAT = "virtual-reactor-session";
export const SESSION_VERSION = 1;

/** Where the worker reads a library folder from. `files` maps manifest-relative paths to bytes. */
export type LibrarySource =
  | { kind: "url"; base: string }
  | { kind: "files"; files: Record<string, ArrayBuffer> };

/** A session file: `engine.session()` plus the step it ends at (the engine's session has no end step). */
export interface SessionFile {
  format: typeof SESSION_FORMAT;
  version: typeof SESSION_VERSION;
  endStep: number;
  session: Record<string, any>;
}

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
  | { kind: "error"; request: ToWorker["kind"]; code: string; message: string }
  | { kind: "fault"; message: string };
