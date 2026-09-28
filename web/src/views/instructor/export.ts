/**
 * Export from the instructor view (docs/m6-instructor-design.md, D6): session files and CSV traces.
 * The CSV comes from a replay in a separate short-lived worker, so the running session does not stop.
 */

import type { SessionFile } from "../../runtime/protocol";
import type { TraceReply, TraceRequest } from "../../runtime/trace-worker";

/** Replay `file` in a new worker and return its CSV trace. The worker stops when it answers. */
export function traceInWorker(files: Record<string, ArrayBuffer>, file: SessionFile, everyS = 0.1): Promise<TraceReply> {
  const worker = new Worker(new URL("../../runtime/trace-worker.ts", import.meta.url), { type: "module" });
  return new Promise((resolve) => {
    worker.onmessage = (ev: MessageEvent) => {
      worker.terminate();
      resolve(ev.data as TraceReply);
    };
    worker.onerror = (ev) => {
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
