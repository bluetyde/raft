import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { compareDocs } from "../sim/compare";
import { engineVectorsDir, syntheticCorePath } from "../sim/testing";
import { parseCase } from "./case";
import { describe as describeRunner, main } from "./cli";
import { findNonFinite, replayRun, runCase, validateCase } from "./run";

const dirs: string[] = [];
afterEach(() => {
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});
const tmp = () => {
  const d = mkdtempSync(join(tmpdir(), "raft-headless-"));
  dirs.push(d);
  return d;
};
const sha = (b: Buffer | string) => createHash("sha256").update(b).digest("hex");

function vector(name: string): Record<string, any> {
  return JSON.parse(readFileSync(join(engineVectorsDir, `${name}.json`), "utf8"));
}

/** A case folder: the synthetic library copied in, and the golden vector's scenario as a case file. */
function caseFolder(name = "scram", edit: (c: Record<string, any>) => void = () => {}): { dir: string; casePath: string; vec: Record<string, any> } {
  const dir = tmp();
  cpSync(syntheticCorePath, join(dir, "lib"), { recursive: true });
  const vec = vector(name);
  const c: Record<string, any> = {
    format: "raft-headless-case",
    version: 1,
    library: "lib",
    seed: vec.seed,
    init: vec.init,
    config: vec.config,
    steps: vec.steps,
    sampleEvery: vec.sampleEvery,
    // the golden vectors were recorded with the client id "local"
    script: vec.script.map((i: Record<string, unknown>) => ({ ...i, clientId: "local" })),
  };
  edit(c);
  const casePath = join(dir, "case.json");
  writeFileSync(casePath, JSON.stringify(c, null, 2));
  return { dir, casePath, vec };
}

const VECTORS = readdirSync(engineVectorsDir).filter((f) => f.endsWith(".json")).map((f) => f.replace(".json", ""));

describe("every engine golden vector, run through the headless runner (oracle agreement)", () => {
  it.each(VECTORS)("%s matches the committed vector within its declared tolerances", async (name) => {
    const { dir, casePath, vec } = caseFolder(name);
    const out = join(dir, "runs");
    const r = await runCase({ casePath, outRoot: out, runId: "r1" });
    if (!r.ok) throw new Error(JSON.stringify(r.errors));
    expect(r.status).toBe("completed");
    const results = JSON.parse(readFileSync(join(r.runDir, "results.json"), "utf8"));
    const got = { samples: results.samples, events: results.events, final: { peakPower: results.final.peakPower, peakTime: results.final.peakTime } };
    const want = { samples: vec.samples, events: vec.events, final: vec.final };
    expect(compareDocs(want, got, vec.tolerances)).toEqual([]);
    expect(results.pins.libraryDigest).toBe(vec.pins.libraryDigest);
  });
});

describe("run folder", () => {
  it("is committed in order and every manifest hash verifies", async () => {
    const { dir, casePath } = caseFolder();
    const r = await runCase({ casePath, outRoot: join(dir, "runs"), runId: "r1", now: () => new Date("2026-10-03T12:00:00Z") });
    if (!r.ok) throw new Error("run refused");
    const m = JSON.parse(readFileSync(join(r.runDir, "manifest.json"), "utf8"));
    expect(m).toMatchObject({ format: "raft-headless-run", runId: "r1", status: "completed", createdAt: "2026-10-03T12:00:00.000Z", finishedAt: "2026-10-03T12:00:00.000Z" });
    expect(m.files.map((f: { path: string }) => f.path)).toEqual(["case.json", "results.json", "session.json"]);
    for (const f of m.files) {
      const bytes = readFileSync(join(r.runDir, f.path));
      expect(sha(bytes)).toBe(f.sha256);
      expect(bytes.length).toBe(f.bytes);
    }
    expect(sha(readFileSync(casePath))).toBe(m.caseSha256);
    expect(readdirSync(r.runDir).filter((n) => n.includes(".tmp-"))).toEqual([]);
  });

  it("while the run is going the manifest says running and the results do not exist yet (an interrupted run is visible)", async () => {
    const { dir, casePath } = caseFolder();
    let seen: { status?: string; finishedAt?: unknown; results: boolean; files: number } | null = null;
    const r = await runCase({
      casePath,
      outRoot: join(dir, "runs"),
      runId: "live",
      afterStep: (e) => {
        if (e.stepIndex !== 5) return;
        const m = JSON.parse(readFileSync(join(dir, "runs", "live", "manifest.json"), "utf8"));
        seen = { status: m.status, finishedAt: m.finishedAt, results: existsSync(join(dir, "runs", "live", "results.json")), files: m.files.length };
      },
    });
    expect(r.ok).toBe(true);
    expect(seen).toEqual({ status: "running", finishedAt: undefined, results: false, files: 0 });
  });

  it("the same case gives byte-identical results and session (deterministic, no clock inside)", async () => {
    const { dir, casePath } = caseFolder("pulse");
    const a = await runCase({ casePath, outRoot: join(dir, "runs"), runId: "a" });
    const b = await runCase({ casePath, outRoot: join(dir, "runs"), runId: "b", now: () => new Date(0) });
    if (!a.ok || !b.ok) throw new Error("refused");
    const norm = (p: string) => readFileSync(p, "utf8").split('"runId": "a"').join('"runId": "b"');
    expect(norm(join(a.runDir, "results.json"))).toBe(readFileSync(join(b.runDir, "results.json"), "utf8"));
    expect(readFileSync(join(a.runDir, "session.json"), "utf8")).toBe(readFileSync(join(b.runDir, "session.json"), "utf8"));
  });

  it("a different seed or script gives a different result", async () => {
    const base = caseFolder("rod-withdrawal");
    const other = caseFolder("rod-withdrawal", (c) => (c.script = []));
    const a = await runCase({ casePath: base.casePath, outRoot: join(base.dir, "runs"), runId: "x" });
    const b = await runCase({ casePath: other.casePath, outRoot: join(other.dir, "runs"), runId: "x" });
    if (!a.ok || !b.ok) throw new Error("refused");
    expect(readFileSync(join(a.runDir, "results.json"), "utf8")).not.toBe(readFileSync(join(b.runDir, "results.json"), "utf8"));
  });

  it("refuses an existing run id and a bad run id, and creates nothing", async () => {
    const { dir, casePath } = caseFolder();
    const out = join(dir, "runs");
    expect((await runCase({ casePath, outRoot: out, runId: "r1" })).ok).toBe(true);
    const again = await runCase({ casePath, outRoot: out, runId: "r1" });
    expect(again.ok).toBe(false);
    if (!again.ok) expect(again.errors[0]?.code).toBe("E_EXISTS");
    for (const id of ["", "../x", "a/b", "-x", "x".repeat(65)]) {
      const r = await runCase({ casePath, outRoot: out, runId: id });
      expect(r.ok).toBe(false);
    }
    expect(readdirSync(out)).toEqual(["r1"]);
  });

  it("a failing step ends the run as failed with the reason, and keeps the partial samples", async () => {
    const { dir, casePath } = caseFolder();
    const r = await runCase({
      casePath,
      outRoot: join(dir, "runs"),
      runId: "f1",
      afterStep: (e) => {
        if (e.stepIndex === 25) throw new Error("injected failure");
      },
    });
    if (!r.ok) throw new Error("refused");
    expect(r).toMatchObject({ status: "failed" });
    expect(r.reason).toContain("injected failure");
    const m = JSON.parse(readFileSync(join(r.runDir, "manifest.json"), "utf8"));
    expect(m.status).toBe("failed");
    const res = JSON.parse(readFileSync(join(r.runDir, "results.json"), "utf8"));
    expect(res.completion.status).toBe("failed");
    expect(res.completion.stepsRun).toBe(25);
    expect(res.samples.length).toBeGreaterThan(1);
    const replay = await replayRun(r.runDir);
    expect(replay.ok).toBe(false);
  });

  it("a halted engine ends the run as failed at that step", async () => {
    const { dir, casePath } = caseFolder();
    const r = await runCase({ casePath, outRoot: join(dir, "runs"), runId: "halt", afterStep: (e) => { if (e.stepIndex === 30) e.halted = "R_TABLE_REJECT_test"; } });
    if (!r.ok) throw new Error("refused");
    expect(r).toMatchObject({ status: "failed", steps: 30 });
    expect(r.reason).toContain("R_TABLE_REJECT_test");
  });

  it("a non-finite sample fails the run instead of being written as null", async () => {
    const { dir, casePath } = caseFolder();
    const r = await runCase({
      casePath,
      outRoot: join(dir, "runs"),
      runId: "nf",
      afterStep: (e) => {
        if (e.stepIndex === 20) e.y[10] = Number.NaN; // the xenon state, which every sample reports
      },
    });
    if (!r.ok) throw new Error("refused");
    expect(r.status).toBe("failed");
    expect(r.reason).toContain("non-finite");
    expect(findNonFinite({ a: [1, { b: Number.POSITIVE_INFINITY }] })).toBe("/a/1/b");
    expect(findNonFinite({ a: [1, 2] })).toBeNull();
  });
});

describe("refusals create no run folder", () => {
  const cases: [string, (c: Record<string, any>) => void, string][] = [
    ["wrong format", (c) => (c.format = "other"), "E_CASE_VERSION"],
    ["future version", (c) => (c.version = 2), "E_CASE_VERSION"],
    ["unknown field", (c) => (c.extra = 1), "E_CASE_INVALID"],
    ["steps zero", (c) => (c.steps = 0), "E_CASE_INVALID"],
    ["steps too many", (c) => (c.steps = 2_000_001), "E_CASE_INVALID"],
    ["sampleEvery beyond steps", (c) => (c.sampleEvery = c.steps + 1), "E_CASE_INVALID"],
    ["seed negative", (c) => (c.seed = -1), "E_CASE_INVALID"],
    ["seed fractional", (c) => (c.seed = 1.5), "E_CASE_INVALID"],
    ["script step at the end", (c) => (c.script = [{ step: c.steps, cmd: { type: "scram" } }]), "E_CASE_INVALID"],
    ["script cmd without type", (c) => (c.script = [{ step: 0, cmd: {} }]), "E_CASE_INVALID"],
    ["script not an array", (c) => (c.script = {}), "E_CASE_INVALID"],
    ["absolute library", (c) => (c.library = "/etc"), "E_PATH_INVALID"],
    ["drive library", (c) => (c.library = "C:/lib"), "E_PATH_INVALID"],
    ["dotdot library", (c) => (c.library = "../lib"), "E_PATH_INVALID"],
    ["backslash library", (c) => (c.library = "lib" + String.fromCharCode(92) + "x"), "E_PATH_INVALID"],
    ["missing library folder", (c) => (c.library = "nowhere"), "E_NOT_FOUND"],
    ["unknown engine method", (c) => (c.config = { method: "nope" }), "E_INIT_INVALID"],
    ["init that cannot start", (c) => (c.init = { rods: { safety: 1.0, regulating: 1.0, transient: 1.0 } }), "E_INIT_NO_EQUILIBRIUM"],
  ];
  it.each(cases)("%s", async (_n, edit, code) => {
    const { dir, casePath } = caseFolder("scram", edit);
    const out = join(dir, "runs");
    const r = await runCase({ casePath, outRoot: out });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.errors[0]?.code).toBe(code);
    expect(existsSync(out)).toBe(false);
    const v = await validateCase(casePath);
    expect(v.ok).toBe(false);
  });

  it("a file that is not JSON, and a missing file", async () => {
    const dir = tmp();
    writeFileSync(join(dir, "bad.json"), "{nope");
    const a = await validateCase(join(dir, "bad.json"));
    expect(!a.ok && a.errors[0]?.code).toBe("E_CASE_INVALID");
    const b = await validateCase(join(dir, "missing.json"));
    expect(!b.ok && b.errors[0]?.code).toBe("E_NOT_FOUND");
  });

  it("parseCase fills the defaults and never throws on garbage", () => {
    for (const junk of [null, undefined, 1, "x", [], { format: "raft-headless-case" }]) {
      expect(parseCase(junk).ok).toBe(false);
    }
    const ok = parseCase({ format: "raft-headless-case", version: 1, library: "lib", seed: 1, steps: 10, sampleEvery: 5, script: [{ step: 0, cmd: { type: "scram" } }] });
    expect(ok.ok && ok.value.script[0]?.clientId).toBe("headless");
    expect(ok.ok && ok.value.init).toEqual({});
  });

  it("a command the engine rejects is recorded in the events, not hidden", async () => {
    const { dir, casePath } = caseFolder("scram", (c) => (c.script = [{ step: 0, cmd: { type: "nonsense" } }]));
    const r = await runCase({ casePath, outRoot: join(dir, "runs"), runId: "rej" });
    if (!r.ok) throw new Error("refused");
    const res = JSON.parse(readFileSync(join(r.runDir, "results.json"), "utf8"));
    expect(res.events.find((e: any) => e.type === "command")).toMatchObject({ status: "rejected", reason: "REJ_UNKNOWN_COMMAND" });
  });
});

describe("replay", () => {
  it("reproduces a completed run exactly", async () => {
    const { dir, casePath } = caseFolder("rod-withdrawal");
    const r = await runCase({ casePath, outRoot: join(dir, "runs"), runId: "r1" });
    if (!r.ok) throw new Error("refused");
    expect(await replayRun(r.runDir)).toEqual({ ok: true, identical: true, differences: [] });
  });

  it("reports a tampered results file, session, case or library", async () => {
    const make = async () => {
      const { dir, casePath } = caseFolder("scram");
      const r = await runCase({ casePath, outRoot: join(dir, "runs"), runId: "r1" });
      if (!r.ok) throw new Error("refused");
      return { dir, run: r.runDir };
    };
    const tamper = async (file: string, edit: (t: string) => string) => {
      const { run } = await make();
      writeFileSync(join(run, file), edit(readFileSync(join(run, file), "utf8")));
      const rep = await replayRun(run);
      expect(rep.ok && !rep.identical).toBe(true);
    };
    await tamper("results.json", (t) => t.replace('"peakPower"', '"peakPower": 1, "x"'));
    await tamper("session.json", (t) => t.replace('"scram"', '"trip.reset"'));
    await tamper("case.json", (t) => t.replace('"steps": 400', '"steps": 401'));
    // A library that changed after the run no longer matches the session pins.
    const { dir, run } = await make();
    const arrays = join(dir, "lib", "arrays");
    const first = readdirSync(arrays)[0]!;
    writeFileSync(join(arrays, first), "[]");
    const rep = await replayRun(run);
    expect(rep.ok && rep.identical).toBe(false);
  });

  it("catches a results file that was changed and re-hashed, so the manifest alone cannot vouch for it", async () => {
    const edits: [string, (r: Record<string, any>) => void][] = [
      ["final sample", (r) => (r.samples[r.samples.length - 1].power *= 1.0000001)],
      ["peak", (r) => (r.final.peakPower *= 2)],
    ];
    for (const [what, edit] of edits) {
      const { dir, casePath } = caseFolder("scram");
      const r = await runCase({ casePath, outRoot: join(dir, "runs"), runId: "r1" });
      if (!r.ok) throw new Error("refused");
      const resPath = join(r.runDir, "results.json");
      const res = JSON.parse(readFileSync(resPath, "utf8"));
      edit(res);
      const text = JSON.stringify(res, null, 2) + "\n";
      writeFileSync(resPath, text);
      const mPath = join(r.runDir, "manifest.json");
      const m = JSON.parse(readFileSync(mPath, "utf8"));
      const entry = m.files.find((f: { path: string }) => f.path === "results.json");
      entry.sha256 = sha(text);
      entry.bytes = Buffer.byteLength(text);
      writeFileSync(mPath, JSON.stringify(m, null, 2));
      const rep = await replayRun(r.runDir);
      expect(rep.ok && !rep.identical, what).toBe(true);
    }
  });

  it("refuses a run that is not completed, or a missing folder", async () => {
    const dir = tmp();
    mkdirSync(join(dir, "r"));
    writeFileSync(join(dir, "r", "manifest.json"), JSON.stringify({ status: "running", files: [] }));
    const a = await replayRun(join(dir, "r"));
    expect(!a.ok && a.errors[0]?.code).toBe("E_NOT_COMPLETE");
    const b = await replayRun(join(dir, "missing"));
    expect(!b.ok && b.errors[0]?.code).toBe("E_NOT_FOUND");
  });
});

describe("command line", () => {
  it("describe lists the engine version and every command type of the schema", () => {
    const d = describeRunner() as Record<string, any>;
    expect(d.engine.version).toMatch(/^\d+\.\d+\.\d+$/);
    expect(d.commands).toEqual(["fault.instrument", "fault.reactivity", "mode.set", "pump.set", "rod.fire", "rod.move", "scram", "trip.reset"]);
  });

  it("exit codes: 0 completed, 1 failed, 2 refused or bad usage; one JSON object on stdout", async () => {
    const { dir, casePath } = caseFolder();
    const out = join(dir, "runs");
    const ok = await main(["run", casePath, "--out", out, "--run-id", "c1"]);
    expect(ok.code).toBe(0);
    expect(JSON.parse(ok.out)).toMatchObject({ ok: true, runId: "c1", status: "completed" });
    expect((await main(["validate", casePath])).code).toBe(0);
    expect((await main(["replay", join(out, "c1")])).code).toBe(0);
    expect((await main(["run", casePath, "--out", out, "--run-id", "c1"])).code).toBe(2);
    for (const argv of [[], ["nope"], ["run"], ["run", casePath], ["validate"], ["replay"]]) {
      const r = await main(argv);
      expect(r.code).toBe(2);
      expect(JSON.parse(r.out).errors[0].code).toBe("E_USAGE");
    }
    expect(r2(await main(["validate", join(dir, "missing.json")]))).toBe(2);
  });
});

function r2(x: { code: number }): number {
  return x.code;
}
