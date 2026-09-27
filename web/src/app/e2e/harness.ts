/**
 * Browser end-to-end harness (TODO Next #8). It runs the real runtime worker and exposes a small
 * API on `window.e2e` that Playwright drives with page.evaluate (web/e2e/runtime.spec.ts).
 * Test-only: the page is built only when VR_E2E=1 (web/vite.config.ts).
 */

import { RuntimeClient, type Ack } from "../../runtime/client";
import type { FromWorker, SessionFile } from "../../runtime/protocol";

const FILES = import.meta.glob("../../../../schema/vectors/synthetic-core/**/*", {
  query: "?url",
  import: "default",
  eager: true,
}) as Record<string, string>;

const ROOT = "../../../../schema/vectors/synthetic-core/";

async function syntheticFiles(): Promise<Record<string, ArrayBuffer>> {
  const out: Record<string, ArrayBuffer> = {};
  for (const [path, url] of Object.entries(FILES)) {
    out[path.slice(ROOT.length)] = await (await fetch(url)).arrayBuffer();
  }
  return out;
}

/** Break a copy of the library on purpose. */
function corrupt(files: Record<string, ArrayBuffer>, how: "json" | "digest"): void {
  if (how === "json") {
    files["manifest.json"] = new TextEncoder().encode("{ not json").buffer as ArrayBuffer;
  } else {
    const name = Object.keys(files).find((k) => k.startsWith("arrays/"))!;
    const bytes = new Uint8Array(files[name]!.slice(0));
    bytes[0] = bytes[0]! ^ 0xff;
    files[name] = bytes.buffer;
  }
}

interface Recorder {
  client: RuntimeClient;
  worker: Worker;
  events: Record<string, any>[];
  acks: Ack[];
  snapshot: Record<string, any> | null;
  snapshots: number;
  clock: Extract<FromWorker, { kind: "clock" }> | null;
  errors: string[];
}

const runs: Recorder[] = [];

function run(id: number): Recorder {
  const r = runs[id];
  if (!r) throw new Error(`no run ${id}`);
  return r;
}

const api = {
  /** Start a worker, load the synthetic core (optionally broken), and return the run id and the load result. */
  async start(
    opts: { init?: Record<string, any>; seed?: number; config?: Record<string, any>; corrupt?: "json" | "digest"; pauseOnTrip?: boolean } = {},
  ) {
    const worker = new Worker(new URL("../../runtime/worker.ts", import.meta.url), { type: "module" });
    const client = new RuntimeClient(worker, "e2e");
    const r: Recorder = { client, worker, events: [], acks: [], snapshot: null, snapshots: 0, clock: null, errors: [] };
    client.on("events", (m) => {
      r.events.push(...m.events);
      // pause from inside the page as soon as a trip arrives: polling from the test runner can lag by a second under load
      if (opts.pauseOnTrip && m.events.some((e: any) => e.type === "trip")) client.setTime({ paused: true });
    });
    client.on("ack", (m) => r.acks.push(m));
    client.on("snapshot", (m) => {
      r.snapshot = m.snapshot;
      r.snapshots++;
    });
    client.on("clock", (m) => (r.clock = m));
    client.on("error", (m) => r.errors.push(`${m.request}: ${m.code}`));
    client.on("fault", (m) => r.errors.push(`fault: ${m.message}`));
    const id = runs.push(r) - 1;
    const { corrupt: how, pauseOnTrip: _p, ...load } = opts;
    const files = await syntheticFiles();
    if (how) corrupt(files, how);
    try {
      const info = await client.load({ kind: "files", files }, load);
      return { id, loaded: info, issues: null };
    } catch (err: any) {
      return { id, loaded: null, issues: (err.issues ?? []).map((i: any) => i.code) as string[] };
    }
  },
  command(id: number, cmd: Record<string, unknown>): Promise<Ack> {
    return run(id).client.command(cmd);
  },
  /** Send a command and return at once (for commands that wait for time to move). */
  send(id: number, cmd: Record<string, unknown>): void {
    void run(id).client.command(cmd);
  },
  time(id: number, t: { rate?: number; paused?: boolean }): void {
    run(id).client.setTime(t);
  },
  step(id: number, n: number): void {
    run(id).client.step(n);
  },
  state(id: number) {
    const r = run(id);
    return { events: r.events, acks: r.acks, snapshot: r.snapshot, snapshots: r.snapshots, clock: r.clock, errors: r.errors };
  },
  exportSession(id: number): Promise<SessionFile> {
    return run(id).client.exportSession();
  },
  async importSession(id: number, file: SessionFile) {
    const m = await run(id).client.importSession(file);
    return { step: m.step, t: m.t };
  },
  async rewind(id: number, step: number) {
    const m = await run(id).client.rewind(step);
    return { step: m.step, t: m.t, previousEnd: m.previous.endStep };
  },
  stop(id: number): void {
    run(id).worker.terminate();
  },
};

(window as unknown as { e2e: typeof api }).e2e = api;
document.getElementById("status")!.textContent = "ready";
