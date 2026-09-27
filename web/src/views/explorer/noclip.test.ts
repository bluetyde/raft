import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { NoclipController } from "./noclip";

function controller() {
  const cam = new THREE.PerspectiveCamera();
  cam.position.set(0, 0, 0);
  const c = new NoclipController(cam);
  c.speed = 10;
  return { cam, c };
}

describe("noclip camera", () => {
  it("W moves along the view direction at the set speed", () => {
    const { cam, c } = controller();
    c.keyDown("KeyW");
    c.update(0.5);
    expect(cam.position.distanceTo(new THREE.Vector3(0, 0, -5))).toBeLessThan(1e-12);
  });

  it("follows the yaw: after turning 90 degrees left, W moves along -x", () => {
    const { cam, c } = controller();
    c.look(-(Math.PI / 2) / c.sensitivity, 0); // mouse left
    c.keyDown("KeyW");
    c.update(1);
    expect(cam.position.distanceTo(new THREE.Vector3(-10, 0, 0))).toBeLessThan(1e-9);
  });

  it("Shift multiplies the speed; Q and E move down and up", () => {
    const { cam, c } = controller();
    c.keyDown("KeyE");
    c.keyDown("ShiftLeft");
    c.update(1);
    expect(cam.position.y).toBeCloseTo(10 * c.fastFactor, 12);
    c.keyUp("KeyE");
    c.keyUp("ShiftLeft");
    c.keyDown("KeyQ");
    c.update(1);
    expect(cam.position.y).toBeCloseTo(10 * c.fastFactor - 10, 12);
  });

  it("pitch is clamped short of straight up and down", () => {
    const { c } = controller();
    c.look(0, -1e6);
    expect(c.pitch).toBeCloseTo((89 * Math.PI) / 180, 12);
    c.look(0, 1e6);
    expect(c.pitch).toBeCloseTo((-89 * Math.PI) / 180, 12);
  });

  it("opposite keys cancel, and moving is false with only Shift held", () => {
    const { cam, c } = controller();
    c.keyDown("KeyA");
    c.keyDown("KeyD");
    c.update(1);
    expect(cam.position.length()).toBe(0);
    c.keyUp("KeyA");
    c.keyUp("KeyD");
    c.keyDown("ShiftLeft");
    expect(c.moving).toBe(false);
    expect(c.keyDown("KeyZ")).toBe(false);
  });

  it("takes yaw and pitch from the camera when switching from orbit", () => {
    const cam = new THREE.PerspectiveCamera();
    cam.position.set(0, 10, 10);
    cam.lookAt(0, 0, 0);
    const c = new NoclipController(cam);
    expect(c.pitch).toBeCloseTo(-Math.PI / 4, 9);
    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion);
    expect(fwd.distanceTo(new THREE.Vector3(0, -1, -1).normalize())).toBeLessThan(1e-9);
  });
});
