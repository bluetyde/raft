import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { JevCopilot, JEV_URL } from "./copilot";

class FakeSocket {
  static all: FakeSocket[] = [];
  static OPEN = 1;
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  constructor(public url: string) { FakeSocket.all.push(this); }
  send(d: string) { this.sent.push(d); }
  close() { this.readyState = 3; }
  open() { this.readyState = 1; this.onopen?.(); }
  reply(o: unknown) { this.onmessage?.({ data: JSON.stringify(o) }); }
}

function fakeClient() {
  const calls: string[] = [];
  const responses: any[] = [];
  const listeners = new Map<string, (m: any) => void>();
  return {
    calls, responses, listeners,
    on: (k: string, fn: (m: any) => void) => (listeners.set(k, fn), () => listeners.delete(k)),
    supervisorEnable: () => calls.push("enable"),
    supervisorDisable: () => calls.push("disable"),
    decisionResponse: (r: any) => responses.push(r),
    command: () => Promise.resolve({}),
    endScenario: () => {},
  } as any;
}

beforeEach(() => { FakeSocket.all = []; (globalThis as any).WebSocket = FakeSocket; });
afterEach(() => { delete (globalThis as any).WebSocket; });

describe("JevCopilot relay", () => {
  it("connects to the server's /jev route", () => {
    new JevCopilot(fakeClient(), "operator").toggle();
    expect(FakeSocket.all[0]!.url).toBe(JEV_URL);
    expect(JEV_URL.endsWith("/jev")).toBe(true);
  });

  it("enables supervision only after the socket opens, and sends the first request", () => {
    const c = fakeClient();
    const cop = new JevCopilot(c, "operator");
    cop.toggle();
    expect(c.calls).toEqual([]);
    FakeSocket.all[0]!.open();
    expect(c.calls).toEqual(["enable"]);
    c.listeners.get("decision_request")!({ request: { requestId: "r1" } });
    expect(JSON.parse(FakeSocket.all[0]!.sent[0]!).requestId).toBe("r1");
  });

  it("forwards ok, shadow and error envelopes", () => {
    const c = fakeClient();
    new JevCopilot(c, "operator").toggle();
    const ws = FakeSocket.all[0]!;
    ws.open();
    for (const status of ["ok", "shadow", "error"]) ws.reply({ requestId: status, status });
    expect(c.responses.map((r: any) => r.status)).toEqual(["ok", "shadow", "error"]);
  });

  it("a remote close disables supervision", () => {
    const c = fakeClient();
    new JevCopilot(c, "operator").toggle();
    const ws = FakeSocket.all[0]!;
    ws.open();
    ws.onclose!();
    expect(c.calls).toEqual(["enable", "disable"]);
  });

  it("an old socket closing does not tear down a new connection", () => {
    const c = fakeClient();
    const cop = new JevCopilot(c, "operator");
    cop.toggle();
    const old = FakeSocket.all[0]!;
    old.open();
    const oldClose = old.onclose;
    cop.toggle(); // off
    cop.toggle(); // on again
    FakeSocket.all[1]!.open();
    oldClose!();
    expect(cop.isOn).toBe(true);
  });

  it("the instructor never touches operator supervision and ignores mismatched replies", () => {
    const c = fakeClient();
    const cop = new JevCopilot(c, "instructor");
    cop.toggle();
    const ws = FakeSocket.all[0]!;
    ws.open();
    expect(c.calls).toEqual([]);
    c.listeners.get("snapshot")!({ snapshot: { t: 1, truth: { power: 1 } } });
    const req = JSON.parse(ws.sent[0]!);
    expect(req.role).toBe("instructor");
    ws.reply({ requestId: "wrong", observationStep: 0, status: "ok", candidateId: "end" });
    expect(c.responses).toEqual([]);
  });
});
