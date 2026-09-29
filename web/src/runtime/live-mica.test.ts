/**
 * Live run against a real jev-server (Mica or DeBERTa) on the TRIGA library, in real time.
 * Skipped unless JEV_LIVE is set. Start the server first (python jev-server/server.py), then:
 *   JEV_LIVE=1 npx vitest run src/runtime/live-mica.test.ts
 * Set JEV_SECONDS (wall seconds, default 40) and JEV_RATE (sim speed, default 5). The report goes to stdout.
 */
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { repoRoot } from "../sim/testing";
import type { DecisionRequest, DecisionResponse, FromWorker } from "./protocol";
import { Runtime, type RuntimeHost } from "./runtime";
import { readFolder } from "./test-helpers";

const LIVE = !!process.env["JEV_LIVE"];
const SECONDS = Number(process.env["JEV_SECONDS"] ?? 40);
const RATE = Number(process.env["JEV_RATE"] ?? 5);
const URL = process.env["JEV_URL"] ?? "ws://localhost:8000/jev";
/** Deadline for a reply (ms). Default 2000; a CPU-only Mica needs about 5000 and a slow sim rate. */
const WALL_MS = Number(process.env["JEV_WALL_MS"] ?? 2000);

class RealHost implements RuntimeHost {
  out: FromWorker[] = [];
  onRequest: (r: DecisionRequest) => void = () => {};
  now(): number {
    return performance.now();
  }
  schedule(fn: () => void, delayMs: number): void {
    setTimeout(fn, Math.max(0, delayMs));
  }
  post(msg: FromWorker): void {
    if (msg.kind === "decision_request") this.onRequest(msg.request);
    else this.out.push(structuredClone(msg));
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe.skipIf(!LIVE)("live jev-server on TRIGA", () => {
  it("runs supervised in real time and reports latency, choices and power", async () => {
    const ws = new WebSocket(URL);
    await new Promise<void>((res, rej) => {
      ws.onopen = () => res();
      ws.onerror = () => rej(new Error(`cannot reach ${URL}: start jev-server first`));
    });

    const host = new RealHost();
    const rt = new Runtime(host, { supervisorMaxWallMs: WALL_MS, supervisorMaxSimS: Math.max(1, (WALL_MS / 1000) * RATE * 1.5) });
    const files = readFolder(join(repoRoot, "libraries", "triga-jsi-242"));
    rt.receive({ kind: "load", protocol: 1, source: { kind: "files", files } });
    await rt.idle();
    // start at the library's reference rod positions (its critical configuration)
    rt.receive({ kind: "load", protocol: 1, source: { kind: "files", files }, init: { rods: { ...rt.engine!.lib.refRods } } });
    await rt.idle();
    expect(rt.engine, "TRIGA library did not load").not.toBeNull();

    const pending = new Map<string, { sentAt: number; req: DecisionRequest }>();
    const rows: { t: number; wallMs: number; choice: string; status: string; ms: number; power: number; regPos: number; target: string; rods: string }[] = [];
    let outcome = { timeouts: 0, errors: 0 };
    ws.onmessage = (ev) => {
      const res = JSON.parse(String(ev.data)) as DecisionResponse;
      const p = pending.get(res.requestId);
      if (!p) return;
      pending.delete(res.requestId);
      const snap = rt.engine!.snapshot(false);
      const choice = p.req.candidates.find((c) => c.id === res.candidateId)?.text.slice(0, 40) ?? "-";
      if (res.status === "error") outcome.errors++;
      rows.push({
        t: p.req.observationSimTimeS,
        wallMs: Math.round(performance.now() - p.sentAt),
        choice: `${res.candidateId ?? "-"} (${choice})`,
        status: res.status,
        ms: Math.round(res.inferenceDurationMs ?? -1),
        power: snap.indicated?.["log"] ?? snap.truth.power,
        regPos: snap.truth.rods?.["regulating"]?.position ?? NaN,
        target: (rt as any).controller.target?.toExponential(2) ?? "off",
        rods: Object.entries<any>(snap.truth.rods).map(([k, r]) => `${k[0]}${r.position.toFixed(2)}`).join(" "),
      });
      rt.receive({ kind: "decision_response", response: res });
    };
    host.onRequest = (req) => {
      pending.set(req.requestId, { sentAt: performance.now(), req });
      ws.send(JSON.stringify(req));
    };

    const s0 = rt.engine!.snapshot(false);
    console.log(
      `TRIGA start: t=${s0.t} power=${s0.truth.power.toExponential(3)} W indicated.log=${s0.indicated?.["log"]} period=${s0.truth.period} mode=${s0.truth.mode} rods=${JSON.stringify(
        Object.fromEntries(Object.entries<any>(s0.truth.rods).map(([k, r]) => [k, +r.position.toFixed(3)])),
      )}`,
    );

    if (process.env["JEV_STARTUP"]) {
      // Operator start-up (no model): safety and shim fully out, regulating half out, then let the multiplication settle.
      // The transient (pulse) rod stays in: with it out the period trips.
      let seq = 1;
      const move = (rod: string, direction: string) =>
        rt.receive({ kind: "command", clientSeq: seq++, clientId: "operator", cmd: { type: "rod.move", rod, direction } });
      rt.receive({ kind: "time", rate: 20, paused: false });
      for (const rod of ["safety", "shim", "regulating"]) move(rod, "out");
      const t0 = performance.now();
      let regStopped = false;
      while ((performance.now() - t0) / 1000 < Number(process.env["JEV_STARTUP"])) {
        await sleep(100);
        host.out.length = 0;
        if (!regStopped && rt.engine!.snapshot(false).truth.rods.regulating.position >= 0.5) {
          regStopped = true;
          move("regulating", "stop");
        }
      }
      rt.receive({ kind: "time", paused: true });
      await sleep(300);
    } else {
      rt.receive({ kind: "time", rate: 1, paused: true }); // the reference rods are all in: source-level power
      await sleep(200);
    }
    const sr = rt.engine!.snapshot(false);
    console.log(
      `after start-up: sim t=${sr.t.toFixed(1)} power=${sr.truth.power.toExponential(3)} W period=${Number(sr.truth.period).toFixed(1)} s rods=${JSON.stringify(
        Object.fromEntries(Object.entries<any>(sr.truth.rods).map(([k, r]) => [k, +r.position.toFixed(3)])),
      )} trips=${JSON.stringify(sr.trips)}`,
    );

    // The instructor's goal: JEV_GOAL_X times the start power (JEV_GOAL2_X halfway through instead of the reactivity step).
    const p0 = rt.engine!.snapshot(false).indicated?.["log"] ?? rt.engine!.snapshot(false).truth.power;
    if (process.env["JEV_GOAL_W"]) {
      rt.receive({ kind: "supervisor.goal", powerW: Number(process.env["JEV_GOAL_W"]) });
      console.log(`-- goal set to ${process.env["JEV_GOAL_W"]} W (absolute)`);
    }
    if (process.env["JEV_GOAL_X"]) {
      rt.receive({ kind: "supervisor.goal", powerW: p0 * Number(process.env["JEV_GOAL_X"]) });
      console.log(`-- goal set to ${(p0 * Number(process.env["JEV_GOAL_X"])).toExponential(2)} W (start power ${p0.toExponential(2)} W)`);
    }
    rt.receive({ kind: "supervisor.enable" });
    rt.receive({ kind: "time", rate: RATE, paused: false });
    const start = performance.now();
    const mid = SECONDS / 2;
    let disturbed = false;
    while ((performance.now() - start) / 1000 < SECONDS) {
      await sleep(250);
      for (const m of host.out.splice(0)) if (m.kind === "snapshot") rt.receive({ kind: "frameAck" });
      if (!disturbed && (performance.now() - start) / 1000 > mid && process.env["JEV_GOAL2_X"]) {
        disturbed = true;
        rt.receive({ kind: "supervisor.goal", powerW: p0 * Number(process.env["JEV_GOAL2_X"]) });
        console.log(`-- goal changed to ${(p0 * Number(process.env["JEV_GOAL2_X"])).toExponential(2)} W at sim t=${rt.engine!.t.toFixed(1)} s`);
      }
      if (!disturbed && (performance.now() - start) / 1000 > mid) {
        disturbed = true;
        // a small reactivity insertion from the instructor: the controller has to answer it
        rt.receive({ kind: "command", clientSeq: 1, clientId: "instructor", cmd: { type: "fault.reactivity", deltaRho: Number(process.env["JEV_DELTA_RHO"] ?? 0.00003) } });
        console.log(`-- disturbance: +${process.env["JEV_DELTA_RHO"] ?? 0.00003} dk/k at sim t=${rt.engine!.t.toFixed(1)} s`);
      }
    }
    await rt.idle();
    const end = rt.engine!.snapshot(false);
    const clock = host.out.filter((m) => m.kind === "clock").at(-1) as any;
    const sup = rt.engine!.commandLog.filter((c: any) => c.clientId === "supervisor");
    const counts: Record<string, number> = {};
    for (const r of rows) counts[r.choice.split(" ")[0]!] = (counts[r.choice.split(" ")[0]!] ?? 0) + 1;
    console.log("choices:", JSON.stringify(counts));
    const stride = Math.max(1, Math.floor(rows.length / 30));
    console.table(rows.filter((_, i) => i % stride === 0 || (i > 0 && rows[i]!.choice !== rows[i - 1]!.choice)));
    const lat = rows.map((r) => r.ms).filter((x) => x >= 0).sort((a, b) => a - b);
    const wall = rows.map((r) => r.wallMs).sort((a, b) => a - b);
    const q = (a: number[], p: number) => a[Math.min(a.length - 1, Math.floor(a.length * p))] ?? NaN;
    console.log(
      `requests answered: ${rows.length}, errors: ${outcome.errors}; model ms p50/p95/max: ${q(lat, 0.5)}/${q(lat, 0.95)}/${lat.at(-1)}; round trip ms p50/p95/max: ${q(wall, 0.5)}/${q(wall, 0.95)}/${wall.at(-1)}`,
    );
    console.log(`supervisor rod commands: ${sup.length} ${JSON.stringify(sup.slice(0, 12).map((c: any) => `${c.t.toFixed(1)}s ${c.cmd.rod ?? c.cmd.type}:${c.cmd.direction ?? ""}`))}`);
    console.log(`end: t=${end.t.toFixed(1)} power=${end.truth.power.toExponential(3)} W, reg rod ${end.truth.rods?.["regulating"]?.position?.toFixed(3)}, clock limited=${clock?.limited ?? "no"} ${clock?.reason ?? ""}, trips=${JSON.stringify(end.trips)}`);
    ws.close();
    expect(rows.length).toBeGreaterThan(0);
  }, (SECONDS + 120) * 1000);
});
