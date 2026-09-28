/**
 * SharedWorker entry point (docs/m6-instructor-design.md, D2a): one Runtime for every window of a session.
 * Each window is a port with its own id. A window sends `attach` with its role first, and the runtime enforces the role.
 * The worker lives while any window is open, so no window owns the session.
 * Start it with `new SharedWorker(new URL("./runtime/shared-worker.ts", import.meta.url), { type: "module", name })`,
 * where the name picks the session.
 */

import { workerClock } from "./host";
import type { ToWorker } from "./protocol";
import { MAIN_PORT, Runtime } from "./runtime";

interface SharedScope {
  onconnect: ((ev: MessageEvent) => void) | null;
}

const scope = globalThis as unknown as SharedScope;
const ports = new Map<string, MessagePort>();

const runtime = new Runtime({
  ...workerClock(),
  post: (msg, transfer, to) => {
    if (to !== undefined) ports.get(to)?.postMessage(msg, transfer ?? []);
    else for (const port of ports.values()) port.postMessage(msg); // messages to all windows carry no transfers
  },
});
runtime.disconnect(MAIN_PORT); // a shared worker has only the windows that connect

let next = 0;
scope.onconnect = (ev: MessageEvent) => {
  const port = ev.ports[0]!;
  const id = `w${++next}`;
  ports.set(id, port);
  runtime.connect(id);
  port.onmessage = (m: MessageEvent<ToWorker>) => {
    runtime.receive(m.data, id);
    if (m.data.kind === "detach") ports.delete(id);
  };
  port.start();
};
