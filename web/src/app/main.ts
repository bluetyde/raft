/**
 * App entry point. M3: the explorer on a bundled library. The runtime worker (src/runtime) and the
 * operator and instructor views are joined to it in later milestones.
 */

import "./app.css";
import { loadLibrary, LibraryError } from "../sim/library";
import { Explorer } from "../views/explorer/explorer";
import { modelFromLibrary } from "../views/explorer/model";
import { CATALOG, catalogReader } from "./catalog";

const app = document.getElementById("app")!;
const bar = document.createElement("header");
bar.className = "vr-bar";
const title = document.createElement("strong");
title.textContent = "Virtual Reactor · explorer";
const select = document.createElement("select");
for (const entry of CATALOG) select.append(new Option(entry.name, entry.name));
const status = document.createElement("span");
status.className = "vr-status";
bar.append(title, select, status);
const view = document.createElement("div");
view.className = "vr-view";
app.replaceChildren(bar, view);

const explorer = new Explorer(view);

async function show(name: string): Promise<void> {
  const entry = CATALOG.find((e) => e.name === name);
  if (!entry) return;
  status.textContent = `loading ${name}…`;
  try {
    const lib = await loadLibrary(catalogReader(entry));
    explorer.show(modelFromLibrary(lib));
    const s = explorer.stats!;
    status.textContent = `${lib.id} (${lib.status}): ${s.primitives} primitives, ${s.drawCalls} draw calls`;
    app.dataset["ready"] = "true";
    app.dataset["library"] = lib.id;
  } catch (err) {
    const issues = err instanceof LibraryError ? err.issues.map((i) => `${i.code} ${i.path}`).join("; ") : String(err);
    status.textContent = `could not load ${name}: ${issues}`;
  }
}

select.onchange = () => void show(select.value);
const initial = CATALOG.find((e) => e.name === "triga-jsi-242") ?? CATALOG[0];
if (initial) {
  select.value = initial.name;
  void show(initial.name);
}

// For end-to-end checks and the browser console.
(window as unknown as { vr: unknown }).vr = { explorer, show };
