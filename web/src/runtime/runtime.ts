/**
 * The simulation runtime: clock, command bus, snapshot and event stream, history.
 * Design: docs/c6-runtime-design.md. It uses only the engine's public API.
 *
 * No Worker or DOM APIs here: the host gives the wall clock, a timer and a way to post
 * messages, so tests drive the runtime with a fake clock (worker.ts is the real host).
 */

import { validateCommand } from "../contracts/validate";
import type { LibraryReader } from "../library/platform";
import type { Issue } from "../library/validate";
import { Engine, InitError } from "../sim/engine";
import { LibraryError, loadLibrary, type Library } from "../sim/library";
import { CheckpointStore, checkSessionFile, replayCommands, sessionFile } from "./history";
import {
  PROTOCOL_VERSION,
  type ClockLimit,
  type Extreme,
  type FromWorker,
  type LibrarySource,
  type SessionFile,
  type ToWorker,
} from "./protocol";
import { readerFor } from "./readers";

type FetchLike = Parameters<typeof readerFor>[1];

export interface RuntimeHost {
  /** Wall time in ms (performance.now() in the worker). */
  now(): number;
  /** Run `fn` after `delayMs` (0 = yield, so pending messages are handled first). */
  schedule(fn: () => void, delayMs: number): void;
  post(msg: FromWorker, transfer?: Transferable[]): void;
  fetch?: FetchLike;
}

export interface RuntimeOptions {
  /** Longest wall time of one batch of steps before the worker yields to messages. */
  sliceMs: number;
  /** When the sim is more than this much wall time behind its target, the clock re-anchors instead of racing. */
  lagLimitS: number;
  snapshotHz: number;
  checkpointEveryS: number;
  maxCheckpoints: number;
  /** Send the power shape again when a rod moved more than this (fraction withdrawn) ... */
  shapeRodTol: number;
  /** ... or the fuel temperature changed more than this (K). */
  shapeTempTol: number;
  /** How often the clock message repeats while running. */
  clockReportMs: number;
}

export const DEFAULT_OPTIONS: RuntimeOptions = {
  sliceMs: 4,
  lagLimitS: 0.25,
  snapshotHz: 30,
  checkpointEveryS: 10,
  maxCheckpoints: 128,
  shapeRodTol: 1e-3,
  shapeTempTol: 0.5,
  clockReportMs: 1000,
};

/** Reads each path once: loadLibrary validates first and then reads the files again. */
function cachingReader(inner: LibraryReader): LibraryReader {
  const cache = new Map<string, Promise<Uint8Array | null>>();
  return {
    read(relPath: string) {
      let p = cache.get(relPath);
      if (!p) {
        p = inner.read(relPath);
        cache.set(relPath, p);
      }
      return p;
    },
  };
}

function everySteps(seconds: number, outerDt: number): number {
  return Math.max(1, Math.round(seconds / outerDt));
}

/** Store a checkpoint of `eng` if one is due (every `every` steps, or `always`) and newer than the last. */
function checkpointInto(store: CheckpointStore, eng: Engine, every: number, always: boolean): boolean {
  const last = store.steps().at(-1);
  if ((always || eng.stepIndex % every === 0) && (last === undefined || eng.stepIndex > last)) {
    store.add(eng.checkpoint());
    return true;
  }
  return false;
}

export class Runtime {
  readonly options: RuntimeOptions;
  private lib: Library | null = null;
  private eng: Engine | null = null;

  private paused = true;
  private rate = 1;
  private anchorWall = 0;
  private anchorSim = 0;
  private limited: ClockLimit = null;
  private limitReason: string | null = null;
  private faulted = false;
  private lastCpuLimitWall = -Infinity;
  private tickToken = 0;
  private tickScheduled = false;
  private samples: [wall: number, sim: number][] = [];
  private lastClockPost = -Infinity;
  private lastClockKey = "";

  private eventCursor = 0;
  private pendingAcks = new Map<number, number>(); // engine seq -> clientSeq

  private awaitingFrameAck = false;
  private lastSnapWall = -Infinity;
  private lastSnapStep = -1;
  private forceSnapshot = false;
  private forceShape = true;
  private extremes: Record<string, Extreme> = {};
  private lastShapeRods: Record<string, number> = {};
  private lastShapeTfuel = NaN;

  private history: CheckpointStore;
  private checkpointEvery = 1;
  private historyDirty = false;

  private inbox: Promise<void> = Promise.resolve();

  constructor(
    private readonly host: RuntimeHost,
    options: Partial<RuntimeOptions> = {},
  ) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.history = new CheckpointStore(this.options.maxCheckpoints);
  }

  /** Handle one message. Messages are handled in arrival order; a load finishes before the next message. */
  receive(msg: ToWorker): void {
    this.inbox = this.inbox
      .then(() => this.handle(msg))
      .catch((err: unknown) => this.host.post({ kind: "fault", message: String(err) }));
  }

  /** Resolves when every message received so far has been handled (for tests and the host). */
  idle(): Promise<void> {
    return this.inbox;
  }

  /** The engine, read-only, for tests and diagnostics. Views never get it. */
  get engine(): Engine | null {
    return this.eng;
  }

  private async handle(msg: ToWorker): Promise<void> {
    switch (msg.kind) {
      case "load":
        return this.load(msg.source, msg.init, msg.seed, msg.config);
      case "command":
        return this.command(msg.clientSeq, msg.clientId, msg.cmd);
      case "time":
        return this.setTime(msg.rate, msg.paused);
      case "step":
        return this.stepN(msg.n);
      case "rewind":
        return this.rewind(msg.step);
      case "session.export":
        return this.exportSession();
      case "session.import":
        return this.importSession(msg.file);
      case "frameAck":
        return this.frameAck();
      default:
        this.error((msg as { kind: string }).kind as ToWorker["kind"], "E_UNKNOWN_MESSAGE", "unknown message kind");
    }
  }

  private error(request: ToWorker["kind"], code: string, message: string): void {
    this.host.post({ kind: "error", request, code, message });
  }

  // ---- loading ----

  private async load(
    source: LibrarySource,
    init: Record<string, any> | undefined,
    seed: number | undefined,
    config: Record<string, any> | undefined,
  ): Promise<void> {
    this.stopClock();
    // A failed load keeps the previous library and engine, paused; the clock message says so.
    const fail = (issues: Issue[]) => {
      this.host.post({ kind: "loadFailed", protocol: PROTOCOL_VERSION, issues });
      this.afterChange();
    };
    let lib: Library;
    try {
      lib = await loadLibrary(cachingReader(readerFor(source, this.host.fetch)));
    } catch (err) {
      if (err instanceof LibraryError) return fail(err.issues);
      return fail([{ code: "E_READ", path: "", message: String(err) }]);
    }
    let eng: Engine;
    try {
      eng = new Engine(lib, init, seed ?? 1, config);
    } catch (err) {
      if (err instanceof InitError) return fail([{ code: err.code, path: "init", message: err.message }]);
      return fail([{ code: "E_INIT_INVALID", path: "init", message: String(err) }]);
    }
    this.rejectPending("REJ_SESSION_REPLACED");
    this.lib = lib;
    this.history.clear();
    this.install(eng);
    this.host.post({
      kind: "loaded",
      protocol: PROTOCOL_VERSION,
      libraryId: lib.manifest.id,
      digest: lib.digest,
      pins: eng.pins(),
      outerDt: eng.config.outerDt,
    });
    this.afterChange();
  }

  /** Make `eng` the current engine, after a load, rewind or import. The clock stays paused. */
  private install(eng: Engine): void {
    this.eng = eng;
    this.extremes = {}; // extremes from a discarded timeline are not news
    this.faulted = false;
    this.limited = null;
    this.limitReason = null;
    this.eventCursor = eng.events.length; // events from building this state (replay) are not news
    this.checkpointEvery = everySteps(this.options.checkpointEveryS, eng.config.outerDt);
    this.maybeCheckpoint(true);
    this.forceShape = true;
    this.forceSnapshot = true;
    this.awaitingFrameAck = false;
  }

  // ---- commands ----

  private command(clientSeq: number, clientId: string, cmd: unknown): void {
    const e = this.eng;
    const reject = (reason: string) =>
      this.host.post({ kind: "ack", clientSeq, seq: null, status: "rejected", reason, t: e ? e.t : 0 });
    if (!e) return reject("REJ_NO_LIBRARY");
    if (typeof clientId !== "string" || validateCommand(cmd).length > 0) return reject("REJ_SCHEMA");
    if (this.faulted) return reject("REJ_FAULTED");
    if (e.halted) return reject("REJ_HALTED");
    const seq = e.submit(cmd as Record<string, any>, clientId);
    this.pendingAcks.set(seq, clientSeq);
    this.host.post({ kind: "queued", clientSeq, seq, step: e.stepIndex, t: e.t });
  }

  private rejectPending(reason: string): void {
    const t = this.eng ? this.eng.t : 0;
    for (const [seq, clientSeq] of this.pendingAcks) {
      this.host.post({ kind: "ack", clientSeq, seq, status: "rejected", reason, t });
    }
    this.pendingAcks.clear();
  }

  // ---- clock ----

  private setTime(rate: number | undefined, paused: boolean | undefined): void {
    if (rate !== undefined) {
      if (typeof rate !== "number" || !Number.isFinite(rate) || rate <= 0) {
        return this.error("time", "E_BAD_RATE", "rate must be a finite number > 0");
      }
      this.rate = rate;
    }
    if (paused === false && this.paused) {
      const e = this.eng;
      if (!e) return this.error("time", "E_NO_LIBRARY", "nothing is loaded");
      if (this.faulted) return this.error("time", "E_FAULTED", "a solver error stopped the clock; rewind to continue");
      if (e.halted) return this.error("time", "E_HALTED", `the engine halted (${e.halted}); rewind to continue`);
      this.paused = false;
      this.limited = null;
      this.limitReason = null;
      this.samples = [];
    } else if (paused === true && !this.paused) {
      this.stopClock();
      this.forceSnapshot = true;
    }
    this.anchor();
    if (!this.paused) this.scheduleTick(0);
    this.afterChange();
  }

  private anchor(): void {
    this.anchorWall = this.host.now();
    this.anchorSim = this.eng ? this.eng.t : 0;
  }

  private stopClock(): void {
    this.paused = true;
    this.tickToken++;
    this.tickScheduled = false;
  }

  private scheduleTick(delayMs: number): void {
    if (this.tickScheduled) return;
    this.tickScheduled = true;
    const token = this.tickToken;
    this.host.schedule(() => {
      if (token !== this.tickToken) return;
      this.tickScheduled = false;
      this.tick();
    }, delayMs);
  }

  private targetSim(wall: number): number {
    return this.anchorSim + (this.rate * (wall - this.anchorWall)) / 1000;
  }

  private tick(): void {
    const e = this.eng;
    if (!e || this.paused) return;
    const dt = e.config.outerDt;
    const start = this.host.now();
    let target = this.targetSim(start);
    const lag = this.options.lagLimitS;
    if (target - e.t > this.rate * lag) {
      // Behind: never skip physics. Re-anchor so the sim runs slower instead of racing later.
      this.anchorWall = start - lag * 1000;
      this.anchorSim = e.t;
      target = e.t + this.rate * lag;
      this.lastCpuLimitWall = start;
    }
    let n = 0;
    while ((e.stepIndex + 1) * dt <= target * (1 + 1e-12) && (n === 0 || this.host.now() - start < this.options.sliceMs)) {
      if (!this.stepOnce()) break;
      n++;
    }
    const now = this.host.now();
    this.samples.push([now, e.t]);
    while (this.samples.length > 2 && now - this.samples[1]![0] >= 1000) this.samples.shift();
    this.afterChange();
    if (!this.paused) {
      const due = (e.stepIndex + 1) * dt;
      const wait = ((due - this.targetSim(now)) / this.rate) * 1000;
      this.scheduleTick(Math.min(Math.max(0, wait), 250));
    }
  }

  /** One engine step with fault, halt and checkpoint handling. False when the clock had to stop. */
  private stepOnce(): boolean {
    const e = this.eng!;
    try {
      e.step();
    } catch (err) {
      this.faulted = true;
      this.pauseFor("solver", String(err));
      this.host.post({ kind: "fault", message: String(err) });
      return false;
    }
    this.maybeCheckpoint(false);
    this.trackExtremes(e);
    if (e.halted) {
      this.pauseFor("halted", e.halted);
      return false;
    }
    return true;
  }

  /** Update each instrument's extremes since the last snapshot (amendment 1 of the M5 design). */
  private trackExtremes(e: Engine): void {
    const t = e.t;
    for (const [id, v] of Object.entries(e.indicated)) {
      if (v === null || !Number.isFinite(v)) continue;
      const x = this.extremes[id];
      if (!x) this.extremes[id] = { min: v, tMin: t, max: v, tMax: t };
      else {
        if (v < x.min) {
          x.min = v;
          x.tMin = t;
        }
        if (v > x.max) {
          x.max = v;
          x.tMax = t;
        }
      }
    }
  }

  private pauseFor(limit: ClockLimit, reason: string): void {
    this.stopClock();
    this.limited = limit;
    this.limitReason = reason;
    this.forceSnapshot = true;
  }

  private stepN(n: number): void {
    const e = this.eng;
    if (!e) return this.error("step", "E_NO_LIBRARY", "nothing is loaded");
    if (!this.paused) return this.error("step", "E_RUNNING", "step only while paused");
    if (!Number.isInteger(n) || n < 1) return this.error("step", "E_BAD_ARGUMENT", "n must be an integer >= 1");
    if (this.faulted) return this.error("step", "E_FAULTED", "a solver error stopped the clock; rewind to continue");
    if (e.halted) return this.error("step", "E_HALTED", `the engine halted (${e.halted}); rewind to continue`);
    for (let i = 0; i < n; i++) {
      if (!this.stepOnce()) break;
    }
    this.forceSnapshot = true;
    this.afterChange();
  }

  private achievedRate(): number {
    if (this.paused || this.samples.length < 2) return 0;
    const [w0, s0] = this.samples[0]!;
    const [w1, s1] = this.samples[this.samples.length - 1]!;
    return w1 > w0 ? ((s1 - s0) / (w1 - w0)) * 1000 : 0;
  }

  // ---- history ----

  private maybeCheckpoint(always: boolean): void {
    if (checkpointInto(this.history, this.eng!, this.checkpointEvery, always)) this.historyDirty = true;
  }

  private rewind(step: number): void {
    const e = this.eng;
    const lib = this.lib;
    if (!e || !lib) return this.error("rewind", "E_NO_LIBRARY", "nothing is loaded");
    if (!Number.isInteger(step) || step < 0 || step > e.stepIndex) {
      return this.error("rewind", "E_BAD_ARGUMENT", `step must be an integer in [0, ${e.stepIndex}]`);
    }
    this.stopClock();
    const previous = sessionFile(e);
    const log = e.commandLog;
    // Build the new state first; the store and engine change only if the replay succeeds.
    const store = this.history.copy();
    store.dropAfter(step);
    let ne: Engine;
    try {
      const cp = store.atOrBefore(step, log);
      if (!cp) return this.error("rewind", "E_NO_CHECKPOINT", `no checkpoint at or before step ${step}`);
      ne = Engine.restore(lib, cp);
      replayCommands(ne, log, step, (x) => checkpointInto(store, x, this.checkpointEvery, false));
    } catch (err) {
      return this.error("rewind", "E_REPLAY", String(err));
    }
    if (step < e.stepIndex) this.rejectPending("REJ_REWOUND");
    this.history = store;
    this.install(ne);
    this.historyDirty = true;
    this.host.post({ kind: "rewound", step: ne.stepIndex, t: ne.t, previous });
    this.afterChange();
  }

  private exportSession(): void {
    const e = this.eng;
    if (!e) return this.error("session.export", "E_NO_LIBRARY", "nothing is loaded");
    this.host.post({ kind: "session", file: sessionFile(e) });
  }

  private importSession(file: SessionFile): void {
    const e = this.eng;
    const lib = this.lib;
    if (!e || !lib) return this.error("session.import", "E_NO_LIBRARY", "nothing is loaded");
    // Build the new state first; nothing changes unless the whole replay succeeds.
    const store = new CheckpointStore(this.options.maxCheckpoints);
    let ne: Engine;
    try {
      const f = checkSessionFile(file, lib);
      const s = f.session;
      ne = new Engine(lib, s.init, s.seed, s.pins.config);
      const every = everySteps(this.options.checkpointEveryS, ne.config.outerDt);
      checkpointInto(store, ne, every, true);
      replayCommands(ne, s.commands, f.endStep, (x) => checkpointInto(store, x, every, false));
    } catch (err) {
      return this.error("session.import", "E_SESSION", String(err));
    }
    this.stopClock();
    const previous = sessionFile(e);
    this.rejectPending("REJ_SESSION_REPLACED");
    this.history = store;
    this.install(ne);
    this.historyDirty = true;
    this.host.post({ kind: "rewound", step: ne.stepIndex, t: ne.t, previous });
    this.afterChange();
  }

  // ---- output ----

  /** Send what changed: events and acks (always), then snapshot, clock and history as their rules allow. */
  private afterChange(): void {
    this.flushEvents();
    this.maybeSnapshot();
    this.maybeClock();
    if (this.historyDirty) {
      this.historyDirty = false;
      this.host.post({ kind: "history", checkpointSteps: this.history.steps(), thinned: this.history.thinned });
    }
  }

  private flushEvents(): void {
    const e = this.eng;
    if (!e || this.eventCursor >= e.events.length) return;
    const batch = e.events.slice(this.eventCursor);
    this.eventCursor = e.events.length;
    this.host.post({ kind: "events", events: batch });
    for (const ev of batch) {
      if (ev.type !== "command") continue;
      const clientSeq = this.pendingAcks.get(ev.seq);
      if (clientSeq === undefined) continue;
      this.pendingAcks.delete(ev.seq);
      this.host.post({ kind: "ack", clientSeq, seq: ev.seq, status: ev.status, reason: ev.reason, t: ev.t });
    }
  }

  private frameAck(): void {
    this.awaitingFrameAck = false;
    this.maybeSnapshot();
  }

  private maybeSnapshot(): void {
    const e = this.eng;
    if (!e) return;
    const changed = this.forceSnapshot || e.stepIndex !== this.lastSnapStep;
    if (!changed || this.awaitingFrameAck) return;
    const now = this.host.now();
    if (!this.forceSnapshot && !this.paused && now - this.lastSnapWall < 1000 / this.options.snapshotHz) return;
    const snapshot = e.snapshot(false);
    let shape: Float32Array | undefined;
    if (this.shapeDue(snapshot)) {
      shape = Float32Array.from(e.shape());
      this.forceShape = false;
      this.lastShapeTfuel = snapshot.truth.fuelTemp;
      this.lastShapeRods = {};
      for (const [rid, r] of Object.entries<any>(snapshot.truth.rods)) this.lastShapeRods[rid] = r.position;
    }
    this.forceSnapshot = false;
    this.lastSnapStep = e.stepIndex;
    this.lastSnapWall = now;
    this.awaitingFrameAck = true;
    const extremes = this.extremes;
    this.extremes = {};
    if (shape) this.host.post({ kind: "snapshot", snapshot, shape, extremes }, [shape.buffer]);
    else this.host.post({ kind: "snapshot", snapshot, extremes });
  }

  private shapeDue(snapshot: Record<string, any>): boolean {
    if (this.forceShape) return true;
    if (Math.abs(snapshot.truth.fuelTemp - this.lastShapeTfuel) > this.options.shapeTempTol) return true;
    for (const [rid, r] of Object.entries<any>(snapshot.truth.rods)) {
      const before = this.lastShapeRods[rid];
      if (before === undefined || Math.abs(r.position - before) > this.options.shapeRodTol) return true;
    }
    return false;
  }

  private maybeClock(): void {
    const e = this.eng;
    const now = this.host.now();
    let limited = this.limited;
    if (!this.paused && now - this.lastCpuLimitWall < 1000) limited = "cpu";
    const key = `${this.rate}|${this.paused}|${limited}|${this.limitReason}`;
    if (key === this.lastClockKey && (this.paused || now - this.lastClockPost < this.options.clockReportMs)) return;
    this.lastClockKey = key;
    this.lastClockPost = now;
    this.host.post({
      kind: "clock",
      rate: this.rate,
      achievedRate: this.achievedRate(),
      paused: this.paused,
      limited,
      reason: this.limitReason,
      t: e ? e.t : 0,
      step: e ? e.stepIndex : 0,
    });
  }
}
