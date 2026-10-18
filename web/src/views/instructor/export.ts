/**
 * Export from the instructor view (docs/m6-instructor-design.md, D6): session files and CSV traces.
 * The CSV comes from a replay in a separate short-lived worker, so the running session does not stop.
 */

import type { SessionFile } from "../../runtime/protocol";
import type { TraceReply, TraceRequest } from "../../runtime/trace-worker";

/** Replay `file` in a new worker and return its CSV trace. The worker stops when it answers. */
export const TRACE_TIMEOUT_MS = 10 * 60_000;

export function traceInWorker(files: Record<string, ArrayBuffer>, file: SessionFile, everyS = 0.1, timeoutMs = TRACE_TIMEOUT_MS): Promise<TraceReply> {
  const worker = new Worker(new URL("../../runtime/trace-worker.ts", import.meta.url), { type: "module" });
  return new Promise((resolve) => {
    // a worker that never answers must not leave the button spinning for ever
    const timer = setTimeout(() => {
      worker.terminate();
      resolve({ ok: false, message: `the trace worker did not answer within ${Math.round(timeoutMs / 1000)} s` });
    }, timeoutMs);
    worker.onmessage = (ev: MessageEvent) => {
      clearTimeout(timer);
      worker.terminate();
      resolve(ev.data as TraceReply);
    };
    worker.onerror = (ev) => {
      clearTimeout(timer);
      worker.terminate();
      resolve({ ok: false, message: String((ev as ErrorEvent).message ?? "the trace worker stopped") });
    };
    const req: TraceRequest = { files, file, everyS };
    worker.postMessage(req, Object.values(files));
  });
}

/** Give the browser a file to save. */
export function download(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** A file name part from a sim time: "t0120.50s". */
export function timeTag(t: number): string {
  return `t${t.toFixed(2).padStart(7, "0")}s`;
}
