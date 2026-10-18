/**
 * App entry point. The runtime worker (src/runtime) runs the chosen library.
 * - M5 operator panel (instruments only) and the M4 explorer (3D, truth read-out and controls).
 * - Layouts (docs/m5-operator-design.md section 4): split (default), realism (instruments only), explorer.
 * - M6 instructor view (docs/m6-instructor-design.md): the instructor layout shows the operator panel next to the instructor panel.
 * - Two windows (M6 slice S3): windows with the same `?session=<id>` share one SharedWorker. `?role=operator` makes an
 *   operator window: instruments only, and the worker refuses its time, rewind and fault requests.
 *
 * The page keeps one runtime connection for its whole life. Every window builds its panels when the worker says
 * a session was loaded (`loaded`, or the answer to `attach`), so all windows show the same library.
 */

import "./app.css";
import type { RuntimeClient } from "../runtime/client";
import type { FromWorker, LoadedInfo, Role } from "../runtime/protocol";
import { loadLibrary, LibraryError } from "../sim/library";
import { Explorer } from "../views/explorer/explorer";
import { elementPowers, rodPositionsFrom } from "../views/explorer/live";
import { modelFromLibrary } from "../views/explorer/model";
import { InstructorPanel } from "../views/instructor/panel";
import { OperatorPanel } from "../views/operator/panel";
import { CATALOG, catalogFiles, catalogReader } from "./catalog";
import { scenarioById, scenariosFor } from "./scenarios";
import { connect, windowParams, windowUrl } from "./connection";
import { Controls } from "./controls";

type Layout = "split" | "realism" | "explorer" | "instructor";
const LAYOUTS_FOR: Record<Role, Layout[]> = {
  full: ["split", "realism", "explorer", "instructor"],
  instructor: ["instructor", "explorer"],
  operator: ["split", "realism"],
};

const params = windowParams(location.search);
if (params.fresh) {
  // keep the session id in the URL, so a reload (or a second window) finds the same session
  history.replaceState(null, "", windowUrl(location.href, params.session, params.role));
}
const conn = connect(params, "explorer");
const client: RuntimeClient = conn.client;
const role: Role = conn.role;
const layouts = LAYOUTS_FOR[role];

const app = document.getElementById("app")!;
app.dataset["role"] = role;
app.dataset["shared"] = String(conn.shared);
const bar = document.createElement("header");
bar.className = "vr-bar";
const title = document.createElement("strong");
title.textContent = "RAFT";
const select = document.createElement("select");
for (const entry of CATALOG) select.append(new Option(entry.name, entry.name));
select.disabled = role === "operator"; // an operator window cannot load (the worker refuses it too)
const layoutSelect = document.createElement("select");
for (const l of layouts) layoutSelect.append(new Option(l, l));
layoutSelect.dataset["op"] = "layout";
const windowText = document.createElement("span");
windowText.className = "vr-note";
windowText.dataset["op"] = "window";
windowText.textContent = conn.shared ? `${role} window, session ${conn.session}` : "one window (this browser has no SharedWorker)";
const openOperator = document.createElement("button");
openOperator.textContent = "open operator window";
openOperator.dataset["op"] = "open-operator";
openOperator.hidden = !conn.shared || role === "operator";
openOperator.onclick = () => window.open(windowUrl(location.href, conn.session, "operator"), "_blank");
const status = document.createElement("span");
status.className = "vr-status";
bar.append(title, select, layoutSelect, windowText, openOperator, status);
const main = document.createElement("div");
main.className = "vr-main";
const opBox = document.createElement("div");
opBox.className = "vr-opbox";
const view = document.createElement("div");
view.className = "vr-view";
const side = document.createElement("aside");
side.className = "vr-side";
const instBox = document.createElement("div");
instBox.className = "vr-instbox";
main.append(opBox, view, side, instBox);
app.replaceChildren(bar, main);

const explorer = new Explorer(view);
let controls: Controls | null = null;
let operator: OperatorPanel | null = null;
let instructor: InstructorPanel | null = null;
let current: string | null = null;
let lastSnapshot: Record<string, any> | null = null;
let elementsOf: ((m: Extract<FromWorker, { kind: "snapshot" }>) => void) | null = null;

// The latest state messages, so panels built after they arrived can show them at once.
const latest: {
  snapshot?: Extract<FromWorker, { kind: "snapshot" }>;
  shaped?: Extract<FromWorker, { kind: "snapshot" }>;
  clock?: Extract<FromWorker, { kind: "clock" }>;
  timeline?: Extract<FromWorker, { kind: "timeline" }>;
  scenario?: Extract<FromWorker, { kind: "scenario" }>;
} = {};

function storedLayout(): Layout {
  try {
    const v = localStorage.getItem(`vr.layout.${role}`);
    if (v && (layouts as string[]).includes(v)) return v as Layout;
  } catch {
    // storage can be blocked; the default is fine
  }
  return layouts[0]!;
}

/**
 * Show a layout: split = operator panel large with a 3D inset; realism = instruments only; explorer = the M4 view;
 * instructor = the operator panel next to the instructor panel.
 */
function setLayout(l: Layout): void {
  if (!layouts.includes(l)) return;
  app.dataset["layout"] = l;
  layoutSelect.value = l;
  opBox.hidden = l === "explorer";
  view.hidden = l === "realism" || l === "instructor";
  side.hidden = l !== "explorer";
  instBox.hidden = l !== "instructor";
  explorer.setCompact(l === "split");
  try {
    localStorage.setItem(`vr.layout.${role}`, l);
  } catch {
    // a convenience only
  }
}
layoutSelect.onchange = () => setLayout(layoutSelect.value as Layout);
// Tab swaps which one is large in the split layout.
window.addEventListener("keydown", (e) => {
  const t = e.target as HTMLElement | null;
  if (e.key !== "Tab" || app.dataset["layout"] !== "split" || (t && ["INPUT", "SELECT", "BUTTON"].includes(t.tagName))) return;
  e.preventDefault();
  main.classList.toggle("vr-swap");
});

// ---- messages from the worker, to whichever panels exist now ----

client.on("snapshot", (m) => {
  latest.snapshot = m;
  if (m.shape) latest.shaped = m;
  lastSnapshot = m.snapshot;
  operator?.onSnapshot(m);
  instructor?.onSnapshot(m);
  controls?.onSnapshot(m.snapshot);
  explorer.setRodPositions(rodPositionsFrom(m.snapshot));
  elementsOf?.(m);
});
client.on("clock", (m) => {
  latest.clock = m;
  operator?.onClock(m);
  instructor?.onClock(m);
  controls?.onClock(m);
});
client.on("timeline", (m) => {
  latest.timeline = m;
  instructor?.onTimeline(m);
});
client.on("scenario", (m) => {
  latest.scenario = m;
  instructor?.onScenario(m);
  operator?.onScenario(m.scenario);
});
client.on("rewound", (m) => {
  operator?.onRewound(m.replaced);
  instructor?.onRewound(m.t, m.outerDt);
});
client.on("loaded", (m) => {
  // a new session: state from the old one must not reach the new panels (the new state follows this message)
  delete latest.snapshot;
  delete latest.shaped;
  delete latest.clock;
  delete latest.timeline;
  delete latest.scenario;
  elementsOf = null; // the old model cannot take the new library's power shape
  const { kind: _k, protocol: _p, ...info } = m;
  void adopt(info);
});
client.on("fault", (m) => (status.textContent = `runtime fault: ${m.message}`));

let adopting: Promise<void> = Promise.resolve();

/** Build this window's panels for the session the worker has loaded. Every window does this, whoever loaded it. */
function adopt(info: LoadedInfo): Promise<void> {
  adopting = adopting.then(() => build(info));
  return adopting;
}

async function build(info: LoadedInfo): Promise<void> {
  const entry = CATALOG.find((e) => e.name === info.libraryId);
  if (!entry) {
    status.textContent = `the session runs ${info.libraryId}, which this app does not ship`;
    return;
  }
  delete app.dataset["ready"];
  current = entry.name;
  select.value = entry.name;
  try {
    // The main thread reads the library for the geometry and the panels; the worker runs its own copy.
    const lib = await loadLibrary(catalogReader(entry));
    const model = modelFromLibrary(lib);
    explorer.show(model);
    explorer.setLive(true);
    explorer.setOverlay("live");
    const A = model.axialEdgesCm.length - 1;
    let lastShape: ArrayLike<number> | null = null;
    elementsOf = (m) => {
      if (m.shape) lastShape = m.shape;
      if (lastShape) explorer.setElementPowers(elementPowers(lastShape, model.elements, A, m.snapshot.truth.power));
    };
    const rods = lib.rods.map((r) => ({ id: r.id, pulseCapable: r.pulseCapable }));
    controls = new Controls(client, { rods, modes: lib.modes });
    side.replaceChildren(controls.root);
    operator?.dispose();
    operator = new OperatorPanel(
      client,
      {
        instruments: lib.instruments,
        trips: lib.trips,
        interlocks: lib.interlocks,
        rods,
        modes: lib.modes,
        ...(lib.hasBoron ? { boron: { range: lib.boronRange, maxRatePpmPerS: lib.boronMaxRate } } : {}),
      },
      { timeControls: role !== "operator" },
    );
    opBox.replaceChildren(operator.root);
    instructor?.dispose();
    instructor = new InstructorPanel(
      client,
      { instruments: lib.instruments, pumps: lib.pumps },
      {
        restart: (outerDt) => void show(entry.name, { config: { ...info.pins["config"], outerDt } }),
        files: () => catalogFiles(entry),
        libraryId: lib.id,
        scenarios: scenariosFor(lib.id),
        startScenario: (sc) => void show(entry.name, { scenario: sc }),
        findScenario: scenarioById,
      },
    );
    instructor.setSession(info.outerDt);
    instBox.replaceChildren(instructor.root);
    // state that arrived while this was building
    if (latest.shaped) elementsOf(latest.shaped);
    if (latest.snapshot) {
      operator.onSnapshot(latest.snapshot);
      instructor.onSnapshot(latest.snapshot);
      controls.onSnapshot(latest.snapshot.snapshot);
      explorer.setRodPositions(rodPositionsFrom(latest.snapshot.snapshot));
    }
    if (latest.clock) {
      operator.onClock(latest.clock);
      instructor.onClock(latest.clock);
      controls.onClock(latest.clock);
    }
    if (latest.timeline) instructor.onTimeline(latest.timeline);
    if (latest.scenario) {
      instructor.onScenario(latest.scenario);
      operator.onScenario(latest.scenario.scenario);
    }

    const s = explorer.stats!;
    status.textContent = `${lib.id} (${lib.status}): ${s.primitives} primitives, ${s.drawCalls} draw calls, outer step ${info.outerDt} s`;
    app.dataset["ready"] = "true";
    app.dataset["library"] = lib.id;
  } catch (err) {
    const issues = err instanceof LibraryError ? err.issues.map((i) => `${i.code} ${i.path}`).join("; ") : String(err);
    status.textContent = `could not load ${entry.name}: ${issues}`;
  }
}

/** Every rod fully in, from the library's manifest: a shut-down start that is subcritical for any library. A library whose
 * reference state is its measured critical state (the M2 OpenMC libraries) has no source equilibrium there
 * (E_INIT_NO_EQUILIBRIUM); the older libraries' reference rods are already all in, so for them this is the reference state. */
function shutdownInit(files: Record<string, ArrayBuffer>): Record<string, any> | undefined {
  const manifest = files["manifest.json"];
  if (!manifest) return undefined;
  const rods = (JSON.parse(new TextDecoder().decode(manifest)) as { reactivity?: { rods?: { id: string }[] } }).reactivity?.rods;
  return rods ? { rods: Object.fromEntries(rods.map((r) => [r.id, 0])) } : undefined;
}

/** Load a library as a new session. `opts` sets the engine's initial state, seed and config (default: all rods in, see
 * shutdownInit; a scenario brings its own). */
async function show(
  name: string,
  opts: { init?: Record<string, any>; seed?: number; config?: Record<string, any>; scenario?: unknown } = {},
): Promise<void> {
  const entry = CATALOG.find((e) => e.name === name);
  if (!entry) return;
  status.textContent = `loading ${name}…`;
  delete app.dataset["ready"];
  try {
    const files = await catalogFiles(entry);
    const init = opts.init ?? (opts.scenario === undefined ? shutdownInit(files) : undefined);
    await client.load({ kind: "files", files }, init === undefined ? opts : { ...opts, init });
    await adopting; // the `loaded` message came before the load's answer, so its build is queued
  } catch (err) {
    status.textContent = `could not load ${name}: ${String(err)}`;
    if (current) app.dataset["ready"] = "true"; // the worker keeps the previous session
  }
}

select.onchange = () => void show(select.value);
setLayout(storedLayout());

// Attach first: if this session already runs (another window, or a reload), show it; otherwise load the default library.
void (async () => {
  const { loaded } = await client.attach(role);
  if (loaded) return adopt(loaded);
  if (role === "operator") {
    status.textContent = "waiting for the instructor window to load a library";
    return;
  }
  const initial = CATALOG.find((e) => e.name === "triga-jsi-242-openmc") ?? CATALOG[0];
  if (initial) return show(initial.name);
})();

// For end-to-end checks and the browser console.
(window as unknown as { vr: unknown }).vr = {
  explorer,
  show,
  client,
  role,
  shared: conn.shared,
  session: conn.session,
  get controls() {
    return controls;
  },
  get snapshot() {
    return lastSnapshot;
  },
  get operator() {
    return operator;
  },
  get instructor() {
    return instructor;
  },
  get library() {
    return current;
  },
  setLayout,
};
