/**
 * M4 control strip: time, rods, scram and mode, plus a small read-out of the live state.
 * Every control sends a command through the runtime client (the command bus); nothing here
 * changes simulation state directly (ARCHITECTURE: views only send commands).
 * The read-out shows truth values, as the explorer may (the operator panel, M5, shows only `indicated`).
 */

import type { RuntimeClient } from "../runtime/client";
import type { FromWorker } from "../runtime/protocol";
import { formatPeriod, formatPower } from "../views/explorer/live";

export interface ControlsLibrary {
  rods: { id: string; pulseCapable: boolean }[];
  modes: string[];
}

const RATES = [0.1, 1, 10, 100];

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> = {}, children: (Node | string)[] = []) {
  const e = document.createElement(tag);
  Object.assign(e, props);
  for (const c of children) e.append(c);
  return e;
}

export class Controls {
  readonly root: HTMLElement;
  private paused = true;
  private readonly play: HTMLButtonElement;
  private readonly rate: HTMLSelectElement;
  private readonly clockText: HTMLElement;
  private readonly readout: HTMLElement;
  private readonly message: HTMLElement;
  private readonly rodText = new Map<string, HTMLElement>();
  private readonly mode: HTMLSelectElement;

  constructor(
    private readonly client: RuntimeClient,
    lib: ControlsLibrary,
  ) {
    this.play = el("button", { textContent: "▶ Run", onclick: () => this.client.setTime({ paused: !this.paused }) });
    this.play.dataset["control"] = "play";
    this.rate = el("select", {}, RATES.map((r) => el("option", { value: String(r), textContent: `${r}×` })));
    this.rate.value = "1";
    this.rate.dataset["control"] = "rate";
    this.rate.onchange = () => this.client.setTime({ rate: Number(this.rate.value) });
    this.clockText = el("span", { className: "vr-clock" });

    const rodRows = lib.rods.map((r) => {
      const pos = el("span", { className: "vr-pos", textContent: "–" });
      this.rodText.set(r.id, pos);
      const button = (label: string, cmd: Record<string, unknown>, key: string) => {
        const b = el("button", { textContent: label, onclick: () => void this.send(cmd) });
        b.dataset["control"] = `${r.id}:${key}`;
        return b;
      };
      const buttons = [
        button("▼ in", { type: "rod.move", rod: r.id, direction: "in" }, "in"),
        button("■", { type: "rod.move", rod: r.id, direction: "stop" }, "stop"),
        button("▲ out", { type: "rod.move", rod: r.id, direction: "out" }, "out"),
      ];
      if (r.pulseCapable) buttons.push(button("fire", { type: "rod.fire", rod: r.id }, "fire"));
      return el("div", { className: "vr-row" }, [el("span", { className: "vr-rodname", textContent: r.id }), pos, ...buttons]);
    });

    this.mode = el("select", {}, lib.modes.map((m) => el("option", { value: m, textContent: m })));
    this.mode.dataset["control"] = "mode";
    this.mode.onchange = () => void this.send({ type: "mode.set", mode: this.mode.value });
    const scram = el("button", { textContent: "SCRAM", className: "vr-scram", onclick: () => void this.send({ type: "scram", reason: "operator" }) });
    scram.dataset["control"] = "scram";
    const reset = el("button", { textContent: "reset trips", onclick: () => void this.send({ type: "trip.reset" }) });
    reset.dataset["control"] = "reset";

    this.readout = el("div", { className: "vr-readout" });
    this.message = el("div", { className: "vr-note" });
    this.root = el("div", { className: "vr-controls" }, [
      el("div", { className: "vr-row" }, [this.play, this.rate, this.clockText]),
      ...rodRows,
      el("div", { className: "vr-row" }, [scram, reset, el("label", {}, ["mode ", this.mode])]),
      this.readout,
      this.message,
    ]);
  }

  /** Send a command; show a rejection with the engine's (or runtime's) reason. */
  private async send(cmd: Record<string, unknown>): Promise<void> {
    const ack = await this.client.command(cmd);
    this.message.textContent =
      ack.status === "rejected" ? `${String(cmd["type"])} rejected: ${ack.reason}` : `${String(cmd["type"])} accepted at t = ${ack.t.toFixed(2)} s`;
  }

  onClock(m: Extract<FromWorker, { kind: "clock" }>): void {
    this.paused = m.paused;
    this.play.textContent = m.paused ? "▶ Run" : "⏸ Pause";
    const limit = m.limited ? ` (limited: ${m.limited}${m.reason ? `, ${m.reason}` : ""})` : "";
    this.clockText.textContent = m.paused ? `paused${limit}` : `${m.achievedRate.toPrecision(3)}× achieved${limit}`;
  }

  onSnapshot(s: Record<string, any>): void {
    const t = s.truth;
    for (const [id, r] of Object.entries<any>(t.rods)) {
      const span = this.rodText.get(id);
      if (span) span.textContent = `${(100 * r.position).toFixed(1)} %${r.moving ? (r.moving === "out" ? " ▲" : " ▼") : ""}`;
    }
    if (this.mode.value !== t.mode) this.mode.value = t.mode;
    const lines: [string, string][] = [
      ["sim time", `${s.t.toFixed(2)} s`],
      ["power", formatPower(t.power)],
      ["period", formatPeriod(t.period)],
      ["fuel temperature", `${t.fuelTemp.toFixed(1)} K`],
      ["peak power", `${formatPower(t.peakPower)} at ${t.peakTime.toFixed(3)} s`],
      ["trips", s.tripped ? [...s.trips.latched, ...s.trips.active].join(", ") || "tripped" : "none"],
      ["validity", `${s.validity.status}${s.validity.reasons.length ? ` (${s.validity.reasons.join(", ")})` : ""}`],
    ];
    this.readout.replaceChildren(
      el("table", {}, lines.map(([k, v]) => {
        const td = el("td", { textContent: v });
        td.dataset["readout"] = k;
        return el("tr", {}, [el("th", { textContent: k }), td]);
      })),
    );
  }
}
