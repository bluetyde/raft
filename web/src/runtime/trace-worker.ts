/**
 * A short-lived worker that writes the CSV trace of a session (docs/m6-instructor-design.md, D6a).
 * It runs beside the main runtime worker, so the running session does not stop.
 */

import { loadLibrary } from "../sim/library";
import { checkSessionFile } from "./history";
import type { SessionFile } from "./protocol";
import { readerFor } from "./readers";
import { traceCsv } from "./trace";

export interface TraceRequest {
  files: Record<string, ArrayBuffer>;
  file: SessionFile;
  everyS: number;
}

export type TraceReply = { ok: true; csv: string; rows: number } | { ok: false; message: string };

const scope = self as unknown as { onmessage: ((ev: MessageEvent) => void) | null; postMessage(msg: TraceReply): void };

scope.onmessage = async (ev: MessageEvent) => {
  const req = ev.data as TraceRequest;
  try {
    const lib = await loadLibrary(readerFor({ kind: "files", files: req.files }));
    const csv = traceCsv(lib, checkSessionFile(req.file, lib), req.everyS);
    scope.postMessage({ ok: true, csv, rows: csv.split("\n").length - 2 });
  } catch (err) {
    scope.postMessage({ ok: false, message: String(err) });
  }
};
