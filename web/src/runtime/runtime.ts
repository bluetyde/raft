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
import { buildBranch, marksBefore, marksFrom, summarize, type Branch } from "./branches";
import { CheckpointStore, checkSessionFile, replayCommands, sessionFile } from "./history";
import { prepareScript, ScriptError, type PreparedScript } from "./script";
import { GoalTracker, prepareScenario, ScenarioError, type PreparedScenario } from "./scenario";
import {
  isCoarse,
  MAX_BRANCHES,
  OPERATOR_FORBIDDEN,
  PROTOCOL_VERSION,
  ROLES,
  type LoadedInfo,
  type Role,
  type ScenarioView,
  type Annotation,
  type BranchInfo,
  type Mark,
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
  /** Send to one window (`to`, a port id), or to every window when `to` is undefined. */
  post(msg: FromWorker, transfer?: Transferable[], to?: string): void;
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
  /** How long a decision request may wait for its reply (ms of wall time) before supervision is dropped. */
  supervisorMaxWallMs: number;
  /** ... and how much simulation time may pass meanwhile (s). */
  supervisorMaxSimS: number;
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
  supervisorMaxWallMs: 2000,
  supervisorMaxSimS: 1.0,
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

import { RAISE_COOLDOWN_S, RAISE_CEILING_FRACTION, RAISE_FACTOR, RAISE_MIN_PERIOD_S, Supervisor, TARGET_FLOOR_W } from "./supervisor";
import { DeterministicPID } from "./controller";

/** True for the commands that a coarse session refuses: pulse mode and rod firing (M6 amendment 1). */
function isPulseCommand(cmd: Record<string, any>): boolean {
  return cmd["type"] === "rod.fire" || (cmd["type"] === "mode.set" && cmd["mode"] === "pulse");
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

/**
 * One connected window: a port of the shared worker, or the one window ("main") of a dedicated worker.
 * Each window has its own snapshot pacing (frame acks), power-shape state and instrument extremes.
 */
class Port {
  awaitingFrameAck = false;
  lastSnapWall = -Infinity;
  lastSnapStep = -1;
  forceSnapshot = true;
  forceShape = true;
  extremes: Record<string, Extreme> = {};
  lastShapeRods: Record<string, number> = {};
  lastShapeTfuel = NaN;
  constructor(
    readonly id: string,
    public role: Role | null,
  ) {}
}

/** The port id of a dedicated worker's one window. */
export const MAIN_PORT = "main";

export class Runtime {
  readonly options: RuntimeOptions;
  private lib: Library | null = null;
  private eng: Engine | null = null;

  private supervisor: Supervisor;
  /** Sim time of the last approved raise, for the cooldown. */
  private lastRaiseT = -Infinity;
  /** The instructor script for this session, or null. Its events are submitted as commands from "script". */
  private script: PreparedScript | null = null;
  private controller: DeterministicPID = new DeterministicPID();

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
  private pendingAcks = new Map<number, { clientSeq: number; port: string }>(); // engine seq -> who asked

  private ports = new Map<string, Port>();
  /** The window whose message is being handled: replies go there. */
  private replyTo = MAIN_PORT;

  private history: CheckpointStore;
  private checkpointEvery = 1;
  private historyDirty = false;

  // branches, marks and annotations (docs/m6-instructor-design.md, D1 and D6)
  private current: BranchInfo = { id: 1, parent: null, forkStep: 0 };
  private nextBranchId = 2;
  private branches: Branch[] = [];
  private marks: Mark[] = [];
  private annotations: Annotation[] = [];
  private nextAnnotationId = 1;
  private timelineDirty = false;

  // the scenario of this session (docs/m5-scenarios-design.md), its goal tracker, and the tracker's state at each checkpoint
  private scenario: PreparedScenario | null = null;
  private tracker: GoalTracker | null = null;
  private trackerAt = new Map<number, GoalTracker>();
  private scenarioDirty = false;
  /** The step at which the instructor ended the scenario on this timeline, or null. */
  private scenarioEndStep: number | null = null;

  private inbox: Promise<void> = Promise.resolve();

  constructor(
    private readonly host: RuntimeHost,
    options: Partial<RuntimeOptions> = {},
  ) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.history = new CheckpointStore(this.options.maxCheckpoints);
    this.supervisor = new Supervisor(() => this.host.now(), { maxWallAgeMs: this.options.supervisorMaxWallMs, maxSimAgeS: this.options.supervisorMaxSimS });
    this.ports.set(MAIN_PORT, new Port(MAIN_PORT, "full"));
  }

  /**
   * A window connects (shared worker). Its role is null until it sends `attach`.
   * A shared worker has no "main" window, so it calls `disconnect(MAIN_PORT)` first.
   */
  connect(id: string, role: Role | null = null): void {
    this.ports.set(id, new Port(id, role));
  }

  /** A window is gone: stop sending to it, and forget its pending acknowledgements. */
  disconnect(id: string): void {
    this.ports.delete(id);
    for (const [seq, p] of this.pendingAcks) if (p.port === id) this.pendingAcks.delete(seq);
  }

  /** The connected windows and their roles (for tests and the host). */
  windows(): { id: string; role: Role | null }[] {
    return [...this.ports.values()].map((p) => ({ id: p.id, role: p.role }));
  }

  /** Handle one message from window `from`. Messages are handled in arrival order; a load finishes before the next message. */
  receive(msg: ToWorker, from: string = MAIN_PORT): void {
    this.inbox = this.inbox
      .then(() => {
        this.replyTo = from;
        return this.handle(msg, from);
      })
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

  private async handle(msg: ToWorker, from: string): Promise<void> {
    const port = this.ports.get(from);
    if (!port) return; // a window that already detached
    if (msg.kind === "attach") return this.attach(port, msg.role);
    if (msg.kind === "detach") return this.disconnect(from);
    if (msg.kind === "frameAck") return this.frameAck(port);
    if (port.role === null) return this.error(msg.kind, "E_NOT_ATTACHED", "send attach (with a role) first");
    // amendment 3: the worker, not the view, decides what an operator window may send
    if (port.role === "operator" && OPERATOR_FORBIDDEN.includes(msg.kind)) {
      return this.error(msg.kind, "E_ROLE", `an operator window cannot send ${msg.kind}`);
    }
    switch (msg.kind) {
      case "load":
        return this.load(msg.source, msg.init, msg.seed, msg.config, msg.scenario);
      case "command":
        return this.command(msg.clientSeq, msg.clientId, msg.cmd, port.role);
      case "time":
        return this.setTime(msg.rate, msg.paused);
      case "step":
        return this.stepN(msg.n);
      case "rewind":
        return this.rewind(msg.step);
      case "session.export":
        return this.exportSession();
      case "session.import":
        return this.importSession(msg.file, msg.scenario);
      case "annotate":
        return this.annotate(msg.text, msg.step);
      case "annotation.delete":
        return this.deleteAnnotation(msg.id);
      case "decision_response":
        // only the window that turned supervision on may answer
        if (from !== this.supervisor.ownerPort) return;
        return this.handleDecisionResponse(msg.response);
      case "branch.switch":
        return this.switchBranch(msg.id);
      case "scenario.end":
        return this.endScenario();
      case "script.load":
        return this.loadScript(msg.script);
      case "supervisor.enable": {
        this.supervisor.enableTracking(from);
        // Turning supervision on is the operator's explicit approval to hold the power as it is now.
        const power = this.eng?.snapshot(false).indicated?.["log"] ?? this.eng?.snapshot(false).truth?.power ?? 0;
        if (this.supervisor.ownerPort === from && !this.controller.enabled && power > TARGET_FLOOR_W) this.controller.enable(power);
        return;
      }
      case "supervisor.disable":
        if (this.supervisor.ownerPort === null || from === this.supervisor.ownerPort) this.stopSupervision();
        return;
      default:
        this.error((msg as { kind: string }).kind as ToWorker["kind"], "E_UNKNOWN_MESSAGE", "unknown message kind");
    }
  }

  /**
   * The next higher target the runtime would approve, or null. A raise needs an armed controller, a known
   * power-high trip to stay well under, a settled period, room on the regulating rod and time since the last raise.
   */
  private raiseTarget(): number | null {
    const e = this.eng;
    const target = this.controller.target;
    if (!e || !this.controller.enabled || target === null) return null;
    const tripValue = (e.lib.trips as any[]).find((x) => x.id === "power-high")?.predicate?.value;
    if (typeof tripValue !== "number") return null; // no trip to stay under: fail closed
    const next = target * RAISE_FACTOR;
    if (next > tripValue * RAISE_CEILING_FRACTION) return null;
    if (e.t - this.lastRaiseT < RAISE_COOLDOWN_S) return null;
    const truth = e.snapshot(false).truth;
    const period = truth?.period;
    if (typeof period === "number" && period > 0 && period < RAISE_MIN_PERIOD_S) return null;
    if ((truth?.rods?.["regulating"]?.position ?? 1) >= 0.99) return null;
    return next;
  }

  /** True when a manual SCRAM should be a choice: a short positive period, or power near the power-high setpoint. */
  private scramOffered(period: number, power: number, tripValue: unknown): boolean {
    if (typeof period === "number" && period > 0 && period < 10) return true;
    return typeof tripValue === "number" && power >= tripValue * RAISE_CEILING_FRACTION;
  }

  private handleDecisionResponse(response: import("./protocol").DecisionResponse): void {
    const candidate = this.supervisor.resolveDecision(response);
    if (!candidate) return; // Invalid, ignored, or error

    if (candidate.intent === "HOLD_TARGET") {
      // Keep the approved target and its history. A reply never arms or moves the target.
    } else if (candidate.intent === "RAISE_TARGET") {
      // Checked again now: the reply may be a moment old. The AI never picks a number; it only says yes to this one.
      const allowed = this.raiseTarget();
      if (allowed !== null && candidate.targetValue !== undefined && candidate.targetValue <= allowed * (1 + 1e-9) &&
          this.controller.target !== null && candidate.targetValue > this.controller.target) {
        this.controller.setTarget(candidate.targetValue);
        this.lastRaiseT = this.eng!.t;
      }
    } else if (candidate.intent === "REDUCE_TARGET") {
      // Track a lower validated target; there is no raw rod insertion.
      if (this.controller.enabled && this.controller.target !== null && candidate.targetValue !== undefined &&
          candidate.targetValue < this.controller.target && candidate.targetValue >= TARGET_FLOOR_W) {
        this.controller.setTarget(candidate.targetValue);
      }
    } else if (candidate.intent === "REQUEST_SCRAM") {
      this.controller.disable();
      this.eng!.submit({ type: "scram" }, "supervisor");
    } else if (candidate.intent === "STOP_MOTION") {
      this.controller.disable();
      // every rod the library has that is moving; the engine refuses to stop a rod that is scramming
      const rods = this.eng!.snapshot(false).truth?.rods ?? {};
      for (const [rid, r] of Object.entries<any>(rods)) {
        if (r.moving) this.eng!.submit({ type: "rod.move", rod: rid, direction: "stop" }, "supervisor");
      }
    }
  }

  private error(request: import("./protocol").ToWorker["kind"], code: string, message: string): void {
    this.reply({ kind: "error", request, code, message });
  }

  /** Send to the window whose message is being handled. */
  private reply(msg: FromWorker, transfer?: Transferable[]): void {
    this.host.post(msg, transfer, this.replyTo);
  }

  private attach(port: Port, role: Role): void {
    if (!ROLES.includes(role)) return this.error("attach", "E_BAD_ARGUMENT", `role must be one of ${ROLES.join(", ")}`);
    port.role = role;
    this.reply({ kind: "attached", role, loaded: this.loadedInfo() });
    // a new window needs the current state now, not at the next change
    if (this.eng) {
      port.forceSnapshot = true;
      port.forceShape = true;
      port.awaitingFrameAck = false;
      this.host.post(this.clockMessage(), undefined, port.id);
      this.host.post({ kind: "history", checkpointSteps: this.history.steps(), thinned: this.history.thinned }, undefined, port.id);
      this.host.post(this.timelineMessage(), undefined, port.id);
      this.host.post(this.scenarioMessage(), undefined, port.id);
      this.maybeSnapshot();
    }
  }

  private loadedInfo(): LoadedInfo | null {
    const e = this.eng;
    const lib = this.lib;
    if (!e || !lib) return null;
    return { libraryId: lib.manifest.id, digest: lib.digest, pins: e.pins(), outerDt: e.config.outerDt };
  }

  private forEachPort(fn: (p: Port) => void): void {
    for (const p of this.ports.values()) fn(p);
  }

  // ---- loading ----

  private async load(
    source: LibrarySource,
    init: Record<string, any> | undefined,
    seed: number | undefined,
    config: Record<string, any> | undefined,
    scenarioFile: unknown,
  ): Promise<void> {
    this.stopClock();
    // A failed load keeps the previous library and engine, paused; the clock message says so.
    const fail = (issues: Issue[]) => {
      this.reply({ kind: "loadFailed", protocol: PROTOCOL_VERSION, issues });
      this.afterChange();
    };
    let lib: Library;
    try {
      lib = await loadLibrary(cachingReader(readerFor(source, this.host.fetch)));
    } catch (err) {
      if (err instanceof LibraryError) return fail(err.issues);
      return fail([{ code: "E_READ", path: "", message: String(err) }]);
    }
    let prepared: PreparedScenario | null = null;
    if (scenarioFile !== undefined) {
      // the scenario sets the start state, seed and outer step
      try {
        prepared = await prepareScenario(scenarioFile, lib);
      } catch (err) {
        if (err instanceof ScenarioError) return fail(err.issues);
        return fail([{ code: "E_SCN_FIELD", path: "", message: String(err) }]);
      }
      init = prepared.init;
      seed = prepared.seed;
      config = { outerDt: prepared.outerDt };
    }
    let eng: Engine;
    try {
      eng = new Engine(lib, init, seed ?? 1, config);
    } catch (err) {
      if (err instanceof InitError) return fail([{ code: err.code, path: "init", message: err.message }]);
      return fail([{ code: "E_INIT_INVALID", path: "init", message: String(err) }]);
    }
    if (isCoarse(eng.config.outerDt) && eng.mode === "pulse") {
      return fail([{ code: "E_COARSE_PULSE", path: "init.mode", message: `pulse mode needs an outer step of 10 ms or less (this one is ${eng.config.outerDt} s)` }]);
    }
    this.rejectPending("REJ_SESSION_REPLACED");
    this.lib = lib;
    this.history.clear();
    this.rate = 1; // a new session starts at 1x, paused (as a new worker did before the shared worker)
    this.scenario = prepared;
    this.script = null;
    this.scenarioEndStep = null;
    this.tracker = prepared ? new GoalTracker(prepared.goals) : null;
    this.tracker?.evaluate(eng);
    this.trackerAt = new Map();
    this.scenarioDirty = true;
    this.install(eng);
    this.branches = [];
    this.current = { id: 1, parent: null, forkStep: 0 };
    this.nextBranchId = 2;
    this.marks = [];
    this.annotations = [];
    this.nextAnnotationId = 1;
    this.timelineDirty = true;
    this.submitDueEvents();
    // every window hears of a new session, so an attached window can rebuild its panels
    this.host.post({ kind: "loaded", protocol: PROTOCOL_VERSION, ...this.loadedInfo()! });
    this.host.post(this.scriptMessage());
    this.afterChange();
  }

  /** Make `eng` the current engine, after a load, rewind or import. The clock stays paused. */
  private install(eng: Engine): void {
    this.eng = eng;

    this.lastRaiseT = -Infinity;
    this.supervisor.temporalEpoch++;
    this.supervisor.disable();
    this.controller.disable();

    this.faulted = false;
    this.limited = null;
    this.limitReason = null;
    this.eventCursor = eng.events.length; // events from building this state (replay) are not news
    this.checkpointEvery = everySteps(this.options.checkpointEveryS, eng.config.outerDt);
    this.maybeCheckpoint(true);
    if (this.tracker) this.trackerAt.set(eng.stepIndex, this.tracker.clone());
    this.forEachPort((p) => {
      p.extremes = {}; // extremes from a discarded timeline are not news
      p.forceShape = true;
      p.forceSnapshot = true;
      p.awaitingFrameAck = false;
    });
  }

  // ---- commands ----

  private command(clientSeq: number, clientId: string, cmd: unknown, role: Role | null): void {
    const e = this.eng;
    const reject = (reason: string) => this.reply({ kind: "ack", clientSeq, seq: null, status: "rejected", reason, t: e ? e.t : 0 });
    if (!e) return reject("REJ_NO_LIBRARY");
    if (typeof clientId !== "string" || validateCommand(cmd).length > 0) return reject("REJ_SCHEMA");
    const type = String((cmd as Record<string, unknown>)["type"]);
    if (role === "operator" && type.startsWith("fault.")) return reject("REJ_ROLE");
    if (clientId === "scenario" || clientId === "script") return reject("REJ_ROLE"); // reserved for scripted events
    // D4a: a scenario limits the operator's controls (the instructor is not limited)
    const fromOperator = role === "operator" || clientId !== "instructor";
    if (this.scenario && fromOperator && !this.scenario.file.controls.allow.includes(type)) return reject("REJ_SCENARIO");
    if (this.faulted) return reject("REJ_FAULTED");
    if (e.halted) return reject("REJ_HALTED");
    // Checked here, before the engine, so the rejected command is not in the log and replays stay the same.
    if (isCoarse(e.config.outerDt) && isPulseCommand(cmd as Record<string, any>)) return reject("REJ_COARSE_STEP");
    // amendment 3: a scripted event due at this boundary gets its seq before any operator command at the boundary
    this.submitDueEvents();
    const seq = e.submit(cmd as Record<string, any>, clientId);
    this.pendingAcks.set(seq, { clientSeq, port: this.replyTo });
    this.reply({ kind: "queued", clientSeq, seq, step: e.stepIndex, t: e.t });
  }

  private rejectPending(reason: string): void {
    const t = this.eng ? this.eng.t : 0;
    for (const [seq, p] of this.pendingAcks) {
      this.host.post({ kind: "ack", clientSeq: p.clientSeq, seq, status: "rejected", reason, t }, undefined, p.port);
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
      this.forEachPort((p) => (p.forceSnapshot = true));
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
    
    // Check Supervisor Deadlines
    if (this.supervisor.checkDeadlines(e.t)) {
      this.stopSupervision();
      this.pauseFor("solver", "Loss of AI supervision (timeout)"); // Suspend simulation
      return false; // Clock stops
    }

    // Execute Deterministic Controller at outer-step boundaries (which stepOnce() represents)
    if (this.controller.enabled) {
      const state = e.snapshot(false);
      const power = state.indicated?.["log"] ?? state.truth?.power ?? 0;
      const isSaturated = false; // We can check this if we need to, but the PID calculates on next line.
      // Wait, we need to know isSaturated. Let's get rod position.
      const rodPos = state.truth?.rods?.["regulating"]?.position ?? 1;
      const directionReq = this.controller.lastOutput > 0 ? "out" : "in";
      const sat = (directionReq === "out" && rodPos >= 0.99) || (directionReq === "in" && rodPos <= 0.01);
      
      const cmd = this.controller.calculate(power, e.config.outerDt, sat);
      
      // Submit only on a change. At a rod limit the engine ends the motion itself, so "in" at the bottom
      // (or "out" at the top) is not re-sent every step.
      const currentMoving = state.truth?.rods?.["regulating"]?.moving ?? "stop";
      const atLimit = (cmd === "out" && rodPos >= 0.99) || (cmd === "in" && rodPos <= 0.01);
      if (currentMoving !== cmd && !(atLimit && currentMoving === "stop")) {
        e.submit({ type: "rod.move", rod: "regulating", direction: cmd }, "supervisor");
      }
    }

    try {
      e.step();
    } catch (err) {
      this.faulted = true;
      this.pauseFor("solver", String(err));
      this.host.post({ kind: "fault", message: String(err) });
      return false;
    }
    const added = this.maybeCheckpoint(false);
    this.trackExtremes(e);
    if (this.tracker) {
      if (this.tracker.evaluate(e)) this.scenarioDirty = true;
      if (added) this.trackerAt.set(e.stepIndex, this.tracker.clone());
    }
    if (e.halted) {
      this.pauseFor("halted", e.halted);
      return false;
    }
    this.submitDueEvents();
    return true;
  }

  /**
   * Submit the scenario's scripted events that are due at the current boundary (D2a), as commands from "scenario".
   * The log holds them, so the count of "scenario" entries is the cursor: after a rewind or a switch, the events
   * after the new step are submitted again when their boundary is reached.
   */
  private submitDueEvents(): void {
    this.submitDueScript();
    const sc = this.scenario;
    const e = this.eng;
    if (!sc || !e || e.halted) return;
    let n = e.commandLog.filter((c: any) => c.clientId === "scenario").length;
    while (n < sc.events.length && sc.events[n]!.step <= e.stepIndex) {
      e.submit(sc.events[n]!.cmd, "scenario");
      n++;
    }
  }

  /** The same for the instructor script, as commands from "script". */
  private submitDueScript(): void {
    const sc = this.script;
    const e = this.eng;
    if (!sc || !e || e.halted) return;
    let n = e.commandLog.filter((c: any) => c.clientId === "script").length;
    while (n < sc.events.length && sc.events[n]!.step <= e.stepIndex) {
      e.submit(sc.events[n]!.cmd, "script");
      n++;
    }
  }

  private scriptMessage(): Extract<FromWorker, { kind: "script" }> {
    const sc = this.script;
    return { kind: "script", script: sc ? { name: sc.name, events: sc.events.map((x) => ({ step: x.step, t: x.t, note: x.note })) } : null };
  }

  private loadScript(raw: unknown | null): void {
    const e = this.eng;
    if (!e || !this.lib) return this.error("script.load", "E_NO_LIBRARY", "nothing is loaded");
    if (raw === null) {
      this.script = null;
      this.reply(this.scriptMessage());
      return;
    }
    // commands from an earlier script are in the log; a second script would break the cursor that counts them
    if (e.commandLog.some((c: any) => c.clientId === "script")) {
      return this.error("script.load", "E_SCRIPT_ACTIVE", "a script has already run in this timeline; rewind before it, or load the library again");
    }
    let prepared: PreparedScript;
    try {
      prepared = prepareScript(raw, this.lib, e.config.outerDt);
    } catch (err) {
      if (err instanceof ScriptError) return this.error("script.load", err.issues[0]!.code, err.message);
      throw err;
    }
    const past = prepared.events.find((x) => x.step < e.stepIndex);
    if (past) return this.error("script.load", "E_SCRIPT_PAST", `an event is due at ${past.t} s, before the current time ${e.t} s`);
    this.script = prepared;
    this.submitDueScript();
    this.host.post(this.scriptMessage());
    this.afterChange();
  }

  /** The after-step callback for a replay: the checkpoint rule, then the goal tracker (and its state at each new checkpoint). */
  private replayHook(tracker: GoalTracker | null, trackerAt: Map<number, GoalTracker>): (st: CheckpointStore, x: Engine) => void {
    const endStep = this.scenarioEndStep;
    return (st, x) => {
      const added = checkpointInto(st, x, this.checkpointEvery, false);
      if (tracker) {
        tracker.evaluate(x);
        if (endStep !== null && x.stepIndex === endStep) tracker.endAt(x.t); // the end is not in the command log
        if (added) trackerAt.set(x.stepIndex, tracker.clone());
      }
    };
  }

  private trackerMapUpTo(step: number): Map<number, GoalTracker> {
    return new Map([...this.trackerAt].filter(([k]) => k <= step));
  }

  /** Update each instrument's extremes since the last snapshot (amendment 1 of the M5 design). */
  private trackExtremes(e: Engine): void {
    for (const p of this.ports.values()) this.extremesInto(p.extremes, e);
  }

  private extremesInto(extremes: Record<string, Extreme>, e: Engine): void {
    const t = e.t;
    for (const [id, v] of Object.entries(e.indicated)) {
      if (v === null || !Number.isFinite(v)) continue;
      const x = extremes[id];
      if (!x) extremes[id] = { min: v, tMin: t, max: v, tMax: t };
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

  /** Supervision off: forget the request, disarm the controller and stop the rod it may be moving. */
  private stopSupervision(): void {
    this.supervisor.disable();
    if (this.controller.enabled && this.eng) {
      this.eng.submit({ type: "rod.move", rod: "regulating", direction: "stop" }, "supervisor");
    }
    this.controller.disable();
  }

  private pauseFor(limit: ClockLimit, reason: string): void {
    this.stopClock();
    this.limited = limit;
    this.limitReason = reason;
    this.forEachPort((p) => (p.forceSnapshot = true));
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
    this.forEachPort((p) => (p.forceSnapshot = true));
    this.afterChange();
  }

  private achievedRate(): number {
    if (this.paused || this.samples.length < 2) return 0;
    const [w0, s0] = this.samples[0]!;
    const [w1, s1] = this.samples[this.samples.length - 1]!;
    return w1 > w0 ? ((s1 - s0) / (w1 - w0)) * 1000 : 0;
  }

  // ---- history ----

  private maybeCheckpoint(always: boolean): boolean {
    const added = checkpointInto(this.history, this.eng!, this.checkpointEvery, always);
    if (added) this.historyDirty = true;
    return added;
  }

  private rewind(step: number): void {
    const e = this.eng;
    const lib = this.lib;
    if (!e || !lib) return this.error("rewind", "E_NO_LIBRARY", "nothing is loaded");
    if (!Number.isInteger(step) || step < 0 || step > e.stepIndex) {
      return this.error("rewind", "E_BAD_ARGUMENT", `step must be an integer in [0, ${e.stepIndex}]`);
    }
    this.stopClock();
    const previous = this.fileOf(e);
    const log = e.commandLog;
    // Build the new state first; the store and engine change only if the replay succeeds.
    const store = this.history.copy();
    store.dropAfter(step);
    let ne: Engine;
    let tracker: GoalTracker | null = null;
    let trackerAt = new Map<number, GoalTracker>();
    try {
      const cp = store.atOrBefore(step, log);
      if (!cp) return this.error("rewind", "E_NO_CHECKPOINT", `no checkpoint at or before step ${step}`);
      if (this.scenario) {
        const at = this.trackerAt.get(cp.stepIndex);
        if (!at) return this.error("rewind", "E_REPLAY", `no goal state at checkpoint ${cp.stepIndex}`);
        tracker = at.clone();
        trackerAt = this.trackerMapUpTo(cp.stepIndex);
      }
      ne = Engine.restore(lib, cp);
      const hook = this.replayHook(tracker, trackerAt);
      replayCommands(ne, log, step, (x) => hook(store, x));
    } catch (err) {
      return this.error("rewind", "E_REPLAY", String(err));
    }
    if (step < e.stepIndex) {
      this.rejectPending("REJ_REWOUND");
      // the discarded future is kept as a branch (D1a); the new timeline forks from it at `step`
      this.saveBranch(e, previous);
      this.current = { id: this.nextBranchId++, parent: this.current.id, forkStep: step };
      this.marks = marksBefore(this.marks, ne.t, ne.config.outerDt);
      this.annotations = this.annotations.filter((a) => a.step <= step);
      this.timelineDirty = true;
    }
    this.history = store;
    if (this.scenario) {
      this.tracker = tracker;
      this.trackerAt = trackerAt;
      if (this.scenarioEndStep !== null && step < this.scenarioEndStep) this.scenarioEndStep = null; // the end is undone
      this.scenarioDirty = true;
    }
    this.install(ne);
    this.submitDueEvents();
    this.historyDirty = true;
    this.host.post({ kind: "rewound", step: ne.stepIndex, t: ne.t, previous });
    this.afterChange();
  }

  private exportSession(): void {
    const e = this.eng;
    if (!e) return this.error("session.export", "E_NO_LIBRARY", "nothing is loaded");
    this.reply({ kind: "session", file: this.fileOf(e) });
  }

  /** The current timeline as a version 2 session file (with its annotations and branch). */
  private fileOf(e: Engine): SessionFile {
    const sc = this.scenario;
    return sessionFile(e, {
      annotations: this.annotations,
      branch: this.current,
      ...(sc ? { scenario: { id: sc.file.id, digest: sc.digest, thresholds: sc.thresholds, endStep: this.scenarioEndStep } } : {}),
    });
  }

  /** Keep the current timeline (ending in `e`) as a branch. At the limit, the oldest branch goes. */
  private saveBranch(e: Engine, file: SessionFile): void {
    this.branches.push({
      info: { ...this.current },
      file,
      marks: [...this.marks],
      summary: summarize(e, this.current, this.annotations.length),
    });
    while (this.branches.length > MAX_BRANCHES) this.branches.shift();
    this.timelineDirty = true;
  }

  private switchBranch(id: number): void {
    const e = this.eng;
    const lib = this.lib;
    if (!e || !lib) return this.error("branch.switch", "E_NO_LIBRARY", "nothing is loaded");
    const i = this.branches.findIndex((b) => b.info.id === id);
    if (i < 0) return this.error("branch.switch", "E_NO_BRANCH", `no branch ${id}`);
    const target = this.branches[i]!;
    let built: ReturnType<typeof buildBranch>;
    let tracker: GoalTracker | null = null;
    let trackerAt = new Map<number, GoalTracker>();
    const sc = this.scenario;
    try {
      const hook = (st: CheckpointStore, x: Engine) => this.replayHook(tracker, trackerAt)(st, x);
      built = buildBranch(lib, e, this.history, target.file, hook, (from, start) => {
        if (!sc) return;
        // the goals at the shared checkpoint are the same on both timelines; at step 0 they start fresh
        const at = this.trackerAt.get(from);
        tracker = at ? at.clone() : new GoalTracker(sc.goals);
        if (!at) tracker.evaluate(start);
        trackerAt = this.trackerMapUpTo(from);
        trackerAt.set(from, tracker.clone());
      });
    } catch (err) {
      return this.error("branch.switch", "E_REPLAY", String(err));
    }
    this.stopClock();
    const previous = this.fileOf(e);
    this.rejectPending("REJ_BRANCH_SWITCHED");
    this.branches.splice(i, 1);
    this.saveBranch(e, previous);
    this.current = { ...target.info };
    this.marks = [...target.marks];
    this.annotations = structuredClone(target.file.annotations ?? []);
    this.lastSwitchFrom = built.fromStep;
    this.history = built.store;
    if (sc) {
      this.tracker = tracker;
      this.trackerAt = trackerAt;
      // the end belongs to the timeline where it happened: it stays only if the shared part includes it
      if (this.scenarioEndStep !== null && this.scenarioEndStep > built.fromStep) this.scenarioEndStep = null;
      this.scenarioDirty = true;
    }
    this.install(built.engine);
    this.submitDueEvents();
    this.historyDirty = true;
    this.timelineDirty = true;
    this.host.post({ kind: "rewound", step: built.engine.stepIndex, t: built.engine.t, previous });
    this.afterChange();
  }

  /** The step the last branch switch started its replay from (0 = no shared checkpoint). For tests. */
  lastSwitchFrom = -1;

  private annotate(text: string, step: number | undefined): void {
    const e = this.eng;
    if (!e) return this.error("annotate", "E_NO_LIBRARY", "nothing is loaded");
    if (typeof text !== "string" || text.trim().length === 0 || text.length > 500) {
      return this.error("annotate", "E_BAD_ARGUMENT", "the text must have 1 to 500 characters");
    }
    const at = step ?? e.stepIndex;
    if (!Number.isInteger(at) || at < 0 || at > e.stepIndex) {
      return this.error("annotate", "E_BAD_ARGUMENT", `step must be an integer in [0, ${e.stepIndex}]`);
    }
    this.annotations.push({ id: this.nextAnnotationId++, step: at, t: at * e.config.outerDt, text: text.trim() });
    this.annotations.sort((a, b) => a.step - b.step || a.id - b.id);
    this.timelineDirty = true;
    this.afterChange();
  }

  private deleteAnnotation(id: number): void {
    const n = this.annotations.length;
    this.annotations = this.annotations.filter((a) => a.id !== id);
    if (this.annotations.length === n) return this.error("annotation.delete", "E_BAD_ARGUMENT", `no annotation ${id}`);
    this.timelineDirty = true;
    this.afterChange();
  }

  private async importSession(file: SessionFile, scenarioFile: unknown): Promise<void> {
    const e = this.eng;
    const lib = this.lib;
    if (!e || !lib) return this.error("session.import", "E_NO_LIBRARY", "nothing is loaded");
    // Build the new state first; nothing changes unless the whole replay succeeds.
    const store = new CheckpointStore(this.options.maxCheckpoints);
    let ne: Engine;
    let prepared: PreparedScenario | null = null;
    let tracker: GoalTracker | null = null;
    let endStep: number | null = null;
    const trackerAt = new Map<number, GoalTracker>();
    try {
      const f = checkSessionFile(file, lib);
      const s = f.session;
      if (f.scenario) {
        // a version 3 session runs a scenario: the same scenario file must come with it
        if (scenarioFile === undefined) throw new Error(`the session runs scenario ${f.scenario.id}; import it with that scenario`);
        prepared = await prepareScenario(scenarioFile, lib);
        if (prepared.file.id !== f.scenario.id || prepared.digest !== f.scenario.digest) {
          throw new Error(`the scenario ${prepared.file.id} does not match the session's (${f.scenario.id}, digest ${f.scenario.digest.slice(0, 12)})`);
        }
        if (prepared.outerDt !== s.pins.config.outerDt) throw new Error("the session's outer step is not the scenario's");
      }
      ne = new Engine(lib, s.init, s.seed, s.pins.config);
      if (isCoarse(ne.config.outerDt) && (ne.mode === "pulse" || s.commands.some((c: any) => isPulseCommand(c.cmd ?? {})))) {
        throw new Error("a coarse session (outer step longer than 10 ms) cannot hold pulse mode or rod firing");
      }
      const every = everySteps(this.options.checkpointEveryS, ne.config.outerDt);
      checkpointInto(store, ne, every, true);
      if (prepared) {
        tracker = new GoalTracker(prepared.goals);
        tracker.evaluate(ne);
        trackerAt.set(0, tracker.clone());
      }
      const t = tracker;
      endStep = f.scenario && "endStep" in f.scenario ? (f.scenario.endStep ?? null) : null;
      replayCommands(ne, s.commands, f.endStep, (x) => {
        const added = checkpointInto(store, x, every, false);
        if (t) {
          t.evaluate(x);
          if (endStep !== null && x.stepIndex === endStep) t.endAt(x.t);
          if (added) trackerAt.set(x.stepIndex, t.clone());
        }
      });
    } catch (err) {
      return this.error("session.import", "E_SESSION", String(err));
    }
    this.stopClock();
    const previous = this.fileOf(e);
    this.rejectPending("REJ_SESSION_REPLACED");
    // the replaced timeline is kept as a branch; the imported one starts a new tree (its ids came from another runtime)
    if (e.stepIndex > 0 || e.commandLog.length > 0) this.saveBranch(e, previous);
    this.current = { id: this.nextBranchId++, parent: null, forkStep: 0 };
    this.marks = marksFrom(ne.events, ne.commandLog);
    this.annotations = structuredClone(file.annotations ?? []);
    this.nextAnnotationId = Math.max(this.nextAnnotationId, ...this.annotations.map((a) => a.id + 1));
    this.timelineDirty = true;
    this.history = store;
    this.scenario = prepared;
    this.script = null;
    this.scenarioEndStep = endStep;
    this.tracker = tracker;
    this.trackerAt = trackerAt;
    this.scenarioDirty = true;
    this.install(ne);
    this.submitDueEvents();
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
    if (this.timelineDirty && this.eng) {
      this.timelineDirty = false;
      this.host.post(this.timelineMessage());
    }
    if (this.scenarioDirty) {
      this.scenarioDirty = false;
      this.host.post(this.scenarioMessage());
    }
  }

  private flushEvents(): void {
    const e = this.eng;
    if (!e || this.eventCursor >= e.events.length) return;
    const batch = e.events.slice(this.eventCursor);
    this.eventCursor = e.events.length;
    this.host.post({ kind: "events", events: batch });
    const marks = marksFrom(batch, e.commandLog);
    if (marks.length > 0) {
      this.marks.push(...marks);
      if (marks.some((m) => m.kind === "trip")) {
        if (this.scenario) this.scenarioDirty = true; // the score counts trips
        // Protective trips disable tracking
        this.supervisor.trip();
        this.controller.disable();
      }
    }
    // a new mark, or a command that changes the current branch's command count in the compare table
    if (marks.length > 0 || batch.some((ev) => ev.type === "command")) this.timelineDirty = true;
    for (const ev of batch) {
      if (ev.type !== "command") continue;
      const who = this.pendingAcks.get(ev.seq);
      if (who === undefined) continue;
      this.pendingAcks.delete(ev.seq);
      this.host.post({ kind: "ack", clientSeq: who.clientSeq, seq: ev.seq, status: ev.status, reason: ev.reason, t: ev.t }, undefined, who.port);
    }
  }

  private frameAck(port: Port): void {
    port.awaitingFrameAck = false;
    this.maybeSnapshot();
  }

  /** Send a snapshot to each window that is ready for one. The snapshot and the power shape are computed once. */
  private maybeSnapshot(): void {
    const e = this.eng;
    if (!e) return;
    const now = this.host.now();
    let snapshot: Record<string, any> | null = null;
    let shape: Float32Array | null = null;
    let faults: { instruments: Record<string, string>; extraRho: number } | null = null;
    for (const p of this.ports.values()) {
      if (p.role === null) continue;
      const changed = p.forceSnapshot || e.stepIndex !== p.lastSnapStep;
      if (!changed || p.awaitingFrameAck) continue;
      if (!p.forceSnapshot && !this.paused && now - p.lastSnapWall < 1000 / this.options.snapshotHz) continue;
      snapshot ??= e.snapshot(false);
      faults ??= { instruments: { ...e.faults }, extraRho: e.extraRho };
      let own: Float32Array | undefined;
      if (this.shapeDue(p, snapshot)) {
        shape ??= Float32Array.from(e.shape());
        own = Float32Array.from(shape); // each window gets its own buffer to transfer
        p.forceShape = false;
        p.lastShapeTfuel = snapshot.truth.fuelTemp;
        p.lastShapeRods = {};
        for (const [rid, r] of Object.entries<any>(snapshot.truth.rods)) p.lastShapeRods[rid] = r.position;
      }
      p.forceSnapshot = false;
      p.lastSnapStep = e.stepIndex;
      p.lastSnapWall = now;
      p.awaitingFrameAck = true;
      const extremes = p.extremes;
      p.extremes = {};
      if (own) this.host.post({ kind: "snapshot", snapshot, shape: own, extremes, faults }, [own.buffer], p.id);
      else this.host.post({ kind: "snapshot", snapshot, extremes, faults }, undefined, p.id);
    }
    
    // Also dispatch inference requests if supervisor is enabled and not waiting
    if (this.supervisor.isTracking() && !this.supervisor.pendingRequest) {
      // Avoid sending too frequently, just piggyback on snapshot pace
      snapshot ??= e.snapshot(false);
      const power = snapshot.indicated?.["log"] ?? snapshot.truth?.power ?? 0;
      const period = snapshot.truth?.period ?? 0;
      const fuelTemp = (snapshot.truth?.fuelTemp ?? 293.15) - 273.15;
      
      const rods = Object.entries<any>(snapshot.truth?.rods ?? {});
      const allIn = rods.length > 0 && rods.every(([, r]) => r.position < 0.01);
      const tripValue = (e.lib.trips as any[]).find((x) => x.id === "power-high")?.predicate?.value;
      const danger = this.scramOffered(period, power, tripValue);
      const active: string[] = snapshot.trips?.active ?? [];
      const latched: string[] = snapshot.trips?.latched ?? [];

      let phaseDesc: string;
      if (allIn && period > 100) phaseDesc = `The reactor is at source-level power, ${power.toExponential(3)} W, steady (period is effectively infinite), with all control rods fully inserted.`;
      else if (danger)          phaseDesc = `Power is ${power.toExponential(3)} W. The period is dangerously short or power is near the trip setpoint (period ${period.toFixed(1)} s).`;
      else if (period > 0 && period <= 100) phaseDesc = `Power is ${power.toExponential(3)} W and rising with a period of ${period.toFixed(1)} s.`;
      else if (period < 0)     phaseDesc = `Power is ${power.toExponential(3)} W and falling (period ${period.toFixed(1)} s).`;
      else                      phaseDesc = `Power is ${power.toExponential(3)} W and steady.`;

      const rodDesc = rods.map(([id, r]) => `${id} ${(r.position * 100).toFixed(0)}% withdrawn${r.moving ? ` (moving ${r.moving})` : ""}`).join(", ");
      const tripDesc = active.length + latched.length === 0 ? "No trips are active." : `Trips: ${[...new Set([...active, ...latched])].join(", ")}.`;
      const target = this.controller.enabled ? this.controller.target : null;
      const modeDesc = target !== null ? `The automatic controller is holding ${target.toExponential(2)} W.` : "The automatic controller is off.";

      const premise = `ROLE: Nuclear Reactor Operator. GOAL: hold power at the approved level and stay safe; a SCRAM is only for a real emergency. CURRENT STATE: ${phaseDesc} ${modeDesc} Control rods — ${rodDesc}. Fuel temperature is ${fuelTemp.toFixed(1)} °C. ${tripDesc}${danger ? "" : " There is no emergency."}`;

      const candidates = this.supervisor.dispatchObservation(e.t, this.controller.enabled ? this.controller.target : null, this.raiseTarget(), danger);
      const req: import("./protocol").DecisionRequest = {
        protocolVersion: 1,
        sessionId: "runtime-session", // We can improve this with real IDs later
        temporalEpoch: this.supervisor.temporalEpoch,
        connectionId: "conn-1",
        requestId: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(),
        observationStep: e.stepIndex,
        observationSimTimeS: e.t,
        role: "operator",
        premise,
        candidates: candidates.map(c => ({ id: c.id, text: c.text }))
      };
      
      this.supervisor.expect(req);
      this.host.post({ kind: "decision_request", request: req }, undefined, this.supervisor.ownerPort ?? undefined);
      // The wall deadline runs on its own timer, so it holds while the clock is paused too.
      this.host.schedule(() => {
        this.inbox = this.inbox.then(() => {
          if (!this.supervisor.isPending(req.requestId) || !this.supervisor.wallExpired()) return;
          this.stopSupervision();
          this.pauseFor("solver", "Loss of AI supervision (timeout)");
        });
      }, this.supervisor.maxWallAgeMs + 1);
    }
  }

  private shapeDue(p: Port, snapshot: Record<string, any>): boolean {
    if (p.forceShape) return true;
    if (Math.abs(snapshot.truth.fuelTemp - p.lastShapeTfuel) > this.options.shapeTempTol) return true;
    for (const [rid, r] of Object.entries<any>(snapshot.truth.rods)) {
      const before = p.lastShapeRods[rid];
      if (before === undefined || Math.abs(r.position - before) > this.options.shapeRodTol) return true;
    }
    return false;
  }

  private scenarioMessage(): Extract<FromWorker, { kind: "scenario" }> {
    const sc = this.scenario;
    const tr = this.tracker;
    if (!sc || !tr) return { kind: "scenario", scenario: null };
    const goals = tr.view();
    const expected = new Set(["manual", ...(sc.file.expectTrips ?? [])]);
    const trips = this.marks.filter((m) => m.kind === "trip" && !expected.has(m.label.slice("trip ".length))).length;
    const metTimes = goals.filter((g) => g.status === "met").map((g) => g.t!);
    const view: ScenarioView = {
      id: sc.file.id,
      title: sc.file.title,
      brief: sc.file.brief ?? "",
      hints: [...(sc.file.hints ?? [])],
      allow: [...sc.file.controls.allow],
      faultsVisible: sc.file.faultsVisible === true,
      outerDt: sc.outerDt,
      goals,
      events: sc.events.map((ev) => ({ step: ev.step, t: ev.step * sc.outerDt, note: ev.note })),
      score: {
        met: goals.filter((g) => g.status === "met").length,
        failed: goals.filter((g) => g.status === "failed").length,
        total: goals.length,
        trips,
        lastGoalT: metTimes.length > 0 ? Math.max(...metTimes) : null,
      },
      done: tr.done(),
      endedAt: this.scenarioEndStep !== null ? this.scenarioEndStep * sc.outerDt : null,
    };
    return { kind: "scenario", scenario: view };
  }

  private endScenario(): void {
    const e = this.eng;
    if (!e || !this.scenario || !this.tracker) return this.error("scenario.end", "E_NO_SCENARIO", "no scenario is running");
    if (this.scenarioEndStep !== null || this.tracker.done()) return; // already over
    this.scenarioEndStep = e.stepIndex;
    this.tracker.endAt(e.t);
    // the checkpoint at this step (if any) must hold the ended goals, so a rewind here keeps the end
    if (this.trackerAt.has(e.stepIndex)) this.trackerAt.set(e.stepIndex, this.tracker.clone());
    this.scenarioDirty = true;
    this.afterChange();
  }

  /** The running scenario, for tests. */
  get scenarioState(): { prepared: PreparedScenario; goals: ReturnType<GoalTracker["view"]> } | null {
    return this.scenario && this.tracker ? { prepared: this.scenario, goals: this.tracker.view() } : null;
  }

  private timelineMessage(): Extract<FromWorker, { kind: "timeline" }> {
    return {
      kind: "timeline",
      current: summarize(this.eng!, this.current, this.annotations.length),
      branches: this.branches.map((b) => b.summary),
      marks: [...this.marks],
      annotations: structuredClone(this.annotations),
    };
  }

  private maybeClock(): void {
    const e = this.eng;
    const now = this.host.now();
    let limited = this.limited;
    if (!this.paused && now - this.lastCpuLimitWall < 1000) limited = "cpu";
    // while paused, the step changes only by a step, rewind, switch or import, and the clock message must name the new step
    const key = `${this.rate}|${this.paused}|${limited}|${this.limitReason}${this.paused && e ? `|${e.stepIndex}` : ""}`;
    if (key === this.lastClockKey && (this.paused || now - this.lastClockPost < this.options.clockReportMs)) return;
    this.lastClockKey = key;
    this.lastClockPost = now;
    this.host.post(this.clockMessage(limited));
  }

  private clockMessage(limited: ClockLimit = this.limited): Extract<FromWorker, { kind: "clock" }> {
    const e = this.eng;
    return {
      kind: "clock",
      rate: this.rate,
      achievedRate: this.achievedRate(),
      paused: this.paused,
      limited,
      reason: this.limitReason,
      t: e ? e.t : 0,
      step: e ? e.stepIndex : 0,
    };
  }
}
