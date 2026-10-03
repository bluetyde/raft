/**
 * Headless case file (format "raft-headless-case", version 1): everything a run needs, as data.
 * The shape is the engine golden-vector scenario (schema/engine-vectors) plus a library path, so a vector
 * is also a valid case. Validation here never throws: it returns typed errors {code, field, message}.
 */

export const CASE_FORMAT = "raft-headless-case";
export const CASE_VERSION = 1;
export const MAX_STEPS = 2_000_000;
export const MAX_SCRIPT = 10_000;

export interface CaseIssue {
  code: string;
  field: string;
  message: string;
}

export interface ScriptItem {
  step: number;
  cmd: Record<string, unknown>;
  clientId: string;
}

export interface HeadlessCase {
  library: string;
  seed: number;
  init: Record<string, unknown>;
  config: Record<string, unknown>;
  steps: number;
  sampleEvery: number;
  script: ScriptItem[];
}

const KNOWN = new Set(["format", "version", "library", "seed", "init", "config", "steps", "sampleEvery", "script", "name", "description"]);

function isObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function isInt(v: unknown, min: number, max: number): v is number {
  return typeof v === "number" && Number.isInteger(v) && v >= min && v <= max;
}

/** A library folder given relative to the case file: no absolute path, drive letter, backslash, empty or `..` segment. */
export function libraryPathProblem(p: string): string | null {
  if (p.length === 0 || p.length > 300) return "must be 1 to 300 characters";
  if (p.startsWith("/") || /^[A-Za-z]:/.test(p) || p.includes(String.fromCharCode(92)) || p.includes(String.fromCharCode(0))) {
    return "must be a relative path with forward slashes";
  }
  if (p.split("/").some((s) => s === ".." || s === "")) return "must not contain empty or .. segments";
  return null;
}

export function parseCase(raw: unknown): { ok: true; value: HeadlessCase } | { ok: false; errors: CaseIssue[] } {
  const errors: CaseIssue[] = [];
  const bad = (field: string, message: string) => errors.push({ code: "E_CASE_INVALID", field, message });
  if (!isObject(raw)) return { ok: false, errors: [{ code: "E_CASE_INVALID", field: "", message: "the case must be a JSON object" }] };
  if (raw.format !== CASE_FORMAT) {
    return { ok: false, errors: [{ code: "E_CASE_VERSION", field: "/format", message: `format must be "${CASE_FORMAT}"` }] };
  }
  if (raw.version !== CASE_VERSION) {
    return { ok: false, errors: [{ code: "E_CASE_VERSION", field: "/version", message: `unsupported case version (this runner reads ${CASE_VERSION})` }] };
  }
  for (const k of Object.keys(raw)) if (!KNOWN.has(k)) bad(`/${k}`, "unknown field");

  const library = raw.library;
  if (typeof library !== "string") bad("/library", "must be a string");
  else {
    const problem = libraryPathProblem(library);
    if (problem) errors.push({ code: "E_PATH_INVALID", field: "/library", message: problem });
  }
  if (!isInt(raw.seed, 0, Number.MAX_SAFE_INTEGER)) bad("/seed", "must be an integer from 0 to 2^53-1");
  const init = raw.init === undefined ? {} : raw.init;
  if (!isObject(init)) bad("/init", "must be an object");
  const config = raw.config === undefined ? {} : raw.config;
  if (!isObject(config)) bad("/config", "must be an object");
  if (!isInt(raw.steps, 1, MAX_STEPS)) bad("/steps", `must be an integer from 1 to ${MAX_STEPS}`);
  if (!isInt(raw.sampleEvery, 1, MAX_STEPS)) bad("/sampleEvery", `must be an integer from 1 to ${MAX_STEPS}`);
  else if (isInt(raw.steps, 1, MAX_STEPS) && raw.sampleEvery > raw.steps) bad("/sampleEvery", "must not exceed steps");

  const script: ScriptItem[] = [];
  if (!Array.isArray(raw.script)) bad("/script", "must be an array");
  else if (raw.script.length > MAX_SCRIPT) bad("/script", `at most ${MAX_SCRIPT} entries`);
  else {
    raw.script.forEach((item: unknown, i: number) => {
      if (!isObject(item)) return bad(`/script/${i}`, "must be an object");
      for (const k of Object.keys(item)) if (!["step", "cmd", "clientId"].includes(k)) bad(`/script/${i}/${k}`, "unknown field");
      if (!isInt(item.step, 0, MAX_STEPS)) bad(`/script/${i}/step`, "must be an integer step index");
      else if (isInt(raw.steps, 1, MAX_STEPS) && item.step >= raw.steps) bad(`/script/${i}/step`, "must be before the last step (steps)");
      if (!isObject(item.cmd) || typeof item.cmd.type !== "string") bad(`/script/${i}/cmd`, "must be an object with a string type");
      const clientId = item.clientId === undefined ? "headless" : item.clientId;
      if (typeof clientId !== "string" || clientId.length === 0 || clientId.length > 80) bad(`/script/${i}/clientId`, "must be a string of 1 to 80 characters");
      if (errors.length === 0) script.push({ step: item.step as number, cmd: item.cmd as Record<string, unknown>, clientId: clientId as string });
    });
  }
  if (errors.length > 0) return { ok: false, errors };
  return {
    ok: true,
    value: {
      library: library as string,
      seed: raw.seed as number,
      init: init as Record<string, unknown>,
      config: config as Record<string, unknown>,
      steps: raw.steps as number,
      sampleEvery: raw.sampleEvery as number,
      script,
    },
  };
}
