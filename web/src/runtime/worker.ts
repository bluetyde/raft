/**
 * Web Worker entry point: one Runtime per worker, with one window (port "main", role "full").
 * Start it from the main thread with `new Worker(new URL("./runtime/worker.ts", import.meta.url), { type: "module" })`.
 */

import { workerClock } from "./host";
import type { ToWorker } from "./protocol";
import { Runtime } from "./runtime";

interface WorkerScope {
  postMessage(msg: unknown, transfer: Transferable[]): void;
  onmessage: ((ev: MessageEvent<ToWorker>) => void) | null;
}

const scope = globalThis as unknown as WorkerScope;

const runtime = new Runtime({
  ...workerClock(),
  post: (msg, transfer) => scope.postMessage(msg, transfer ?? []),
});

scope.onmessage = (ev) => runtime.receive(ev.data);
