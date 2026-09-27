import { describe, expect, it } from "vitest";
import { LoadError, RuntimeClient, type WorkerLike } from "./client";
import type { FromWorker } from "./protocol";
import { fetchReader, filesReader } from "./readers";
import { Runtime } from "./runtime";
import { FakeHost, invalidDir, readFolder, syntheticCoreDir } from "./test-helpers";

/** A client and a runtime joined in memory. Messages are cloned and delivered asynchronously, like postMessage. */
function pair() {
  const host = new FakeHost();
  const rt = new Runtime(host);
  const worker: WorkerLike = {
    onmessage: null,
    onerror: null,
    postMessage(msg) {
      rt.receive(structuredClone(msg));
    },
  };
  host.post = (msg: FromWorker) => {
    host.out.push(msg);
    const copy = structuredClone(msg);
    queueMicrotask(() => worker.onmessage?.({ data: copy } as MessageEvent));
  };
  const client = new RuntimeClient(worker, "operator");
  const settle = async () => {
    for (let i = 0; i < 5; i++) {
      await rt.idle();
      await new Promise((r) => setTimeout(r, 0));
    }
  };
  const load = () => client.load({ kind: "files", files: readFolder(syntheticCoreDir) });
  return { host, rt, worker, client, settle, load };
}

// Compile-time check: a real DOM Worker must fit WorkerLike (tsc fails here if it stops fitting).
const workerFits: (w: Worker) => WorkerLike = (w) => w;
void workerFits;

describe("RuntimeClient", () => {
  it("load resolves with the pins, or rejects with the validator's issues", async () => {
    const p = pair();
    const info = await p.load();
    expect(info.libraryId).toBe("synthetic-core");
    expect(info.outerDt).toBe(0.01);
    const q = pair();
    const err = await q.client.load({ kind: "files", files: readFolder(invalidDir("bad-json")) }).catch((e) => e);
    expect(err).toBeInstanceOf(LoadError);
    expect((err as LoadError).issues.map((i) => i.code)).toContain("E_JSON");
  });

  it("a command resolves with the engine's result after the step that applied it", async () => {
    const p = pair();
    await p.load();
    const queued: number[] = [];
    let done = false;
    const ack = p.client.command({ type: "rod.move", rod: "safety", direction: "in" }, (q) => queued.push(q.seq));
    void ack.then(() => (done = true));
    await p.settle();
    expect(queued).toEqual([1]);
    expect(done).toBe(false); // paused: queued, not yet applied (D2: a)
    p.client.step(1);
    expect(await ack).toMatchObject({ seq: 1, status: "accepted", reason: null });
    expect(p.rt.engine!.commandLog[0].clientId).toBe("operator");
  });

  it("acknowledges each snapshot, so the worker sends the next one", async () => {
    const p = pair();
    const seen: number[] = [];
    p.client.on("snapshot", (m) => seen.push(m.snapshot.t));
    await p.load();
    await p.settle();
    p.client.step(3);
    await p.settle();
    p.client.step(2);
    await p.settle();
    expect(seen.map((t) => Math.round(t * 100))).toEqual([0, 3, 5]);
  });

  it("an error for another request does not answer a rewind", async () => {
    const p = pair();
    await p.load();
    p.client.step(10);
    p.client.setTime({ rate: -1 }); // answered by an error for "time"
    const r = await p.client.rewind(4);
    expect(r.step).toBe(4);
    await expect(p.client.rewind(99)).rejects.toThrow(/E_BAD_ARGUMENT/);
  });

  it("session export and import round-trip through the client", async () => {
    const p = pair();
    await p.load();
    const ack = p.client.command({ type: "rod.move", rod: "transient", direction: "out" });
    p.client.step(30);
    expect((await ack).status).toBe("accepted");
    const file = await p.client.exportSession();
    expect(file.endStep).toBe(30);
    const q = pair();
    await q.load();
    const r = await q.client.importSession(file);
    expect(r.step).toBe(30);
    expect(q.rt.engine!.commandLog).toHaveLength(1);
  });

  it("a worker error marks the client disconnected and emits a fault", async () => {
    const p = pair();
    const faults: string[] = [];
    p.client.on("fault", (m) => faults.push(m.message));
    p.worker.onerror?.(new Event("error"));
    expect(p.client.disconnected).toBe(true);
    expect(faults).toHaveLength(1);
    expect(() => p.client.step(1)).toThrow(/stopped/);
  });
});

describe("readers", () => {
  it("fetchReader joins paths to the base URL and reads a missing file as null", async () => {
    const asked: string[] = [];
    const reader = fetchReader("https://example.test/lib", async (url) => {
      asked.push(url);
      return url.endsWith("manifest.json")
        ? { ok: true, arrayBuffer: async () => new TextEncoder().encode("{}").buffer as ArrayBuffer }
        : { ok: false, arrayBuffer: async () => new ArrayBuffer(0) };
    });
    expect(new TextDecoder().decode((await reader.read("manifest.json"))!)).toBe("{}");
    expect(await reader.read("arrays/x.f32")).toBeNull();
    expect(asked).toEqual(["https://example.test/lib/manifest.json", "https://example.test/lib/arrays/x.f32"]);
  });

  it("filesReader looks keys up as own properties only", async () => {
    const reader = filesReader({ "manifest.json": new Uint8Array([1, 2]).buffer });
    expect(Array.from((await reader.read("manifest.json"))!)).toEqual([1, 2]);
    expect(await reader.read("constructor")).toBeNull();
    expect(await reader.read("toString")).toBeNull();
  });
});
