/**
 * App entry point. The runtime worker (src/runtime) runs the chosen library.
 * - M5 operator panel (instruments only) and the M4 explorer (3D, truth read-out and controls).
 * - Layouts (docs/m5-operator-design.md section 4): split (default), realism (instruments only), explorer.
 * - M6 instructor view (docs/m6-instructor-design.md): the instructor layout shows the operator panel next to the instructor panel.
 */

import "./app.css";
import { RuntimeClient } from "../runtime/client";
import { loadLibrary, LibraryError } from "../sim/library";
import { Explorer } from "../views/explorer/explorer";
import { elementPowers, rodPositionsFrom } from "../views/explorer/live";
import { modelFromLibrary } from "../views/explorer/model";
import { InstructorPanel } from "../views/instructor/panel";
import { OperatorPanel } from "../views/operator/panel";
import { CATALOG, catalogFiles, catalogReader } from "./catalog";
import { Controls } from "./controls";

const app = document.getElementById("app")!;
const bar = document.createElement("header");
bar.className = "vr-bar";
const title = document.createElement("strong");
title.textContent = "Virtual Reactor";
const select = document.createElement("select");
for (const entry of CATALOG) select.append(new Option(entry.name, entry.name));
const status = document.createElement("span");
status.className = "vr-status";
type Layout = "split" | "realism" | "explorer" | "instructor";
const LAYOUTS: Layout[] = ["split", "realism", "explorer", "instructor"];
const layoutSelect = document.createElement("select");
for (const l of LAYOUTS) layoutSelect.append(new Option(l, l));
layoutSelect.dataset["op"] = "layout";
bar.append(title, select, layoutSelect, status);
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
let worker: Worker | null = null;
let client: RuntimeClient | null = null;
let controls: Controls | null = null;
let lastSnapshot: Record<string, any> | null = null;
let operator: OperatorPanel | null = null;
let instructor: InstructorPanel | null = null;
let current: string | null = null;

function storedLayout(): Layout {
  try {
    const v = localStorage.getItem("vr.layout");
    if (v && (LAYOUTS as string[]).includes(v)) return v as Layout;
  } catch {
    // storage can be blocked; the default is fine
  }
  return "split";
}

/**
 * Show a layout: split = operator panel large with a 3D inset; realism = instruments only; explorer = the M4 view;
 * instructor = the operator panel next to the instructor panel.
 */
function setLayout(l: Layout): void {
  app.dataset["layout"] = l;
  layoutSelect.value = l;
  opBox.hidden = l === "explorer";
  view.hidden = l === "realism" || l === "instructor";
  side.hidden = l !== "explorer";
  instBox.hidden = l !== "instructor";
  explorer.setCompact(l === "split");
  try {
    localStorage.setItem("vr.layout", l);
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

/** Load a library into a fresh runtime. `opts` sets the engine's initial state, seed and config (default: the library's reference state). */
async function show(name: string, opts: { init?: Record<string, any>; seed?: number; config?: Record<string, any> } = {}): Promise<void> {
  const entry = CATALOG.find((e) => e.name === name);
  if (!entry) return;
  status.textContent = `loading ${name}…`;
  current = name;
  delete app.dataset["ready"];
  worker?.terminate();
  worker = null;
  client = null;
  try {
    // The main thread reads the library for the geometry; the worker reads it again to run it.
    const lib = await loadLibrary(catalogReader(entry));
    const model = modelFromLibrary(lib);
    explorer.show(model);
    explorer.setLive(true);
    explorer.setOverlay("live");

    const w = new Worker(new URL("../runtime/worker.ts", import.meta.url), { type: "module" });
    const c = new RuntimeClient(w, "explorer");
    worker = w;
    client = c;
    const A = model.axialEdgesCm.length - 1;
    const rods = lib.rods.map((r) => ({ id: r.id, pulseCapable: r.pulseCapable }));
    const ctl = new Controls(c, { rods, modes: lib.modes });
    controls = ctl;
    side.replaceChildren(ctl.root);
    operator?.dispose();
    const op = new OperatorPanel(c, { instruments: lib.instruments, trips: lib.trips, interlocks: lib.interlocks, rods, modes: lib.modes });
    operator = op;
    opBox.replaceChildren(op.root);
    const inst = new InstructorPanel(
      c,
      { instruments: lib.instruments, pumps: lib.pumps },
      { restart: (outerDt) => void show(name, { ...opts, config: { ...opts.config, outerDt } }) },
    );
    instructor = inst;
    instBox.replaceChildren(inst.root);
    c.on("rewound", (m) => {
      op.onRewound();
      inst.onRewound(m.t);
    });
    c.on("clock", (m) => op.onClock(m));
    c.on("clock", (m) => inst.onClock(m));
    c.on("events", (m) => inst.onEvents(m.events));
    c.on("snapshot", (m) => {
      lastSnapshot = m.snapshot;
      op.onSnapshot(m);
      inst.onSnapshot(m);
      explorer.setRodPositions(rodPositionsFrom(m.snapshot));
      if (m.shape) explorer.setElementPowers(elementPowers(m.shape, model.elements, A, m.snapshot.truth.power));
      ctl.onSnapshot(m.snapshot);
    });
    c.on("clock", (m) => ctl.onClock(m));
    c.on("fault", (m) => (status.textContent = `runtime fault: ${m.message}`));
    const info = await c.load({ kind: "files", files: await catalogFiles(entry) }, opts);
    inst.setSession(info.outerDt);

    const s = explorer.stats!;
    status.textContent = `${lib.id} (${lib.status}): ${s.primitives} primitives, ${s.drawCalls} draw calls, outer step ${info.outerDt} s`;
    app.dataset["ready"] = "true";
    app.dataset["library"] = lib.id;
  } catch (err) {
    const issues = err instanceof LibraryError ? err.issues.map((i) => `${i.code} ${i.path}`).join("; ") : String(err);
    status.textContent = `could not load ${name}: ${issues}`;
  }
}

select.onchange = () => void show(select.value);
setLayout(storedLayout());
const initial = CATALOG.find((e) => e.name === "triga-jsi-242") ?? CATALOG[0];
if (initial) {
  select.value = initial.name;
  void show(initial.name);
}

// For end-to-end checks and the browser console.
(window as unknown as { vr: unknown }).vr = {
  explorer,
  show,
  get client() {
    return client;
  },
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
