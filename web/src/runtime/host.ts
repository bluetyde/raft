/**
 * The wall clock and timer that the real workers give the runtime (worker.ts and shared-worker.ts).
 */

import type { RuntimeHost } from "./runtime";

/** `now` and `schedule` for a worker. A MessageChannel yields to pending messages without setTimeout's minimum delay. */
export function workerClock(): Pick<RuntimeHost, "now" | "schedule"> {
  const channel = new MessageChannel();
  const queue: (() => void)[] = [];
  channel.port1.onmessage = () => queue.shift()?.();
  return {
    now: () => performance.now(),
    schedule: (fn, delayMs) => {
      if (delayMs <= 0) {
        queue.push(fn);
        channel.port2.postMessage(null);
      } else {
        setTimeout(fn, delayMs);
      }
    },
  };
}
