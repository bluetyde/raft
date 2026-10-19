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
// The same for a SharedWorker's port (M6 slice S3).
const portFits: (p: MessagePort) => WorkerLike = (p) => p;
void portFits;

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

  it("a load is completed by its own reply, not by another window's loaded broadcast", async () => {
    const p = pair();
    let done = false;
    const pending = p.load().then((i) => ((done = true), i));
    // another window's load answered first: same kind, other request id
    p.worker.onmessage?.({ data: { kind: "loaded", protocol: 1, reqId: "someone-else", libraryId: "other", digest: "x", pins: {}, outerDt: 0.5 } } as MessageEvent);
    await p.settle();
    const info = await pending;
    expect(info.libraryId).toBe("synthetic-core");
    expect(info.outerDt).toBe(0.01);
    expect(done).toBe(true);
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

  it("a worker error rejects the requests still waiting, and later requests reject instead of throwing", async () => {
    const p = pair();
    await p.load();
    const waiting = p.client.exportSession();
    const cmd = p.client.command({ type: "noop" });
    p.worker.onerror?.(new Event("error"));
    await expect(waiting).rejects.toThrow(/stopped/);
    await expect(cmd).rejects.toThrow(/stopped/);
    await expect(p.client.exportSession()).rejects.toThrow(/stopped/);
    await expect(p.client.command({ type: "noop" })).rejects.toThrow(/stopped/);
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
        : { ok: false, status: 404, arrayBuffer: async () => new ArrayBuffer(0) };
    });
    expect(new TextDecoder().decode((await reader.read("manifest.json"))!)).toBe("{}");
    expect(await reader.read("arrays/x.f32")).toBeNull();
    expect(asked).toEqual(["https://example.test/lib/manifest.json", "https://example.test/lib/arrays/x.f32"]);
  });

  it("fetchReader reads a 404 or 410 as missing and any other failure as an error that names the URL", async () => {
    const answer = (status: number) =>
      fetchReader("https://example.test/lib", async () => ({ ok: false, status, arrayBuffer: async () => new ArrayBuffer(0) }));
    expect(await answer(404).read("a")).toBeNull();
    expect(await answer(410).read("a")).toBeNull();
    for (const status of [403, 429, 500, 503]) {
      await expect(answer(status).read("a")).rejects.toThrow(`https://example.test/lib/a: HTTP ${status}`);
    }
  });

  it("filesReader looks keys up as own properties only", async () => {
    const reader = filesReader({ "manifest.json": new Uint8Array([1, 2]).buffer });
    expect(Array.from((await reader.read("manifest.json"))!)).toEqual([1, 2]);
    expect(await reader.read("constructor")).toBeNull();
    expect(await reader.read("toString")).toBeNull();
  });
});

describe("RuntimeClient frame acks", () => {
  it("runs every listener and asks for the next snapshot, even when one listener throws", () => {
    const sent: unknown[] = [];
    const worker: WorkerLike = { onmessage: null, onerror: null, postMessage: (msg) => sent.push(msg) };
    const client = new RuntimeClient(worker);
    let later = 0;
    client.on("snapshot", () => {
      throw new Error("view bug");
    });
    client.on("snapshot", () => later++);
    const deliver = () => worker.onmessage!({ data: { kind: "snapshot", snapshot: { t: 0 } } } as MessageEvent);
    expect(deliver).toThrow("view bug");
    expect(sent).toEqual([{ kind: "frameAck" }]);
    expect(later).toBe(1); // the other views still get the message
  });
});

describe("RuntimeClient requests answered by broadcasts", () => {
  it("another window's rewound broadcast does not complete this window's request", async () => {
    const sent: any[] = [];
    const worker: WorkerLike = { onmessage: null, onerror: null, postMessage: (msg) => sent.push(msg) };
    const client = new RuntimeClient(worker);
    const deliver = (msg: object) => worker.onmessage!({ data: msg } as MessageEvent);
    let outcome = "pending";
    client.switchBranch(999).then(() => (outcome = "resolved"), () => (outcome = "rejected"));
    const mine = sent[0].reqId as string;
    expect(typeof mine).toBe("string");
    deliver({ kind: "rewound", step: 5, t: 0.05, previous: {}, reqId: "other-1" }); // window A's rewind
    deliver({ kind: "rewound", step: 6, t: 0.06, previous: {} }); // no id at all
    await Promise.resolve();
    expect(outcome).toBe("pending");
    deliver({ kind: "error", request: "branch.switch", code: "E_NO_BRANCH", message: "no such branch" });
    await new Promise((r) => setTimeout(r, 0));
    expect(outcome).toBe("rejected");
    // and the asker's own reply still completes it
    let ok = false;
    client.rewind(3).then(() => (ok = true));
    deliver({ kind: "rewound", step: 3, t: 0.03, previous: {}, reqId: sent[1].reqId });
    await new Promise((r) => setTimeout(r, 0));
    expect(ok).toBe(true);
    expect(sent[1].reqId).not.toBe(mine);
  });
});
