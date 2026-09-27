/**
 * Main-thread side of the runtime: typed requests, a promise per command, and subscriptions.
 * It acknowledges each snapshot after the snapshot listeners ran, so the worker sends the next one.
 */

import {
  PROTOCOL_VERSION,
  type FromWorker,
  type LibrarySource,
  type LoadedInfo,
  type SessionFile,
  type ToWorker,
} from "./protocol";
import type { Issue } from "../library/validate";

/** What the client needs from a Worker (a real one, or an in-memory pair in tests). */
export interface WorkerLike {
  postMessage(msg: ToWorker, transfer?: Transferable[]): void;
  onmessage: ((ev: { data: FromWorker }) => void) | null;
  onerror?: ((ev: unknown) => void) | null;
}

export type Ack = Extract<FromWorker, { kind: "ack" }>;
export type Queued = Extract<FromWorker, { kind: "queued" }>;
type Kind = FromWorker["kind"];
type Msg<K extends Kind> = Extract<FromWorker, { kind: K }>;

export class LoadError extends Error {
  constructor(readonly issues: Issue[]) {
    super(issues.slice(0, 5).map((i) => `${i.code} ${i.path}`).join("; "));
    this.name = "LoadError";
  }
}

export class RuntimeClient {
  private nextClientSeq = 1;
  private acks = new Map<number, { resolve: (a: Ack) => void; onQueued?: (q: Queued) => void }>();
  private listeners = new Map<Kind, Set<(msg: any) => void>>();
  private waiters: { kinds: Kind[]; request: ToWorker["kind"]; resolve: (msg: FromWorker) => void }[] = [];
  /** True after the worker failed. Views disable their controls and say so. */
  disconnected = false;

  constructor(
    private readonly worker: WorkerLike,
    readonly clientId = "local",
  ) {
    worker.onmessage = (ev) => this.dispatch(ev.data);
    worker.onerror = () => {
      this.disconnected = true;
      this.emit({ kind: "fault", message: "the runtime worker stopped" });
    };
  }

  on<K extends Kind>(kind: K, fn: (msg: Msg<K>) => void): () => void {
    let set = this.listeners.get(kind);
    if (!set) this.listeners.set(kind, (set = new Set()));
    set.add(fn);
    return () => set.delete(fn);
  }

  /** Load a library. Resolves with its pins, or rejects with LoadError and the validator's issues. */
  load(
    source: LibrarySource,
    opts: { init?: Record<string, any>; seed?: number; config?: Record<string, any> } = {},
  ): Promise<LoadedInfo> {
    const transfer = source.kind === "files" ? Object.values(source.files) : [];
    const done = this.next(["loaded", "loadFailed", "error"], "load");
    this.send({ kind: "load", protocol: PROTOCOL_VERSION, source, ...opts }, transfer);
    return done.then((m) => {
      if (m.kind === "loadFailed") throw new LoadError(m.issues);
      if (m.kind === "error") throw new Error(`${m.code}: ${m.message}`);
      const { kind: _k, protocol: _p, ...info } = m as Msg<"loaded">;
      return info;
    });
  }

  /** Send an engine command. Resolves with the engine's result, after the step that applied it. */
  command(cmd: Record<string, unknown>, onQueued?: (q: Queued) => void): Promise<Ack> {
    const clientSeq = this.nextClientSeq++;
    const p = new Promise<Ack>((resolve) => this.acks.set(clientSeq, { resolve, onQueued }));
    this.send({ kind: "command", clientSeq, clientId: this.clientId, cmd });
    return p;
  }

  setTime(t: { rate?: number; paused?: boolean }): void {
    this.send({ kind: "time", ...t });
  }

  step(n = 1): void {
    this.send({ kind: "step", n });
  }

  rewind(step: number): Promise<Msg<"rewound">> {
    const done = this.next(["rewound", "error"], "rewind");
    this.send({ kind: "rewind", step });
    return done.then((m) => this.orThrow(m, "rewound"));
  }

  exportSession(): Promise<SessionFile> {
    const done = this.next(["session", "error"], "session.export");
    this.send({ kind: "session.export" });
    return done.then((m) => this.orThrow(m, "session").file);
  }

  importSession(file: SessionFile): Promise<Msg<"rewound">> {
    const done = this.next(["rewound", "error"], "session.import");
    this.send({ kind: "session.import", file });
    return done.then((m) => this.orThrow(m, "rewound"));
  }

  private orThrow<K extends Kind>(m: FromWorker, kind: K): Msg<K> {
    if (m.kind === "error") throw new Error(`${m.code}: ${m.message}`);
    if (m.kind !== kind) throw new Error(`expected ${kind}, got ${m.kind}`);
    return m as Msg<K>;
  }

  private send(msg: ToWorker, transfer: Transferable[] = []): void {
    if (this.disconnected) throw new Error("the runtime worker stopped");
    this.worker.postMessage(msg, transfer);
  }

  /**
   * The answer to a request: the next message of one of `kinds`, where an `error` must name `request`.
   * Requests of one kind are answered in order, because the worker handles messages in order.
   */
  private next(kinds: Kind[], request: ToWorker["kind"]): Promise<FromWorker> {
    return new Promise((resolve) => this.waiters.push({ kinds, request, resolve }));
  }

  private matches(w: { kinds: Kind[]; request: ToWorker["kind"] }, msg: FromWorker): boolean {
    if (!w.kinds.includes(msg.kind)) return false;
    return msg.kind !== "error" || msg.request === w.request;
  }

  private dispatch(msg: FromWorker): void {
    if (msg.kind === "queued") this.acks.get(msg.clientSeq)?.onQueued?.(msg);
    if (msg.kind === "ack") {
      const a = this.acks.get(msg.clientSeq);
      this.acks.delete(msg.clientSeq);
      a?.resolve(msg);
    }
    const i = this.waiters.findIndex((w) => this.matches(w, msg));
    if (i >= 0) this.waiters.splice(i, 1)[0]!.resolve(msg);
    this.emit(msg);
    if (msg.kind === "snapshot") this.worker.postMessage({ kind: "frameAck" });
  }

  private emit(msg: FromWorker): void {
    for (const fn of this.listeners.get(msg.kind) ?? []) fn(msg);
  }
}
