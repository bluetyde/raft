/**
 * Branches, timeline marks and branch switching (docs/m6-instructor-design.md, D1 and §4).
 * A branch is a session file (the command log), its marks and a summary of its final values.
 * Only the current branch keeps checkpoints, so memory stays bounded.
 */

import { Engine, CheckpointError } from "../sim/engine";
import type { Library } from "../sim/library";
import { CheckpointStore, replayCommands } from "./history";
import type { BranchInfo, BranchSummary, Mark, SessionFile } from "./protocol";

export interface Branch {
  info: BranchInfo;
  file: SessionFile;
  marks: Mark[];
  summary: BranchSummary;
}

const FAULT_COMMANDS = new Set(["fault.instrument", "fault.reactivity", "pump.set"]);

function faultLabel(cmd: Record<string, any>): string {
  if (cmd["type"] === "fault.instrument") return `${cmd["instrument"]}: ${cmd["kind"]}`;
  if (cmd["type"] === "fault.reactivity") return `reactivity ${(Number(cmd["deltaRho"]) * 1e5).toFixed(1)} pcm`;
  return `pump ${cmd["pump"]} ${cmd["on"] ? "on" : "off"}`;
}

/** Marks from engine events: trips, rejected commands, and accepted fault commands (looked up in the command log by seq). */
export function marksFrom(events: Record<string, any>[], commandLog: Record<string, any>[]): Mark[] {
  const bySeq = new Map<number, Record<string, any>>();
  for (const c of commandLog) bySeq.set(c.seq, c.cmd);
  const out: Mark[] = [];
  for (const e of events) {
    if (e["type"] === "trip") out.push({ kind: "trip", t: e["t"], label: `trip ${e["id"]}` });
    else if (e["type"] === "command") {
      if (e["status"] === "rejected") out.push({ kind: "rejected", t: e["t"], label: `${e["clientId"]}: ${e["reason"]}` });
      else {
        const cmd = bySeq.get(e["seq"]);
        if (cmd && FAULT_COMMANDS.has(cmd["type"])) out.push({ kind: "fault", t: e["t"], label: faultLabel(cmd) });
      }
    }
  }
  return out;
}

/**
 * The marks that stay after a rewind to time `t`. Trips at or before `t` stay. Command marks at `t` itself go:
 * those commands were logged at that step, so they are still queued and mark again when they apply.
 */
export function marksBefore(marks: Mark[], t: number, outerDt: number): Mark[] {
  const eps = 1e-9 * outerDt;
  return marks.filter((m) => (m.kind === "trip" ? m.t <= t + eps : m.t < t - eps));
}

export function summarize(e: Engine, info: BranchInfo, annotationCount: number): BranchSummary {
  const s = e.snapshot(false);
  return {
    ...info,
    endStep: e.stepIndex,
    commandCount: e.commandLog.length,
    annotationCount,
    final: {
      t: s.t,
      power: s.truth.power,
      fuelTemp: s.truth.fuelTemp,
      coolantTemp: s.truth.coolantTemp,
      xenon: s.truth.xenon,
      tripped: s.tripped,
      latched: [...s.trips.latched],
    },
  };
}

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * Build the engine for `target` (a session file of the same library). It starts from the latest checkpoint in `store`
 * that both timelines share: same pins, initial state and seed, and the same commands before the checkpoint's next seq.
 * Replay is deterministic, so this gives the same state as a replay from step 0 (a test checks it).
 * Without such a checkpoint it starts from step 0. The store is not changed; the result has its own.
 */
export function buildBranch(
  lib: Library,
  current: Engine,
  store: CheckpointStore,
  target: SessionFile,
  /** The runtime's checkpoint rule, run after each replayed step. */
  checkpoint: (st: CheckpointStore, e: Engine) => void,
): { engine: Engine; store: CheckpointStore; fromStep: number } {
  const ts = target.session;
  const cs = current.session();
  const takeEvery = (st: CheckpointStore) => (x: Engine) => checkpoint(st, x);
  if (same(ts.pins, cs.pins) && same(ts.init, cs.init) && ts.seed === cs.seed) {
    const log = current.commandLog;
    const entries = store.entries().filter((c) => c.step <= target.endStep).reverse();
    for (const { step, nextSeq } of entries) {
      const mine = log.filter((c) => c.seq < nextSeq);
      const theirs = ts.commands.filter((c: any) => c.seq < nextSeq);
      if (!same(mine, theirs)) continue;
      if (ts.commands.some((c: any) => c.seq >= nextSeq && c.step < step)) continue;
      const cp = store.at(step, log);
      if (!cp) continue;
      const engine = Engine.restore(lib, cp);
      const own = store.copy();
      own.dropAfter(step);
      replayCommands(engine, ts.commands, target.endStep, takeEvery(own));
      return { engine, store: own, fromStep: step };
    }
  }
  const engine = new Engine(lib, ts.init, ts.seed, ts.pins.config);
  const own = new CheckpointStore(store.max);
  own.add(engine.checkpoint());
  replayCommands(engine, ts.commands, target.endStep, takeEvery(own));
  if (engine.stepIndex !== target.endStep && !engine.halted) {
    throw new CheckpointError(`replay stopped at step ${engine.stepIndex}, not ${target.endStep}`);
  }
  return { engine, store: own, fromStep: 0 };
}
