/**
 * Explorer view, M3 (static): draws a library's primitives with an orbit or noclip camera,
 * a cutaway plane with caps, and click-to-inspect. Rods can be moved with view-only sliders here;
 * in M4 the positions come from runtime snapshots instead.
 */

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { elementShares, pick, rodOffsetCm, type HalfSpace, type PickHit, type Vec3, type ViewerModel } from "./model";
import { bindNoclip, NoclipController } from "./noclip";
import { CoreScene, fromScene, toScene } from "./scene";
import { powerColors } from "./live";
import { styleFor, viridis } from "./styles";

export type CutAxis = "x" | "y" | "z";
export interface Cutaway {
  axis: CutAxis;
  /** Library coordinate of the plane, cm. */
  position: number;
  /** false: remove the part above `position` (keep coordinate <= position); true: keep >= position. */
  flip: boolean;
}

/** The cutaway as a kept half-space in library coordinates. */
export function cutawayHalfSpace(c: Cutaway): HalfSpace {
  const e: Vec3 = c.axis === "x" ? [1, 0, 0] : c.axis === "y" ? [0, 1, 0] : [0, 0, 1];
  return c.flip ? { normal: e, constant: -c.position } : { normal: [-e[0], -e[1], -e[2]], constant: c.position };
}

export interface Inspected {
  hit: PickHit;
  lines: [string, string][];
}

export type Overlay = "materials" | "power" | "live";

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> & { className?: string } = {},
  children: (Node | string)[] = [],
): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  Object.assign(e, props);
  for (const c of children) e.append(c);
  return e;
}

function fmt(x: number, digits = 3): string {
  return Number.isFinite(x) ? x.toFixed(digits) : String(x);
}

export class Explorer {
  readonly renderer: THREE.WebGLRenderer;
  readonly camera = new THREE.PerspectiveCamera(55, 1, 0.5, 20000);
  private readonly scene = new THREE.Scene();
  private readonly orbit: OrbitControls;
  private readonly noclip: NoclipController;
  private unbindNoclip: (() => void) | null = null;
  private core: CoreScene | null = null;
  private highlight: THREE.Box3Helper | null = null;
  private cutaway: Cutaway | null = null;
  private overlay: Overlay = "materials";
  private livePowers: Map<string, number> | null = null;
  private live = false;
  private readonly overlaySelect: HTMLSelectElement;
  private dirty = true;
  private last = performance.now();
  private raf = 0;
  private readonly canvas: HTMLCanvasElement;
  private readonly panel: HTMLElement;
  private readonly inspectBox: HTMLElement;
  private readonly rodBox: HTMLElement;
  private readonly cutSlider: HTMLInputElement;
  private readonly modeButton: HTMLButtonElement;
  private readonly crosshair: HTMLElement;
  mode: "orbit" | "noclip" = "orbit";
  lastInspected: Inspected | null = null;

  constructor(private readonly container: HTMLElement) {
    container.classList.add("vr-explorer");
    this.renderer = new THREE.WebGLRenderer({ antialias: true, stencil: true, preserveDrawingBuffer: true });
    this.renderer.localClippingEnabled = true;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x0b1a2a);
    this.canvas = this.renderer.domElement;
    this.canvas.tabIndex = 0;
    container.append(this.canvas);

    this.scene.add(new THREE.HemisphereLight(0xdfe8f0, 0x202830, 1.2));
    const head = new THREE.DirectionalLight(0xffffff, 1.4); // a headlight, so noclip views inside the core are lit
    head.position.set(0.3, 0.5, 1);
    this.camera.add(head);
    this.scene.add(this.camera);

    this.orbit = new OrbitControls(this.camera, this.canvas);
    this.orbit.addEventListener("change", () => (this.dirty = true));
    this.noclip = new NoclipController(this.camera);

    this.modeButton = el("button", { textContent: "Noclip (N)", onclick: () => this.setMode(this.mode === "orbit" ? "noclip" : "orbit") });
    this.cutSlider = el("input", { type: "range", min: "-1", max: "1", step: "0.1", value: "0", disabled: true });
    const axis = el("select", {}, ["off", "x", "y", "z"].map((a) => el("option", { value: a, textContent: a === "off" ? "no cutaway" : `cut ${a}` })));
    const flip = el("input", { type: "checkbox" });
    const onCut = () => {
      if (axis.value === "off") {
        this.cutSlider.disabled = true;
        this.setCutaway(null);
      } else {
        this.cutSlider.disabled = false;
        this.setCutaway({ axis: axis.value as CutAxis, position: Number(this.cutSlider.value), flip: flip.checked });
      }
    };
    axis.onchange = onCut;
    this.cutSlider.oninput = onCut;
    flip.onchange = onCut;
    const overlay = el("select", {}, [
      el("option", { value: "materials", textContent: "materials" }),
      el("option", { value: "power", textContent: "reference power share" }),
      el("option", { value: "live", textContent: "live power (M4)" }),
    ]);
    this.overlaySelect = overlay;
    overlay.onchange = () => this.setOverlay(overlay.value as Overlay);
    const presets = el("span", {}, [
      el("button", { textContent: "Top (1)", onclick: () => this.preset(1) }),
      el("button", { textContent: "Side (2)", onclick: () => this.preset(2) }),
      el("button", { textContent: "Diver (3)", onclick: () => this.preset(3) }),
    ]);
    this.rodBox = el("div", { className: "vr-rods" });
    this.inspectBox = el("div", { className: "vr-inspect", textContent: "Click an element or rod to inspect it." });
    this.panel = el("div", { className: "vr-panel" }, [
      el("div", { className: "vr-row" }, [this.modeButton, presets]),
      el("div", { className: "vr-row" }, [axis, this.cutSlider, el("label", {}, [flip, " keep other side"])]),
      el("div", { className: "vr-row" }, [el("label", {}, ["colour: ", overlay])]),
      this.rodBox,
      this.inspectBox,
      el("div", {
        className: "vr-help",
        textContent: "Orbit: drag, scroll, right-drag. Noclip: click to look, WASD move, Q/E down/up, Shift fast, Esc release; click picks the centre.",
      }),
    ]);
    this.crosshair = el("div", { className: "vr-crosshair", textContent: "+" });
    container.append(this.panel, this.crosshair);

    this.bindPointer();
    window.addEventListener("keydown", this.onKey);
    new ResizeObserver(() => this.resize()).observe(container);
    this.resize();
    this.loop();
  }

  show(model: ViewerModel): void {
    if (this.core) {
      this.scene.remove(this.core.root);
      this.core.dispose();
    }
    this.core = new CoreScene(model);
    this.scene.add(this.core.root);
    const r = this.core.radius;
    this.cutSlider.min = String(-Math.ceil(r));
    this.cutSlider.max = String(Math.ceil(r));
    this.cutSlider.value = "0";
    this.buildRodSliders(model);
    this.setOverlay(this.overlay);
    if (this.cutaway) this.setCutaway(this.cutaway);
    this.select(null);
    this.inspectBox.textContent = "Click an element or rod to inspect it.";
    this.preset(3);
  }

  get stats(): { primitives: number; drawCalls: number; triangles: number } | null {
    const c = this.core;
    return c ? { primitives: c.model.primitives.length, drawCalls: c.drawCalls, triangles: c.triangles } : null;
  }

  setRodPositions(rods: Record<string, number>): void {
    if (!this.core) return;
    this.core.setRodPositions(rods);
    for (const input of this.rodBox.querySelectorAll("input")) {
      const id = input.dataset["rod"]!;
      if (Object.hasOwn(rods, id)) input.value = String(rods[id]);
    }
    const hit = this.lastInspected?.hit;
    if (hit && this.core.model.primitives[hit.index]!.rod !== undefined) this.select(hit); // the box follows a moved rod
    this.dirty = true;
  }

  setCutaway(c: Cutaway | null): void {
    this.cutaway = c;
    this.core?.setCutaway(c ? cutawayHalfSpace(c) : null);
    this.dirty = true;
  }

  setOverlay(o: Overlay): void {
    this.overlay = o;
    this.overlaySelect.value = o;
    if (!this.core) return;
    if (o === "live") {
      this.core.setElementColors(this.livePowers ? powerColors(this.livePowers) : null);
    } else if (o === "power") {
      const shares = elementShares(this.core.model);
      const max = Math.max(...shares.values());
      const colors = new Map<string, [number, number, number]>();
      for (const [id, s] of shares) colors.set(id, viridis(max > 0 ? s / max : 0));
      this.core.setElementColors(colors);
    } else {
      this.core.setElementColors(null);
    }
    this.dirty = true;
  }

  /** Live element powers (W) from the runtime; drawn when the overlay is "live". */
  setElementPowers(powers: Map<string, number> | null): void {
    this.livePowers = powers;
    if (this.overlay === "live") this.setOverlay("live");
  }

  /** Live mode (M4): rods follow the simulation, so the sliders become read-outs. */
  setLive(on: boolean): void {
    this.live = on;
    if (this.core) this.buildRodSliders(this.core.model);
  }

  /** Compact mode (an inset next to the operator panel): the explorer's own panel is hidden. */
  setCompact(on: boolean): void {
    this.panel.hidden = on;
    this.dirty = true;
  }

  get rodPositions(): Record<string, number> {
    return this.core ? this.core.rodPositions : {};
  }

  setMode(mode: "orbit" | "noclip"): void {
    if (mode === this.mode) return;
    this.mode = mode;
    if (mode === "noclip") {
      this.orbit.enabled = false;
      this.noclip.speed = Math.max(10, (this.core?.radius ?? 50) * 0.8);
      this.noclip.syncFromCamera();
      this.unbindNoclip = bindNoclip(this.noclip, this.canvas, () => (this.dirty = true));
      this.modeButton.textContent = "Orbit (N)";
    } else {
      this.unbindNoclip?.();
      this.unbindNoclip = null;
      if (document.pointerLockElement === this.canvas) document.exitPointerLock();
      // Orbit around the point in front of the camera.
      const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(this.camera.quaternion);
      this.orbit.target.copy(this.camera.position).addScaledVector(fwd, this.core?.radius ?? 50);
      this.orbit.enabled = true;
      this.orbit.update();
      this.modeButton.textContent = "Noclip (N)";
    }
    this.crosshair.style.display = mode === "noclip" ? "block" : "none";
    this.dirty = true;
  }

  /** 1: top, 2: side (looking at the cut face when there is a cutaway), 3: diver's view from above the pool. */
  preset(n: 1 | 2 | 3): void {
    const r = this.core?.radius ?? 50;
    let pos: THREE.Vector3;
    if (n === 1) pos = new THREE.Vector3(0, 3.2 * r, 0.001);
    else if (n === 3) pos = new THREE.Vector3(1.6 * r, 1.9 * r, 1.6 * r);
    else if (this.cutaway && this.cutaway.axis !== "z") {
      // from the removed side, straight at the cut
      const h = cutawayHalfSpace(this.cutaway);
      pos = toScene([-h.normal[0], -h.normal[1], -h.normal[2]]).multiplyScalar(3 * r);
      pos.y += 0.2 * r;
    } else pos = new THREE.Vector3(0, 0.2 * r, 3 * r);
    this.camera.position.copy(pos);
    this.orbit.target.set(0, 0, 0);
    this.camera.lookAt(0, 0, 0);
    this.orbit.update();
    if (this.mode === "noclip") this.noclip.syncFromCamera();
    this.dirty = true;
  }

  /** Pick at canvas pixel coordinates (or the centre in noclip), show it in the panel, and return it. */
  pickAt(px: number, py: number): Inspected | null {
    const core = this.core;
    if (!core) return null;
    const rect = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2((px / rect.width) * 2 - 1, -(py / rect.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, this.camera);
    const hit = pick(core.model, fromScene(ray.ray.origin), fromScene(ray.ray.direction), {
      rods: core.rodPositions,
      cut: this.cutaway ? cutawayHalfSpace(this.cutaway) : null,
      pickable: (p) => styleFor(p.material).pickable,
    });
    return this.select(hit);
  }

  private select(hit: PickHit | null): Inspected | null {
    const core = this.core;
    if (this.highlight) {
      this.scene.remove(this.highlight);
      this.highlight.dispose();
      this.highlight = null;
    }
    if (!core || !hit) {
      this.lastInspected = null;
      this.inspectBox.textContent = hit === null && core ? "Nothing pickable there." : "";
      this.dirty = true;
      return null;
    }
    const p = core.model.primitives[hit.index]!;
    this.highlight = new THREE.Box3Helper(core.boundsOf(hit.index).expandByScalar(0.15), 0xffd84a);
    this.scene.add(this.highlight);
    const lines: [string, string][] = [
      ["primitive", `#${p.index} ${p.type}`],
      ["material", p.material],
    ];
    if (p.type === "annulus") lines.push(["radius", `${fmt(p.rInner)}–${fmt(p.radius)} cm`]);
    else if (p.type === "cylinder") lines.push(["radius", `${fmt(p.radius)} cm`]);
    if (p.type !== "box") lines.push(["height", `${fmt(p.height)} cm`]);
    else lines.push(["size", `${p.size.map((v) => fmt(v)).join(" × ")} cm`]);
    lines.push(["centre", `(${p.center.map((v) => fmt(v, 2)).join(", ")}) cm`]);
    if (p.element !== undefined) {
      const m = core.model;
      const e = m.elements.indexOf(p.element);
      const A = m.axialEdgesCm.length - 1;
      const bins = m.baseShape.slice(e * A, (e + 1) * A);
      const share = bins.reduce((a, b) => a + b, 0);
      const peak = bins.indexOf(Math.max(...bins));
      lines.push(["element", p.element]);
      lines.push(["power share (reference)", `${fmt(100 * share, 2)} % of the core`]);
      lines.push(["peak axial bin", `${peak + 1} of ${A} (${fmt(m.axialEdgesCm[peak]!, 1)} to ${fmt(m.axialEdgesCm[peak + 1]!, 1)} cm)`]);
    }
    if (p.rod !== undefined) {
      const x = core.rodPositions[p.rod] ?? 0;
      lines.push(["rod", p.rod]);
      lines.push(["position", `${fmt(x)} withdrawn (${fmt(rodOffsetCm(p, core.model, core.rodPositions), 2)} cm up)`]);
    }
    lines.push(["hit point", `(${hit.point.map((v) => fmt(v, 2)).join(", ")}) cm${hit.onCut ? ", on the cut face" : ""}`]);
    this.inspectBox.replaceChildren(
      el("table", {}, lines.map(([k, v]) => el("tr", {}, [el("th", { textContent: k }), el("td", { textContent: v })]))),
    );
    this.lastInspected = { hit, lines };
    this.dirty = true;
    return this.lastInspected;
  }

  private buildRodSliders(model: ViewerModel): void {
    const rows = Object.keys(model.rodTravelCm).map((id) => {
      const input = el("input", { type: "range", min: "0", max: "1", step: "0.01", value: String(model.refRods[id] ?? 0) });
      input.dataset["rod"] = id;
      input.oninput = () => this.setRodPositions({ [id]: Number(input.value) });
      input.disabled = this.live;
      return el("label", { className: "vr-rod" }, [`${id} `, input]);
    });
    const note = this.live ? "Rods (following the simulation; drive them from the controls):" : "Rods (view only):";
    this.rodBox.replaceChildren(el("div", { className: "vr-note", textContent: note }), ...rows);
  }

  private bindPointer(): void {
    let downAt: [number, number] | null = null;
    this.canvas.addEventListener("pointerdown", (e) => (downAt = [e.clientX, e.clientY]));
    this.canvas.addEventListener("pointerup", (e) => {
      const d = downAt;
      downAt = null;
      if (!d || Math.hypot(e.clientX - d[0], e.clientY - d[1]) > 4 || e.button !== 0) return; // a drag, not a click
      if (this.mode === "noclip") {
        if (document.pointerLockElement !== this.canvas) {
          void this.canvas.requestPointerLock();
          return;
        }
        const r = this.canvas.getBoundingClientRect();
        this.pickAt(r.width / 2, r.height / 2);
      } else {
        const r = this.canvas.getBoundingClientRect();
        this.pickAt(e.clientX - r.left, e.clientY - r.top);
      }
    });
  }

  private onKey = (e: KeyboardEvent) => {
    const t = e.target as HTMLElement | null;
    if (t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA")) return;
    if (e.code === "KeyN") this.setMode(this.mode === "orbit" ? "noclip" : "orbit");
    else if (e.code === "Digit1") this.preset(1);
    else if (e.code === "Digit2") this.preset(2);
    else if (e.code === "Digit3") this.preset(3);
  };

  private resize(): void {
    const w = Math.max(1, this.container.clientWidth);
    const h = Math.max(1, this.container.clientHeight);
    this.renderer.setSize(w, h, false);
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.dirty = true;
  }

  /** Render only when something changed, or while the noclip camera moves (plan 04). */
  private loop = () => {
    this.raf = requestAnimationFrame(this.loop);
    const now = performance.now();
    const dt = Math.min(0.1, (now - this.last) / 1000);
    this.last = now;
    if (this.mode === "noclip" && this.noclip.moving) {
      this.noclip.update(dt);
      this.dirty = true;
    }
    if (!this.dirty) return;
    this.dirty = false;
    this.renderer.render(this.scene, this.camera);
  };

  /** Render now (tests and screenshots). */
  renderNow(): void {
    this.renderer.render(this.scene, this.camera);
  }

  dispose(): void {
    cancelAnimationFrame(this.raf);
    window.removeEventListener("keydown", this.onKey);
    this.unbindNoclip?.();
    this.orbit.dispose();
    this.core?.dispose();
    this.renderer.dispose();
    this.container.replaceChildren();
  }
}
