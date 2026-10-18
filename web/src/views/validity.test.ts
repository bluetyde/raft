import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createValidityBanner, disposeValidityBanner } from "./validity";

/** A banner must stop following the runtime when its panel goes: the whole-repo review found the subscription kept for ever. */

class FakeEl {
  dataset: Record<string, string> = {};
  style: Record<string, string> = {};
  hidden = false;
  textContent = "";
  children: FakeEl[] = [];
  replaceChildren() { this.children = []; }
  append(...c: FakeEl[]) { this.children.push(...c); }
}

beforeEach(() => { (globalThis as any).document = { createElement: () => new FakeEl() }; });
afterEach(() => { delete (globalThis as any).document; });

function fakeClient() {
  const listeners = new Set<(m: any) => void>();
  return {
    listeners,
    on: (_k: string, fn: (m: any) => void) => { listeners.add(fn); return () => { listeners.delete(fn); }; },
    resync: () => {},
  } as any;
}

describe("the validity banner", () => {
  it("follows the runtime until it is disposed, then no more", () => {
    const c = fakeClient();
    const box = createValidityBanner(c) as unknown as FakeEl;
    expect(c.listeners.size).toBe(1);
    const view = { level: "caution", status: "unvalidated", messages: ["a message"], reasons: [] };
    for (const fn of c.listeners) fn({ view });
    expect(box.dataset["level"]).toBe("caution");
    disposeValidityBanner(box as unknown as HTMLElement);
    expect(c.listeners.size).toBe(0);
    disposeValidityBanner(box as unknown as HTMLElement);        // twice is harmless
    expect(c.listeners.size).toBe(0);
  });

  it("each banner has its own subscription", () => {
    const c = fakeClient();
    const a = createValidityBanner(c);
    const b = createValidityBanner(c);
    expect(c.listeners.size).toBe(2);
    disposeValidityBanner(a);
    expect(c.listeners.size).toBe(1);
    disposeValidityBanner(b);
    expect(c.listeners.size).toBe(0);
  });
});
