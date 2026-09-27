/**
 * Builds a three.js scene from the viewer model's primitives (docs/m3-renderer-decision.md).
 *
 * - Library coordinates are cm, z up. three.js is y up, so a library point (x, y, z) is drawn at (x, z, -y).
 *   1 scene unit = 1 cm.
 * - Equal primitives (same type, size and material) share one InstancedMesh: one draw call per group.
 * - The cutaway is one clipping plane. Cut solids get caps drawn with the stencil buffer, per material.
 * - Picking does not use this scene: it is exact, on the analytic primitives (model.ts `pick`).
 */

import * as THREE from "three";
import { rodOffsetCm, type HalfSpace, type PrimitiveInfo, type Vec3, type ViewerModel } from "./model";
import { styleFor } from "./styles";

export function toScene(p: Vec3): THREE.Vector3 {
  return new THREE.Vector3(p[0], p[2], -p[1]);
}

export function fromScene(v: THREE.Vector3): Vec3 {
  return [v.x, -v.z, v.y];
}

/** The library half-space as a three.js clipping plane (same convention: n·p + c >= 0 is kept). */
export function planeFor(h: HalfSpace): THREE.Plane {
  return new THREE.Plane(toScene(h.normal), h.constant);
}

const SEGMENTS = 48;

function geometryFor(p: PrimitiveInfo): THREE.BufferGeometry {
  if (p.type === "cylinder") return new THREE.CylinderGeometry(p.radius, p.radius, p.height, SEGMENTS);
  if (p.type === "box") return new THREE.BoxGeometry(p.size[0], p.size[2], p.size[1]);
  // Annulus: a closed ring solid, lathed around the y axis. The profile runs counter-clockwise in (r, y),
  // so the faces point outwards; corner points repeat so the edges stay sharp.
  const h = p.height / 2;
  const r0 = p.rInner;
  const r1 = p.radius;
  const pts = [
    [r0, h], [r0, -h],
    [r0, -h], [r1, -h],
    [r1, -h], [r1, h],
    [r1, h], [r0, h],
  ].map(([r, y]) => new THREE.Vector2(r, y));
  return new THREE.LatheGeometry(pts, SEGMENTS);
}

function groupKey(p: PrimitiveInfo): string {
  const dims =
    p.type === "cylinder" ? [p.radius, p.height] : p.type === "annulus" ? [p.rInner, p.radius, p.height] : p.size;
  return `${p.type}|${dims.join(",")}|${p.material}`;
}

export interface Group {
  key: string;
  material: string;
  mesh: THREE.InstancedMesh;
  /** Primitive index for each instance. */
  indices: number[];
}

export class CoreScene {
  readonly root = new THREE.Group();
  readonly groups: Group[] = [];
  /** Where each primitive is drawn: its group and instance. */
  readonly where: { group: number; instance: number }[] = [];
  private rods: Record<string, number>;
  private readonly materials = new Map<string, THREE.Material>();
  private readonly capParts: THREE.Object3D[] = [];
  private cut: THREE.Plane | null = null;
  private readonly m = new THREE.Matrix4();
  /** Radius of a sphere around the core, for camera and cap sizes. */
  readonly radius: number;

  constructor(readonly model: ViewerModel) {
    this.rods = { ...model.refRods };
    const byKey = new Map<string, PrimitiveInfo[]>();
    for (const p of model.primitives) {
      const k = groupKey(p);
      if (!byKey.has(k)) byKey.set(k, []);
      byKey.get(k)!.push(p);
    }
    for (const [key, prims] of byKey) {
      const first = prims[0]!;
      const style = styleFor(first.material);
      if (style.opacity === 0) {
        for (const p of prims) this.where[p.index] = { group: -1, instance: -1 };
        continue;
      }
      const mat = this.materialFor(first.material);
      const mesh = new THREE.InstancedMesh(geometryFor(first), mat, prims.length);
      mesh.name = key;
      mesh.frustumCulled = false; // instances move (rods); the base geometry's bounds don't cover them
      if (style.opacity < 1) mesh.renderOrder = 1000; // transparent water last
      const g = this.groups.length;
      this.groups.push({ key, material: first.material, mesh, indices: prims.map((p) => p.index) });
      prims.forEach((p, i) => (this.where[p.index] = { group: g, instance: i }));
      this.root.add(mesh);
    }
    this.applyMatrices();
    const box = new THREE.Box3();
    for (const p of model.primitives) if (styleFor(p.material).pickable) box.union(this.boundsOf(p.index));
    this.radius = box.isEmpty() ? 100 : box.getBoundingSphere(new THREE.Sphere()).radius;
  }

  private materialFor(material: string): THREE.Material {
    let mat = this.materials.get(material);
    if (!mat) {
      const s = styleFor(material);
      mat = new THREE.MeshStandardMaterial({
        color: s.color,
        roughness: 0.6,
        metalness: material === "steel" || material === "aluminum" ? 0.3 : 0.0,
        transparent: s.opacity < 1,
        opacity: s.opacity,
        depthWrite: s.opacity >= 1,
        side: s.opacity < 1 ? THREE.BackSide : THREE.FrontSide,
      });
      this.materials.set(material, mat);
    }
    return mat;
  }

  /** Rod positions (fraction withdrawn). Rods not named keep their position. */
  setRodPositions(rods: Record<string, number>): void {
    this.rods = { ...this.rods, ...rods };
    this.applyMatrices();
  }

  get rodPositions(): Record<string, number> {
    return { ...this.rods };
  }

  private applyMatrices(): void {
    for (const p of this.model.primitives) {
      const w = this.where[p.index]!;
      if (w.group < 0) continue;
      const c = p.center;
      const pos = toScene([c[0], c[1], c[2] + rodOffsetCm(p, this.model, this.rods)]);
      this.m.makeTranslation(pos.x, pos.y, pos.z);
      this.groups[w.group]!.mesh.setMatrixAt(w.instance, this.m);
    }
    for (const g of this.groups) g.mesh.instanceMatrix.needsUpdate = true;
  }

  /** World-space bounds of one primitive as drawn (for tests and camera framing). */
  boundsOf(index: number): THREE.Box3 {
    const w = this.where[index]!;
    const p = this.model.primitives[index]!;
    const g = w.group >= 0 ? this.groups[w.group]!.mesh.geometry : geometryFor(p);
    if (!g.boundingBox) g.computeBoundingBox();
    const box = g.boundingBox!.clone();
    const c = p.center;
    return box.translate(toScene([c[0], c[1], c[2] + rodOffsetCm(p, this.model, this.rods)]));
  }

  /** Per-element overlay: colour the fuel of each element; others keep their material colour. null clears it. */
  setElementColors(colors: Map<string, [number, number, number]> | null): void {
    const white = new THREE.Color(1, 1, 1);
    const c = new THREE.Color();
    for (const g of this.groups) {
      if (g.material !== "fuel") continue;
      g.indices.forEach((pi, i) => {
        const el = this.model.primitives[pi]!.element;
        const rgb = colors && el !== undefined ? colors.get(el) : undefined;
        // Instance colours multiply the material colour, so the overlay uses a white material.
        g.mesh.setColorAt(i, rgb ? c.setRGB(rgb[0], rgb[1], rgb[2], THREE.SRGBColorSpace) : white);
      });
      if (g.mesh.instanceColor) g.mesh.instanceColor.needsUpdate = true;
      const mat = g.mesh.material as THREE.MeshStandardMaterial;
      mat.color.set(colors ? 0xffffff : styleFor("fuel").color);
      mat.needsUpdate = true; // the shader needs the instance-colour attribute once it exists
    }
  }

  /** Set or clear the cutaway (library coordinates). */
  setCutaway(h: HalfSpace | null): void {
    this.cut = h ? planeFor(h) : null;
    const planes = this.cut ? [this.cut] : [];
    for (const mat of this.materials.values()) {
      mat.clippingPlanes = planes;
      mat.needsUpdate = true;
    }
    this.rebuildCaps();
  }

  get cutPlane(): THREE.Plane | null {
    return this.cut;
  }

  /**
   * Stencil caps (per capped material): back faces of the clipped solids add 1, front faces subtract 1,
   * so the stencil is non-zero exactly where the cut plane lies inside a solid. A plane quad in the
   * material's colour is drawn there, and it resets the stencil for the next material.
   */
  private rebuildCaps(): void {
    for (const o of this.capParts) {
      o.removeFromParent();
      if (o instanceof THREE.Mesh) {
        (o.material as THREE.Material).dispose();
        if (o.geometry instanceof THREE.PlaneGeometry) o.geometry.dispose();
      }
    }
    this.capParts.length = 0;
    const plane = this.cut;
    if (!plane) return;
    const materials = [...new Set(this.groups.map((g) => g.material))].filter((m) => styleFor(m).capped);
    materials.forEach((material, k) => {
      const order = 10 + 3 * k;
      const stencilBase = {
        depthWrite: false,
        depthTest: false,
        colorWrite: false,
        stencilWrite: true,
        stencilFunc: THREE.AlwaysStencilFunc,
        clippingPlanes: [plane],
      };
      const back = new THREE.MeshBasicMaterial({
        ...stencilBase,
        side: THREE.BackSide,
        stencilFail: THREE.IncrementWrapStencilOp,
        stencilZFail: THREE.IncrementWrapStencilOp,
        stencilZPass: THREE.IncrementWrapStencilOp,
      });
      const front = new THREE.MeshBasicMaterial({
        ...stencilBase,
        side: THREE.FrontSide,
        stencilFail: THREE.DecrementWrapStencilOp,
        stencilZFail: THREE.DecrementWrapStencilOp,
        stencilZPass: THREE.DecrementWrapStencilOp,
      });
      for (const g of this.groups.filter((x) => x.material === material)) {
        for (const mat of [back, front]) {
          const s = new THREE.InstancedMesh(g.mesh.geometry, mat, g.mesh.count);
          s.instanceMatrix = g.mesh.instanceMatrix; // shared: rods move their caps too
          s.frustumCulled = false;
          s.renderOrder = order;
          this.root.add(s);
          this.capParts.push(s);
        }
      }
      const capMat = new THREE.MeshStandardMaterial({
        color: styleFor(material).color,
        roughness: 0.8,
        side: THREE.DoubleSide,
        stencilWrite: true,
        stencilRef: 0,
        stencilFunc: THREE.NotEqualStencilFunc,
        stencilFail: THREE.ReplaceStencilOp,
        stencilZFail: THREE.ReplaceStencilOp,
        stencilZPass: THREE.ReplaceStencilOp,
      });
      const cap = new THREE.Mesh(new THREE.PlaneGeometry(4 * this.radius + 400, 4 * this.radius + 400), capMat);
      plane.coplanarPoint(cap.position);
      cap.lookAt(cap.position.clone().sub(plane.normal));
      cap.renderOrder = order + 1;
      cap.onAfterRender = (renderer) => renderer.clearStencil();
      cap.name = `cap:${material}`;
      this.root.add(cap);
      this.capParts.push(cap);
    });
  }

  /** Number of draw calls for the solids (instanced groups), without caps. */
  get drawCalls(): number {
    return this.groups.length;
  }

  get triangles(): number {
    let n = 0;
    for (const g of this.groups) {
      const geo = g.mesh.geometry;
      const tris = (geo.index ? geo.index.count : geo.attributes.position!.count) / 3;
      n += tris * g.mesh.count;
    }
    return n;
  }

  dispose(): void {
    this.setCutaway(null);
    for (const g of this.groups) g.mesh.geometry.dispose();
    for (const m of this.materials.values()) m.dispose();
  }
}
