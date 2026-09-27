/**
 * Web Worker entry point: one Runtime per worker. Start it from the main thread with
 * `new Worker(new URL("./runtime/worker.ts", import.meta.url), { type: "module" })`.
 */

import type { ToWorker } from "./protocol";
import { Runtime } from "./runtime";

interface WorkerScope {
  postMessage(msg: unknown, transfer: Transferable[]): void;
  onmessage: ((ev: MessageEvent<ToWorker>) => void) | null;
}

const scope = globalThis as unknown as WorkerScope;

// A MessageChannel yields to pending messages without setTimeout's minimum delay.
const channel = new MessageChannel();
const queue: (() => void)[] = [];
channel.port1.onmessage = () => queue.shift()?.();

const runtime = new Runtime({
  now: () => performance.now(),
  schedule: (fn, delayMs) => {
    if (delayMs <= 0) {
      queue.push(fn);
      channel.port2.postMessage(null);
    } else {
      setTimeout(fn, delayMs);
    }
  },
  post: (msg, transfer) => scope.postMessage(msg, transfer ?? []),
});

scope.onmessage = (ev) => runtime.receive(ev.data);
