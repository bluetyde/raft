/**
 * Headless runner: one case file in, one run folder out, no browser. Node only (not bundled into the web app).
 *
 * Run folder (written like NODAL's run manifest: the manifest is written last, and a folder whose manifest still says
 * "running" is an interrupted run):
 *   <out>/<runId>/case.json      the case as given (byte copy)
 *   <out>/<runId>/results.json   samples, events and final values; no clock or path inside, so one case gives identical bytes
 *   <out>/<runId>/session.json   engine session (pins, seed, init, command log) for replay
 *   <out>/<runId>/manifest.json  status, pins, sha256 of every file
 */

import { createHash, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { nodeReader } from "../library/node-reader";
import { CAPABILITY, ENGINE_VERSION, Engine, InitError, CheckpointError } from "../sim/engine";
import { LibraryError, loadLibrary, type Library } from "../sim/library";
import { sampleFromEngine } from "../sim/vectors";
import { parseCase, type CaseIssue, type HeadlessCase } from "./case";

export const RESULTS_FORMAT = "raft-headless-results";
export const MANIFEST_FORMAT = "raft-headless-run";
export const FORMAT_VERSION = 1;
export const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/;

export type RunStatus = "running" | "completed" | "failed";
export type Refusal = { ok: false; errors: CaseIssue[] };

export interface RunOptions {
  casePath: string;
  outRoot: string;
  runId?: string;
  now?: () => Date;
  /** Test hook: called after every step with the engine. */
  afterStep?: (engine: Engine) => void;
}

export interface RunSummary {
  ok: true;
  runId: string;
  runDir: string;
  status: "completed" | "failed";
  reason?: string;
  steps: number;
}

const sha = (data: string | Uint8Array) => createHash("sha256").update(data).digest("hex");

function refuse(code: string, field: string, message: string): Refusal {
  return { ok: false, errors: [{ code, field, message }] };
}

function writeAtomic(path: string, data: string): void {
  const tmp = `${path}.tmp-${randomBytes(6).toString("hex")}`;
  try {
    writeFileSync(tmp, data, "utf8");
    renameSync(tmp, path);
  } catch (e) {
    try {
      if (existsSync(tmp)) unlinkSync(tmp);
    } catch {
      // the original error is the one to report
    }
    throw e;
  }
}

/** The first non-finite number in a value, as a path, or null. JSON.stringify would turn it into null silently. */
export function findNonFinite(v: unknown, path = ""): string | null {
  if (typeof v === "number") return Number.isFinite(v) ? null : path || "/";
  if (Array.isArray(v)) {
    for (let i = 0; i < v.length; i++) {
      const hit = findNonFinite(v[i], `${path}/${i}`);
      if (hit) return hit;
    }
  } else if (v !== null && typeof v === "object") {
    for (const [k, x] of Object.entries(v)) {
      const hit = findNonFinite(x, `${path}/${k}`);
      if (hit) return hit;
    }
  }
  return null;
}

type Loaded = { c: HeadlessCase; caseBytes: Buffer; libraryDir: string; lib: Library };

async function load(casePath: string): Promise<Loaded | Refusal> {
  let caseBytes: Buffer;
  try {
    caseBytes = readFileSync(casePath);
  } catch (e) {
    const code = (e as NodeJS.ErrnoException).code;
    return refuse(code === "ENOENT" ? "E_NOT_FOUND" : "E_INTERNAL", "/case", `cannot read the case file: ${code ?? String(e)}`);
  }
  let raw: unknown;
  try {
    raw = JSON.parse(caseBytes.toString("utf8"));
  } catch {
    return refuse("E_CASE_INVALID", "", "the case file is not valid JSON");
  }
  const parsed = parseCase(raw);
  if (!parsed.ok) return parsed;
  const libraryDir = resolve(dirname(casePath), parsed.value.library);
  if (!existsSync(libraryDir) || !statSync(libraryDir).isDirectory()) {
    return refuse("E_NOT_FOUND", "/library", "the library folder does not exist");
  }
  try {
    const lib = await loadLibrary(nodeReader(libraryDir));
    return { c: parsed.value, caseBytes, libraryDir, lib };
  } catch (e) {
    if (e instanceof LibraryError) return refuse("E_LIBRARY", "/library", e.message);
    throw e;
  }
}

function makeEngine(lib: Library, c: HeadlessCase): Engine | Refusal {
  try {
    return new Engine(lib, c.init, c.seed, c.config);
  } catch (e) {
    if (e instanceof InitError) return refuse(e.code, "/init", e.message);
    throw e;
  }
}

/** Validate a case and its library, and build the engine, without running or writing anything. */
export async function validateCase(casePath: string): Promise<{ ok: true; libraryDigest: string; caseSha256: string } | Refusal> {
  const l = await load(casePath);
  if ("ok" in l) return l;
  const e = makeEngine(l.lib, l.c);
  if (!(e instanceof Engine)) return e;
  return { ok: true, libraryDigest: l.lib.digest, caseSha256: sha(l.caseBytes) };
}

export async function runCase(opts: RunOptions): Promise<RunSummary | Refusal> {
  const now = opts.now ?? (() => new Date());
  const runId = opts.runId ?? `r-${randomBytes(6).toString("hex")}`;
  if (!RUN_ID_PATTERN.test(runId)) return refuse("E_CASE_INVALID", "/runId", "run id must match " + RUN_ID_PATTERN.source);
  const l = await load(opts.casePath);
  if ("ok" in l) return l;
  const engine = makeEngine(l.lib, l.c);
  if (!(engine instanceof Engine)) return engine;

  const runDir = join(resolve(opts.outRoot), runId);
  if (existsSync(runDir)) return refuse("E_EXISTS", "/runId", "a run with this id already exists");
  mkdirSync(runDir, { recursive: true });
  const createdAt = now().toISOString();
  const caseSha256 = sha(l.caseBytes);
  const base = {
    format: MANIFEST_FORMAT,
    version: FORMAT_VERSION,
    runId,
    createdAt,
    engine: { version: ENGINE_VERSION, capability: CAPABILITY },
    libraryDigest: l.lib.digest,
    libraryPath: l.libraryDir,
    caseSha256,
    steps: l.c.steps,
  };
  writeFileSync(join(runDir, "case.json"), l.caseBytes);
  // Step 1 of the commit protocol: a manifest that says "running" and has no finish time.
  writeAtomic(join(runDir, "manifest.json"), JSON.stringify({ ...base, status: "running" satisfies RunStatus, files: [] }, null, 2) + "\n");

  const byStep = new Map<number, { cmd: Record<string, unknown>; clientId: string }[]>();
  for (const item of l.c.script) {
    const list = byStep.get(item.step) ?? [];
    list.push({ cmd: item.cmd, clientId: item.clientId });
    byStep.set(item.step, list);
  }
  const samples: Record<string, unknown>[] = [sampleFromEngine(engine)];
  let status: "completed" | "failed" = "completed";
  let reason: string | undefined;
  try {
    for (let k = 0; k < l.c.steps; k++) {
      for (const item of byStep.get(k) ?? []) engine.submit(item.cmd, item.clientId);
      engine.step();
      opts.afterStep?.(engine);
      if (engine.stepIndex % l.c.sampleEvery === 0 || engine.stepIndex === l.c.steps) {
        const s = sampleFromEngine(engine);
        const bad = findNonFinite(s);
        if (bad) {
          status = "failed";
          reason = `non-finite value at step ${engine.stepIndex} (${bad})`;
          break;
        }
        samples.push(s);
      }
      if (engine.halted) {
        status = "failed";
        reason = `engine halted: ${engine.halted}`;
        break;
      }
    }
  } catch (e) {
    status = "failed";
    reason = `engine error: ${e instanceof Error ? e.message : String(e)}`;
  }

  const results = {
    format: RESULTS_FORMAT,
    version: FORMAT_VERSION,
    runId,
    engine: { version: ENGINE_VERSION, capability: CAPABILITY },
    libraryId: l.lib.id,
    libraryDigest: l.lib.digest,
    caseSha256,
    completion: { status, stepsRun: engine.stepIndex, steps: l.c.steps, ...(reason ? { reason } : {}) },
    pins: engine.pins(),
    samples,
    events: structuredClone(engine.events),
    final: { peakPower: engine.peakPower, peakTime: engine.peakTime, halted: engine.halted },
  };
  const resultsText = JSON.stringify(results, null, 2) + "\n";
  const sessionText = JSON.stringify(engine.session(), null, 2) + "\n";
  writeAtomic(join(runDir, "results.json"), resultsText);
  writeAtomic(join(runDir, "session.json"), sessionText);
  const file = (path: string, role: string, text: string | Buffer) => ({ path, role, sha256: sha(text), bytes: Buffer.byteLength(text) });
  const files = [file("case.json", "case", l.caseBytes), file("results.json", "results", resultsText), file("session.json", "session", sessionText)];
  writeAtomic(
    join(runDir, "manifest.json"),
    JSON.stringify({ ...base, status, ...(reason ? { reason } : {}), finishedAt: now().toISOString(), stepsRun: engine.stepIndex, files }, null, 2) + "\n",
  );
  return { ok: true, runId, runDir, status, ...(reason ? { reason } : {}), steps: engine.stepIndex };
}

export type ReplayReport = { ok: true; identical: boolean; differences: string[] } | Refusal;

/** Re-run a finished run from its session and compare the final state with its results, exactly (the engine is deterministic). */
export async function replayRun(runDir: string): Promise<ReplayReport> {
  const read = (name: string): unknown | Refusal => {
    try {
      return JSON.parse(readFileSync(join(runDir, name), "utf8"));
    } catch (e) {
      const code = (e as NodeJS.ErrnoException).code;
      return refuse(code === "ENOENT" ? "E_NOT_FOUND" : "E_INTERNAL", `/${name}`, `cannot read ${name}`);
    }
  };
  const manifest = read("manifest.json") as Record<string, any>;
  if ("errors" in manifest) return manifest as unknown as Refusal;
  if (manifest.status !== "completed") return refuse("E_NOT_COMPLETE", "/manifest/status", `only a completed run can be replayed (status ${String(manifest.status)})`);
  const results = read("results.json") as Record<string, any>;
  if ("errors" in results) return results as unknown as Refusal;
  const session = read("session.json") as Record<string, any>;
  if ("errors" in session) return session as unknown as Refusal;
  const differences: string[] = [];
  for (const f of manifest.files as { path: string; sha256: string }[]) {
    if (isAbsolute(f.path) || f.path.includes("..")) return refuse("E_PATH_TRAVERSAL", "/manifest/files", "file path leaves the run folder");
    const actual = sha(readFileSync(join(runDir, f.path)));
    if (actual !== f.sha256) differences.push(`${f.path} does not match its manifest hash`);
  }
  if (differences.length > 0) return { ok: true, identical: false, differences };
  if (typeof manifest.libraryPath !== "string") return refuse("E_CASE_INVALID", "/manifest/libraryPath", "manifest has no library path");
  let lib: Library;
  try {
    lib = await loadLibrary(nodeReader(manifest.libraryPath));
  } catch (e) {
    if (e instanceof LibraryError) return refuse("E_LIBRARY", "/manifest/libraryPath", e.message);
    throw e;
  }
  let e: Engine;
  try {
    e = Engine.replay(lib, session, results.completion.stepsRun);
  } catch (err) {
    if (err instanceof CheckpointError) return { ok: true, identical: false, differences: [`session does not match this engine and library: ${err.message}`] };
    throw err;
  }
  const last = results.samples[results.samples.length - 1];
  const again = sampleFromEngine(e);
  if (JSON.stringify(last) !== JSON.stringify(again)) differences.push("final sample differs from the replay");
  if (e.peakPower !== results.final.peakPower || e.peakTime !== results.final.peakTime) differences.push("peak power or time differs from the replay");
  return { ok: true, identical: differences.length === 0, differences };
}
