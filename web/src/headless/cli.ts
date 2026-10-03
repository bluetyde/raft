/**
 * Command line for the headless runner. Every verb prints one JSON object on stdout.
 * Exit status: 0 the verb succeeded (a run that finished "failed" is 1), 2 the input was refused or the usage is wrong.
 *
 *   describe
 *   validate <case.json>
 *   run <case.json> --out <folder> [--run-id <id>]
 *   replay <run-folder>
 */

import commandSchema from "../../../schema/command.schema.json";
import { CAPABILITY, ENGINE_VERSION } from "../sim/engine";
import { CASE_FORMAT, CASE_VERSION, MAX_SCRIPT, MAX_STEPS } from "./case";
import { FORMAT_VERSION, MANIFEST_FORMAT, RESULTS_FORMAT, replayRun, runCase, validateCase } from "./run";

function commandTypes(node: unknown, out = new Set<string>()): string[] {
  if (Array.isArray(node)) node.forEach((n) => commandTypes(n, out));
  else if (node !== null && typeof node === "object") {
    const o = node as Record<string, unknown>;
    const t = (o.properties as Record<string, { const?: unknown }> | undefined)?.type;
    if (t && typeof t.const === "string") out.add(t.const);
    Object.values(o).forEach((v) => commandTypes(v, out));
  }
  return [...out].sort();
}

export function describe(): Record<string, unknown> {
  return {
    ok: true,
    format: "raft-headless-describe",
    version: FORMAT_VERSION,
    engine: { version: ENGINE_VERSION, capability: CAPABILITY },
    caseFormat: { format: CASE_FORMAT, version: CASE_VERSION, maxSteps: MAX_STEPS, maxScriptEntries: MAX_SCRIPT },
    resultsFormat: RESULTS_FORMAT,
    manifestFormat: MANIFEST_FORMAT,
    commands: commandTypes(commandSchema),
    quantities: ["power", "precursors", "fuelTemp", "coolantTemp", "iodine", "xenon", "energy", "reactivityTotal", "rods", "mode", "indicated", "tripped", "latched", "validityStatus"],
    units: "defined by the library manifest; this runner converts nothing",
    statuses: ["running", "completed", "failed"],
    notes: ["a trip is an event, not an end: the run continues and the trip stays visible in samples and events", "a manifest still saying running means the run was interrupted"],
  };
}

function option(args: string[], name: string): string | undefined {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
}

export async function main(argv: string[]): Promise<{ code: number; out: string }> {
  const emit = (code: number, value: unknown) => ({ code, out: JSON.stringify(value) + "\n" });
  const usage = (message: string) => emit(2, { ok: false, errors: [{ code: "E_USAGE", field: "", message }] });
  const [verb, ...args] = argv;
  try {
    if (verb === "describe") return emit(0, describe());
    if (verb === "validate") {
      if (!args[0]) return usage("validate needs a case file");
      const r = await validateCase(args[0]);
      return emit(r.ok ? 0 : 2, r);
    }
    if (verb === "run") {
      const out = option(args, "--out");
      if (!args[0] || args[0].startsWith("--") || !out) return usage("run needs a case file and --out <folder>");
      const r = await runCase({ casePath: args[0], outRoot: out, runId: option(args, "--run-id") });
      return emit(!r.ok ? 2 : r.status === "completed" ? 0 : 1, r);
    }
    if (verb === "replay") {
      if (!args[0]) return usage("replay needs a run folder");
      const r = await replayRun(args[0]);
      return emit(!r.ok ? 2 : r.identical ? 0 : 1, r);
    }
    return usage("verb must be describe, validate, run or replay");
  } catch (e) {
    return emit(1, { ok: false, errors: [{ code: "E_INTERNAL", field: "", message: e instanceof Error ? e.message : String(e) }] });
  }
}

// Run as a program when this file is the entry point of the bundle (not when a test imports it).
const entry = typeof process !== "undefined" ? process.argv[1] : undefined;
if (entry && /raft-headless\.m?js$/.test(entry.split(String.fromCharCode(92)).join("/"))) {
  main(process.argv.slice(2)).then(({ code, out }) => {
    process.stdout.write(out, () => process.exit(code));
  });
}
