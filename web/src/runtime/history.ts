/**
 * Checkpoint store, replay from a checkpoint, and session files (docs/c6-runtime-design.md section 8).
 */

import { Engine, ENGINE_VERSION, CheckpointError } from "../sim/engine";
import type { Library } from "../sim/library";
import { SESSION_FORMAT, SESSION_VERSION, SESSION_VERSIONS, type Annotation, type BranchInfo, type SessionFile } from "./protocol";

interface Stored {
  cp: Record<string, any>; // engine.checkpoint() without commandLog
  logLength: number;
}

/**
 * Bounded checkpoint store. Checkpoints are kept without their command log: engine.checkpoint()
 * copies the whole log, so storing it would grow with the square of the session length.
 * The log is append-only, so the entries with seq < cp.nextSeq rebuild it exactly.
 */
export class CheckpointStore {
  private items: Stored[] = [];
  thinned = false;

  constructor(readonly max: number) {
    if (!(max >= 2)) throw new RangeError("CheckpointStore needs room for at least 2 checkpoints");
  }

  add(cp: Record<string, any>): void {
    const { commandLog, ...rest } = cp;
    const stored = { cp: rest, logLength: (commandLog as unknown[]).length };
    const last = this.items[this.items.length - 1];
    if (last && last.cp.stepIndex === rest.stepIndex) {
      this.items[this.items.length - 1] = stored;
    } else {
      this.items.push(stored);
    }
    if (this.items.length > this.max) this.thin();
  }

  /** Drop every second checkpoint in the older half. The first and the latest always stay. */
  private thin(): void {
    const half = Math.floor(this.items.length / 2);
    const kept: Stored[] = [];
    for (let i = 0; i < this.items.length; i++) {
      if (i === 0 || i >= half || i % 2 === 0) kept.push(this.items[i]!);
    }
    this.items = kept;
    this.thinned = true;
  }

  steps(): number[] {
    return this.items.map((s) => s.cp.stepIndex as number);
  }

  /** The latest checkpoint at or before `step`, with its command log rebuilt from `log`. */
  atOrBefore(step: number, log: Record<string, any>[]): Record<string, any> | null {
    for (let i = this.items.length - 1; i >= 0; i--) {
      const s = this.items[i]!;
      if (s.cp.stepIndex <= step) return rebuild(s, log);
    }
    return null;
  }

  /** The step and next command seq of each stored checkpoint, oldest first. */
  entries(): { step: number; nextSeq: number }[] {
    return this.items.map((s) => ({ step: s.cp.stepIndex as number, nextSeq: s.cp.nextSeq as number }));
  }

  /** The checkpoint at exactly `step`, with its command log rebuilt from `log`, or null. */
  at(step: number, log: Record<string, any>[]): Record<string, any> | null {
    const s = this.items.find((x) => x.cp.stepIndex === step);
    return s ? rebuild(s, log) : null;
  }

  /** Remove checkpoints after `step` (their timeline was discarded by a rewind). */
  dropAfter(step: number): void {
    this.items = this.items.filter((s) => s.cp.stepIndex <= step);
  }

  copy(): CheckpointStore {
    const c = new CheckpointStore(this.max);
    c.items = [...this.items];
    c.thinned = this.thinned;
    return c;
  }

  clear(): void {
    this.items = [];
    this.thinned = false;
  }
}

function rebuild(s: Stored, log: Record<string, any>[]): Record<string, any> {
  const prefix = log.filter((c) => c.seq < s.cp.nextSeq);
  if (prefix.length !== s.logLength) {
    throw new CheckpointError(
      `command log has ${prefix.length} entries before seq ${s.cp.nextSeq}, checkpoint had ${s.logLength}`,
    );
  }
  return structuredClone({ ...s.cp, commandLog: prefix });
}

/**
 * Run `engine` to `untilStep`, submitting each logged command at its step. Same loop as
 * Engine.replay, but it starts from any engine (for example a restored checkpoint):
 * commands with seq < engine.nextSeq are already in the engine's state and are skipped.
 * `afterStep` runs after every step (the runtime takes checkpoints there).
 */
export function replayCommands(
  engine: Engine,
  commands: Record<string, any>[],
  untilStep: number,
  afterStep?: (e: Engine) => void,
): void {
  const cmds = commands.filter((c) => c.seq >= engine.nextSeq).sort((a, b) => a.seq - b.seq);
  if (cmds.length > 0 && cmds[0]!.step < engine.stepIndex) {
    throw new CheckpointError(`command seq ${cmds[0]!.seq} is at step ${cmds[0]!.step}, before the start`);
  }
  let k = 0;
  while (engine.stepIndex < untilStep) {
    while (k < cmds.length && cmds[k]!.step === engine.stepIndex) {
      engine.submit(cmds[k]!.cmd, cmds[k]!.clientId);
      k++;
    }
    if (engine.halted) return;
    engine.step();
    afterStep?.(engine);
  }
  while (k < cmds.length && cmds[k]!.step === engine.stepIndex) {
    engine.submit(cmds[k]!.cmd, cmds[k]!.clientId);
    k++;
  }
}

export function sessionFile(
  engine: Engine,
  extra: { annotations?: Annotation[]; branch?: BranchInfo; scenario?: SessionFile["scenario"] } = {},
): SessionFile {
  return {
    format: SESSION_FORMAT,
    version: SESSION_VERSION,
    endStep: engine.stepIndex,
    session: engine.session(),
    annotations: structuredClone(extra.annotations ?? []),
    ...(extra.branch ? { branch: { ...extra.branch } } : {}),
    ...(extra.scenario ? { scenario: structuredClone(extra.scenario) } : {}),
  };
}

/** Check a session file's form and pins against this engine build and library. Throws CheckpointError. */
export function checkSessionFile(file: unknown, lib: Library): SessionFile {
  const f = file as SessionFile;
  if (typeof f !== "object" || f === null || f.format !== SESSION_FORMAT || !SESSION_VERSIONS.includes(f.version)) {
    throw new CheckpointError(`not a ${SESSION_FORMAT} file, version ${SESSION_VERSIONS.join(" or ")}`);
  }
  if (f.annotations !== undefined && !validAnnotations(f.annotations)) {
    throw new CheckpointError("annotations must be a list of {id, step, t, text}");
  }
  if (f.scenario !== undefined) {
    const sc = f.scenario as Record<string, unknown>;
    if (typeof sc !== "object" || sc === null || typeof sc["id"] !== "string" || typeof sc["digest"] !== "string" || typeof sc["thresholds"] !== "object") {
      throw new CheckpointError("scenario must be {id, digest, thresholds}");
    }
  }
  if (!Number.isInteger(f.endStep) || f.endStep < 0) {
    throw new CheckpointError("endStep must be a non-negative integer");
  }
  const s = f.session;
  if (typeof s !== "object" || s === null || typeof s.pins !== "object" || !Array.isArray(s.commands)) {
    throw new CheckpointError("session has no pins or commands");
  }
  if (s.pins.engineVersion !== ENGINE_VERSION) {
    throw new CheckpointError(`session from engine ${s.pins.engineVersion}, this is ${ENGINE_VERSION}`);
  }
  if (s.pins.libraryDigest !== lib.digest) {
    throw new CheckpointError("library digest doesn't match the session");
  }
  return f;
}

function validAnnotations(a: unknown): a is Annotation[] {
  return (
    Array.isArray(a) &&
    a.every(
      (x) =>
        typeof x === "object" &&
        x !== null &&
        Number.isInteger(x.id) &&
        Number.isInteger(x.step) &&
        x.step >= 0 &&
        typeof x.t === "number" &&
        typeof x.text === "string",
    )
  );
}
