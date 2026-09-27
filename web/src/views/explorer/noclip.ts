/**
 * Noclip camera (plan 04): WASD to move along the view, Q/E down/up, Shift faster, mouse to look.
 * The math is separate from the DOM so tests can drive it; `bindNoclip` connects keys and pointer lock.
 * Scene units are cm (three.js y up).
 */

import * as THREE from "three";

export type NoclipKey = "forward" | "back" | "left" | "right" | "up" | "down" | "fast";

const KEYMAP: Record<string, NoclipKey> = {
  KeyW: "forward",
  KeyS: "back",
  KeyA: "left",
  KeyD: "right",
  KeyE: "up",
  KeyQ: "down",
  ShiftLeft: "fast",
  ShiftRight: "fast",
};

export class NoclipController {
  yaw = 0; // radians, 0 looks along -z
  pitch = 0; // radians, clamped to +-89 degrees
  /** Speed in cm/s; Shift multiplies it by `fastFactor`. */
  speed = 40;
  fastFactor = 4;
  /** Radians per pixel of mouse movement. */
  sensitivity = 0.0025;
  readonly held = new Set<NoclipKey>();

  constructor(readonly camera: THREE.PerspectiveCamera) {
    this.syncFromCamera();
  }

  /** Take yaw and pitch from the camera's current orientation (after switching from orbit). */
  syncFromCamera(): void {
    const e = new THREE.Euler().setFromQuaternion(this.camera.quaternion, "YXZ");
    this.yaw = e.y;
    this.pitch = e.x;
    this.apply();
  }

  look(dx: number, dy: number): void {
    this.yaw -= dx * this.sensitivity;
    const lim = (89 * Math.PI) / 180;
    this.pitch = Math.min(lim, Math.max(-lim, this.pitch - dy * this.sensitivity));
    this.apply();
  }

  /** True while any movement key is held (the view must keep rendering). */
  get moving(): boolean {
    for (const k of this.held) if (k !== "fast") return true;
    return false;
  }

  /** Move for `dt` seconds with the keys held now. */
  update(dt: number): void {
    const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(this.camera.quaternion);
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(this.camera.quaternion);
    const v = new THREE.Vector3();
    if (this.held.has("forward")) v.add(forward);
    if (this.held.has("back")) v.sub(forward);
    if (this.held.has("right")) v.add(right);
    if (this.held.has("left")) v.sub(right);
    if (this.held.has("up")) v.y += 1;
    if (this.held.has("down")) v.y -= 1;
    if (v.lengthSq() === 0) return;
    const s = this.speed * (this.held.has("fast") ? this.fastFactor : 1);
    this.camera.position.addScaledVector(v.normalize(), s * dt);
  }

  private apply(): void {
    this.camera.quaternion.setFromEuler(new THREE.Euler(this.pitch, this.yaw, 0, "YXZ"));
  }

  keyDown(code: string): boolean {
    const k = KEYMAP[code];
    if (k) this.held.add(k);
    return k !== undefined;
  }

  keyUp(code: string): boolean {
    const k = KEYMAP[code];
    if (k) this.held.delete(k);
    return k !== undefined;
  }
}

/** Connect a controller to the page. Look needs pointer lock (click the canvas; Esc leaves). Returns an unbind function. */
export function bindNoclip(c: NoclipController, el: HTMLElement, onChange: () => void): () => void {
  const down = (e: KeyboardEvent) => {
    if (c.keyDown(e.code)) {
      e.preventDefault();
      onChange();
    }
  };
  const up = (e: KeyboardEvent) => {
    if (c.keyUp(e.code)) onChange();
  };
  const move = (e: MouseEvent) => {
    if (document.pointerLockElement !== el) return;
    c.look(e.movementX, e.movementY);
    onChange();
  };
  const blur = () => c.held.clear();
  window.addEventListener("keydown", down);
  window.addEventListener("keyup", up);
  window.addEventListener("blur", blur);
  document.addEventListener("mousemove", move);
  return () => {
    window.removeEventListener("keydown", down);
    window.removeEventListener("keyup", up);
    window.removeEventListener("blur", blur);
    document.removeEventListener("mousemove", move);
    c.held.clear();
  };
}
