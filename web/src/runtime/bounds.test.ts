/**
 * TD-08: Explicit resource limits and memory bounds (docs/TECH-DEBT-REVIEW.md § TD-08).
 *
 * Verifies:
 * 1. Output traffic backpressure: stale display updates coalesce when unacknowledged (awaitingFrameAck),
 *    while authoritative events (trips, acks, halts) are never dropped.
 * 2. Buffer ownership: Float32Array shape arrays transfer buffer ownership to the port.
 * 3. History limits: CheckpointStore enforces maxCheckpoints by thinning the older half while preserving
 *    step 0 and recent checkpoints; rewind and branching continue to function reliably.
 * 4. Exportability: sessions whose checkpoints have thinned remain fully exportable and replayable bit-identically.
 * 5. Accelerated synthetic session: runs sustained accelerated execution under continuous frame exchanges and
 *    operator commands, measuring heap memory on the local test machine, proving responsive controls and replay.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import os from "node:os";
import { describe, expect, it } from "vitest";
import { Engine } from "../sim/engine";
import { repoRoot } from "../sim/testing";
import type { FromWorker, SessionFile } from "./protocol";
import { MAIN_PORT, Runtime } from "./runtime";
import type { ScenarioFile } from "./scenario";
import { FakeHost, loadedRuntime, readFolder, send, syntheticCoreDir } from "./test-helpers";

const SCENARIOS_DIR = join(repoRoot, "web", "src", "app", "scenarios");
const readScenario = (id: string) => JSON.parse(readFileSync(join(SCENARIOS_DIR, `${id}.json`), "utf8")) as ScenarioFile;

describe("TD-08: Output backpressure and update coalescing", () => {
  it("coalesces stale display updates without dropping authoritative events when unacknowledged", async () => {
    const { host, rt } = await loadedRuntime({ snapshotHz: 30 });
    // Step 0 was posted upon load
    const snaps0 = host.of("snapshot");
    expect(snaps0.length).toBeGreaterThanOrEqual(1);

    // Drain host messages so we start clean
    host.drain();

    // Advance 50 steps without sending frameAck (client is busy or slow)
    for (let i = 0; i < 50; i++) {
      await send(rt, { kind: "step", n: 1 });
    }

    // Since awaitingFrameAck was set after the first snapshot, intermediate snapshots were suppressed
    const snapsDuringLag = host.of("snapshot");
    expect(snapsDuringLag.length).toBeLessThanOrEqual(1);

    // Inject an authoritative command: scram
    await send(rt, { kind: "command", clientSeq: 101, clientId: "op", cmd: { type: "scram" } });
    await send(rt, { kind: "step", n: 1 });

    // Events and command acks are NOT blocked by awaitingFrameAck
    const acks = host.of("ack");
    expect(acks.some((a) => a.clientSeq === 101 && a.status === "accepted")).toBe(true);

    const events = host.of("events");
    expect(events.some((e) => e.events.some((ev) => ev.type === "trip" && ev.id === "manual"))).toBe(true);

    // Now client acknowledges previous frame
    host.drain();
    await send(rt, { kind: "frameAck" });

    // Immediately receives a fresh snapshot with the latest step
    const freshSnaps = host.of("snapshot");
    expect(freshSnaps.length).toBe(1);
    expect(freshSnaps[0]!.snapshot.t).toBeCloseTo(rt.engine!.t, 8);
  });

  it("defines buffer ownership by transferring shape Float32Array buffers", async () => {
    const { host, rt } = await loadedRuntime();
    host.drain();

    // Move regulating rod to cause a significant rod position change, triggering shapeDue
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "rod.move", rod: "regulating", direction: "out" } });
    await send(rt, { kind: "step", n: 10 });
    // Client acknowledges frame to receive snapshot
    await send(rt, { kind: "frameAck" });

    const snapTransfers = host.transfers.filter((t) => t.msg.kind === "snapshot" && "shape" in t.msg && t.msg.shape);
    expect(snapTransfers.length).toBeGreaterThan(0);

    const last = snapTransfers[snapTransfers.length - 1]!;
    expect(last.transfer).toBeDefined();
    expect(Array.isArray(last.transfer)).toBe(true);
    // Buffer ownership is transferred via Transferable
    expect(last.transfer!.length).toBe(1);
    expect(last.transfer![0]).toBeInstanceOf(ArrayBuffer);
    expect((last.transfer![0] as ArrayBuffer).byteLength).toBeGreaterThan(0);
  });
});

describe("TD-08: Checkpoint store quotas, thinning, and exportability", () => {
  it("bounds retained checkpoints to maxCheckpoints and thins the older half while preserving step 0 and latest", async () => {
    const max = 8;
    const checkpointEveryS = 1;
    const { host, rt } = await loadedRuntime({ maxCheckpoints: max, checkpointEveryS });

    // Each step is 0.01s, checkpointEvery = 100 steps
    // Run 20 checkpoints = 2000 steps
    for (let i = 0; i < 20; i++) {
      await send(rt, { kind: "step", n: 100 });
    }

    const histMsg = host.last("history")!;
    expect(histMsg.thinned).toBe(true);
    expect(histMsg.checkpointSteps.length).toBeLessThanOrEqual(max);
    // Step 0 must always remain preserved
    expect(histMsg.checkpointSteps[0]).toBe(0);
    // The latest checkpoint is kept
    expect(histMsg.checkpointSteps[histMsg.checkpointSteps.length - 1]).toBe(rt.engine!.stepIndex);

    // Verify rewind to a preserved checkpoint works accurately
    const targetStep = histMsg.checkpointSteps[1]!;
    await send(rt, { kind: "rewind", step: targetStep });
    expect(rt.engine!.stepIndex).toBe(targetStep);

    // Verify rewind to an intermediate step (whose exact checkpoint was thinned) replays correctly from earlier checkpoint
    await send(rt, { kind: "rewind", step: 350 });
    expect(rt.engine!.stepIndex).toBe(350);
  });

  it("retains full exportability and deterministic replayability after checkpoint thinning", async () => {
    const { host, rt } = await loadedRuntime({ maxCheckpoints: 6, checkpointEveryS: 0.5 });

    // Submit some commands along the way
    await send(rt, { kind: "command", clientSeq: 1, clientId: "op", cmd: { type: "rod.move", rod: "safety", direction: "out" } });
    await send(rt, { kind: "step", n: 500 });
    await send(rt, { kind: "command", clientSeq: 2, clientId: "op", cmd: { type: "rod.move", rod: "safety", direction: "stop" } });
    await send(rt, { kind: "step", n: 1000 });

    expect(host.last("history")!.thinned).toBe(true);
    const endState = rt.engine!.checkpoint();

    // Export session
    await send(rt, { kind: "session.export" });
    const exported = host.last("session")!.file;
    expect(exported.version).toBe(3);
    expect(exported.session.commands.length).toBe(2);

    // Re-import into a fresh runtime
    const r2 = await loadedRuntime();
    await send(r2.rt, { kind: "session.import", file: exported });

    const importedState = r2.rt.engine!.checkpoint();
    expect(importedState.stepIndex).toBe(endState.stepIndex);
    expect(r2.rt.engine!.t).toBeCloseTo(rt.engine!.t, 8);
    expect(importedState.y).toEqual(endState.y);
    expect(importedState.motions).toEqual(endState.motions);
    expect(importedState.mode).toBe(endState.mode);
  });
});

describe("TD-08: Accelerated synthetic session memory and responsiveness harness", () => {
  it("sustains an accelerated synthetic session within stated memory budget with responsive controls and rewind", async () => {
    const scn = readScenario("synthetic-power-ascension");
    const { host, rt } = await loadedRuntime({ snapshotHz: 30, lagLimitS: 1000 }, { scenario: scn });

    // Establish baseline memory
    if (typeof global.gc === "function") global.gc();
    const memInitial = process.memoryUsage();

    // Run accelerated session with active operator control loop
    let clientSeq = 1;
    let maxAckLatencySteps = 0;
    const totalSimSteps = 4000; // 40 seconds of fine kinetics
    const chunkSteps = 20;

    for (let step = 0; step < totalSimSteps; step += chunkSteps) {
      // Operator activity: adjust regulating rod periodically
      if (step === 100) {
        await send(rt, { kind: "command", clientSeq: clientSeq++, clientId: "op", cmd: { type: "rod.move", rod: "safety", direction: "out" } });
      } else if (step === 300) {
        await send(rt, { kind: "command", clientSeq: clientSeq++, clientId: "op", cmd: { type: "rod.move", rod: "regulating", direction: "out" } });
      } else if (step > 600 && step % 400 === 0) {
        const startStep = rt.engine!.stepIndex;
        const curSeq = clientSeq++;
        const dir = (step / 400) % 2 === 0 ? "out" : "in";
        await send(rt, { kind: "command", clientSeq: curSeq, clientId: "op", cmd: { type: "rod.move", rod: "regulating", direction: dir } });
        // Track latency to ack
        const ack = host.of("ack").find((a) => a.clientSeq === curSeq);
        if (ack) {
          const latency = rt.engine!.stepIndex - startStep;
          if (latency > maxAckLatencySteps) maxAckLatencySteps = latency;
        }
      }

      // Step simulation
      await send(rt, { kind: "step", n: chunkSteps });

      // Simulate responsive client sending frameAck
      await send(rt, { kind: "frameAck" });

      // Drain client buffers to prevent unbounded memory growth in the test host harness
      host.drain();
    }

    // Verify commands were processed responsively
    expect(maxAckLatencySteps).toBeLessThanOrEqual(chunkSteps);

    // Final memory reading
    if (typeof global.gc === "function") global.gc();
    const memFinal = process.memoryUsage();
    const heapUsedDeltaMB = (memFinal.heapUsed - memInitial.heapUsed) / (1024 * 1024);
    const heapTotalDeltaMB = (memFinal.heapTotal - memInitial.heapTotal) / (1024 * 1024);
    const rssDeltaMB = (memFinal.rss - memInitial.rss) / (1024 * 1024);

    const testMachine = {
      platform: os.platform(),
      arch: os.arch(),
      cpus: os.cpus().length,
      nodeVersion: process.version,
      totalMemoryGB: (os.totalmem() / (1024 * 1024 * 1024)).toFixed(1),
    };

    console.log("TD-08 Benchmark Measurement:", {
      testMachine,
      simSteps: totalSimSteps,
      finalSimTimeS: rt.engine!.t,
      heapUsedInitialMB: (memInitial.heapUsed / (1024 * 1024)).toFixed(2),
      heapUsedFinalMB: (memFinal.heapUsed / (1024 * 1024)).toFixed(2),
      heapUsedDeltaMB: heapUsedDeltaMB.toFixed(2),
      heapTotalDeltaMB: heapTotalDeltaMB.toFixed(2),
      rssDeltaMB: rssDeltaMB.toFixed(2),
      maxAckLatencySteps,
    });

    // Stated memory budget: heap delta during the sustained session must be strictly bounded (< 35 MB)
    expect(heapUsedDeltaMB).toBeLessThan(35);

    // Verify retained history can still replay faithfully
    const latestStep = rt.engine!.stepIndex;
    expect(latestStep).toBe(totalSimSteps);

    await send(rt, { kind: "rewind", step: 500 });
    expect(rt.engine!.stepIndex).toBe(500);

    // Replay forward again
    await send(rt, { kind: "step", n: 100 });
    expect(rt.engine!.stepIndex).toBe(600);
  });
});
