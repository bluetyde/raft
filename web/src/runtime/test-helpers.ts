/**
 * Test helpers for the runtime: a fake host with a controllable wall clock, and library folders
 * read into the `files` form of a load message. Node only (tests); not bundled.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import type { FromWorker, ToWorker } from "./protocol";
import { Runtime, type RuntimeHost, type RuntimeOptions } from "./runtime";
import { repoRoot } from "../sim/testing";

export const syntheticCoreDir = join(repoRoot, "schema", "vectors", "synthetic-core");
export const invalidDir = (name: string) => join(repoRoot, "schema", "vectors", "invalid", name);

/** Every file under `dir`, keyed by its forward-slash path relative to `dir`. */
export function readFolder(dir: string): Record<string, ArrayBuffer> {
  const files: Record<string, ArrayBuffer> = {};
  const walk = (d: string) => {
    for (const name of readdirSync(d)) {
      const p = join(d, name);
      if (statSync(p).isDirectory()) walk(p);
      else {
        const buf = readFileSync(p);
        files[relative(dir, p).split(sep).join("/")] = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
      }
    }
  };
  walk(dir);
  return files;
}

/** A host whose wall clock moves only when the test says so. Posted messages are cloned, like postMessage. */
export class FakeHost implements RuntimeHost {
  t = 0;
  out: FromWorker[] = [];
  private timers: { at: number; order: number; fn: () => void }[] = [];
  private order = 0;

  now(): number {
    return this.t;
  }

  schedule(fn: () => void, delayMs: number): void {
    this.timers.push({ at: this.t + Math.max(0, delayMs), order: this.order++, fn });
  }

  /** Each posted message with the window it went to (undefined = every window). */
  sent: { msg: FromWorker; to: string | undefined }[] = [];
  /** Captured transfers with each post. */
  transfers: { msg: FromWorker; transfer: Transferable[] | undefined; to: string | undefined }[] = [];

  post(msg: FromWorker, transfer?: Transferable[], to?: string): void {
    const copy = structuredClone(msg);
    this.out.push(copy);
    this.sent.push({ msg: copy, to });
    this.transfers.push({ msg: copy, transfer, to });
  }

  /** Drain accumulated message buffers so long sessions do not grow memory in the test host. */
  drain(): FromWorker[] {
    const copy = [...this.out];
    this.out = [];
    this.sent = [];
    this.transfers = [];
    return copy;
  }

  /** The messages window `port` received (sent to it, or to every window), optionally of one kind. */
  seenBy<K extends FromWorker["kind"]>(port: string, kind?: K): Extract<FromWorker, { kind: K }>[] {
    return this.sent
      .filter((x) => (x.to === undefined || x.to === port) && (kind === undefined || x.msg.kind === kind))
      .map((x) => x.msg) as Extract<FromWorker, { kind: K }>[];
  }

  /** Run timers in time order until `ms` of wall time have passed. */
  advance(ms: number): void {
    const end = this.t + ms;
    for (;;) {
      this.timers.sort((a, b) => a.at - b.at || a.order - b.order);
      const next = this.timers[0];
      if (!next || next.at > end) break;
      this.timers.shift();
      this.t = Math.max(this.t, next.at);
      next.fn();
    }
    this.t = end;
  }

  /** Messages of one kind, in order. */
  of<K extends FromWorker["kind"]>(kind: K): Extract<FromWorker, { kind: K }>[] {
    return this.out.filter((m) => m.kind === kind) as Extract<FromWorker, { kind: K }>[];
  }

  last<K extends FromWorker["kind"]>(kind: K): Extract<FromWorker, { kind: K }> | undefined {
    return this.of(kind).at(-1);
  }
}

/** A runtime on a fake host, with the synthetic core loaded (paused at step 0). */
export async function loadedRuntime(
  opts: Partial<RuntimeOptions> = {},
  load: Partial<Extract<ToWorker, { kind: "load" }>> = {},
): Promise<{ host: FakeHost; rt: Runtime }> {
  const host = new FakeHost();
  const rt = new Runtime(host, opts);
  rt.receive({ kind: "load", protocol: 1, source: { kind: "files", files: readFolder(syntheticCoreDir) }, ...load });
  await rt.idle();
  if (!rt.engine) throw new Error(`load failed: ${JSON.stringify(host.last("loadFailed"))}`);
  return { host, rt };
}

/** Send a message and wait until the runtime handled it. */
export async function send(rt: Runtime, msg: ToWorker): Promise<void> {
  rt.receive(msg);
  await rt.idle();
}
