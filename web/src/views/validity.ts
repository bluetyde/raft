import type { ValidityView } from "../runtime/envelope";
import type { RuntimeClient } from "../runtime/client";

const HEADLINE: Record<ValidityView["level"], string> = {
  ok: "Supported state",
  caution: "Caution: this state is not validated",
  warning: "WARNING: outside the supported range",
};

const COLOURS: Record<ValidityView["level"], { bg: string; fg: string }> = {
  ok: { bg: "#e3f4e6", fg: "#14451c" },
  caution: { bg: "#fff3cd", fg: "#5c4400" },
  warning: { bg: "#f8d7da", fg: "#6b0f1a" },
};

/** The text of a validity view, for the banner and for tests. */
export function describeValidity(v: ValidityView): string[] {
  const lines = [HEADLINE[v.level]];
  if (v.summary) lines.push(`Lesson: ${v.summary}`);
  lines.push(...v.messages);
  return lines;
}

const banners = new WeakMap<HTMLElement, () => void>();

/** Stop a banner following the runtime (call when the panel that holds it is disposed, or the dead banner keeps receiving every update). */
export function disposeValidityBanner(box: HTMLElement): void {
  banners.get(box)?.();
  banners.delete(box);
}

/** A banner that follows the runtime's validity view. Shown in every window that has a state to trust. */
export function createValidityBanner(client: RuntimeClient): HTMLElement {
  const box = document.createElement("div");
  box.dataset["validity"] = "banner";
  box.style.cssText = "margin: 6px 0; padding: 6px 10px; border-radius: 4px; font-size: 0.9em; line-height: 1.35;";
  box.hidden = true;
  const off = client.on("validity", (m) => {
    const lines = describeValidity(m.view);
    const c = COLOURS[m.view.level];
    box.style.background = c.bg;
    box.style.color = c.fg;
    box.dataset["level"] = m.view.level;
    box.replaceChildren();
    const head = document.createElement("strong");
    head.textContent = lines[0]!;
    box.append(head);
    for (const line of lines.slice(1)) {
      const p = document.createElement("div");
      p.textContent = line;
      box.append(p);
    }
    box.hidden = false;
  });
  banners.set(box, off);
  // the runtime posted its first view before this window subscribed; ask for it again
  client.resync();
  return box;
}
