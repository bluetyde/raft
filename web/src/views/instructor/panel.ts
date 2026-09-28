/**
 * The instructor panel (M6 slice S1, docs/m6-instructor-design.md §3): time bar, timeline with rewind,
 * faults, and the truth panel. It sends commands as clientId "instructor".
 */

import type { Ack, RuntimeClient } from "../../runtime/client";
import { RUNTIME_REJECTIONS, type ActiveFaults, type FromWorker } from "../../runtime/protocol";
import { formatPeriod, formatPower } from "../explorer/live";
import { kelvinToCelsius } from "../operator/meters";
import { faultLabel, instrumentFault, pumpFault, reactivityFault, WAITING_FOR_ENGINE, type InstrumentFaultKind } from "./faults";
import { formatOuterStep, OUTER_STEPS, ratesFor } from "./time";
import { Timeline } from "./timeline";
import { activeFaultLines, formatPcm, formatSignal, instrumentRows, reactivityBars } from "./truth";

export interface InstructorLibrary {
  instruments: { id: string; signal: string }[];
  pumps: string[];
}

export interface InstructorOptions {
  /** Start a new session of the same library with this outer step (the step is fixed per session). */
  restart(outerDt: number): void;
}

type SnapshotMsg = Extract<FromWorker, { kind: "snapshot" }>;
type ClockMsg = Extract<FromWorker, { kind: "clock" }>;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> = {}, children: (Node | string)[] = []) {
  const e = document.createElement(tag);
  Object.assign(e, props);
  for (const c of children) e.append(c);
  return e;
}

function button(text: string, data: string, onclick: () => void): HTMLButtonElement {
  const b = el("button", { textContent: text, onclick });
  b.dataset["inst"] = data;
  return b;
}

function describe(ack: Ack): string {
  const text = ack.reason ? RUNTIME_REJECTIONS[ack.reason] : undefined;
  return `rejected: ${ack.reason}${text ? ` (${text})` : ""}`;
}

export class InstructorPanel {
  readonly root: HTMLElement;
  readonly timeline = new Timeline();
  private outerDt = 0.01;
  private paused = true;
  private readonly play: HTMLButtonElement;
  private readonly rate: HTMLSelectElement;
  private readonly clockText: HTMLElement;
  private readonly stepText: HTMLElement;
  private readonly bar: HTMLElement;
  private readonly confirmBox: HTMLElement;
  private pendingStep: number | null = null;
  private readonly message: HTMLElement;
  private readonly activeList: HTMLElement;
  private readonly instrumentTable: HTMLElement;
  private readonly truthTable: HTMLElement;
  private readonly bars: HTMLElement;
  private readonly rhoInput: HTMLInputElement;
  /** The last faults and snapshot the panel drew (for tests). */
  lastFaults: ActiveFaults | undefined;

  constructor(
    private readonly client: RuntimeClient,
    private readonly lib: InstructorLibrary,
    private readonly opts: InstructorOptions,
  ) {
    // ---- time bar ----
    this.play = button("play", "play", () => this.client.setTime({ paused: !this.paused }));
    this.rate = el("select");
    this.rate.dataset["inst"] = "rate";
    this.rate.onchange = () => this.client.setTime({ rate: Number(this.rate.value) });
    const step = button("step", "step", () => this.client.step(1));
    this.clockText = el("span", { className: "vr-inst-clock" });
    this.stepText = el("span", { className: "vr-inst-outer" });
    this.stepText.dataset["inst"] = "outer-step";
    const outer = el("select");
    outer.dataset["inst"] = "outer-choice";
    for (const s of OUTER_STEPS) outer.append(new Option(s.label, String(s.outerDt)));
    const restart = button("new session", "restart", () => this.opts.restart(Number(outer.value)));

    // ---- timeline ----
    this.bar = el("div", { className: "vr-inst-timeline" });
    this.bar.dataset["inst"] = "timeline";
    this.bar.onclick = (ev) => {
      const r = this.bar.getBoundingClientRect();
      this.askRewind(this.timeline.stepAt((ev.clientX - r.left) / Math.max(1, r.width), this.outerDt));
    };
    this.confirmBox = el("div", { className: "vr-inst-confirm", hidden: true });

    // ---- faults ----
    const insSelect = el("select");
    insSelect.dataset["inst"] = "fault-instrument";
    for (const ins of lib.instruments) insSelect.append(new Option(ins.id, ins.id));
    const insButtons = (["stuck", "dead", "clear"] as InstrumentFaultKind[]).map((k) =>
      button(k, `fault-${k}`, () => void this.send(instrumentFault(insSelect.value, k))),
    );
    this.rhoInput = el("input", { type: "number", value: "50", step: "10" });
    this.rhoInput.dataset["inst"] = "rho";
    const insert = button("insert (pcm)", "rho-insert", () => {
      let cmd: Record<string, unknown>;
      try {
        cmd = reactivityFault(Number(this.rhoInput.value));
      } catch (err) {
        this.message.textContent = String((err as Error).message);
        return;
      }
      void this.send(cmd);
    });
    const pumpRows = lib.pumps.map((p) =>
      el("div", { className: "vr-row" }, [
        `pump ${p}`,
        button("trip", `pump-trip-${p}`, () => void this.send(pumpFault(p, false))),
        button("restart", `pump-on-${p}`, () => void this.send(pumpFault(p, true))),
      ]),
    );
    this.activeList = el("ul", { className: "vr-inst-active" });
    this.activeList.dataset["inst"] = "active-faults";
    this.message = el("div", { className: "vr-inst-message" });
    this.message.dataset["inst"] = "message";

    // ---- truth ----
    this.truthTable = el("table", { className: "vr-inst-table" });
    this.truthTable.dataset["inst"] = "truth";
    this.instrumentTable = el("table", { className: "vr-inst-table" });
    this.instrumentTable.dataset["inst"] = "instruments";
    this.bars = el("div", { className: "vr-inst-bars" });
    this.bars.dataset["inst"] = "reactivity";

    this.root = el("div", { className: "vr-instructor" }, [
      el("section", {}, [
        el("h3", { textContent: "Time" }),
        el("div", { className: "vr-row" }, [this.play, this.rate, step, this.clockText]),
        el("div", { className: "vr-row" }, ["outer step: ", this.stepText, outer, restart]),
      ]),
      el("section", {}, [el("h3", { textContent: "Timeline (click to rewind)" }), this.bar, this.confirmBox]),
      el("section", {}, [
        el("h3", { textContent: "Faults" }),
        el("div", { className: "vr-row" }, ["instrument", insSelect, ...insButtons]),
        el("div", { className: "vr-row" }, ["reactivity", this.rhoInput, insert]),
        el("div", {
          className: "vr-inst-note",
          textContent: "A step insertion can trip a period trip at once, when the trip reads the true period (it has no lag).",
        }),
        ...pumpRows,
        el("div", { className: "vr-inst-note", textContent: `Not in the engine yet: ${WAITING_FOR_ENGINE.join(", ")}.` }),
        el("div", { textContent: "Active faults (hidden from the operator):" }),
        this.activeList,
        this.message,
      ]),
      el("section", {}, [
        el("h3", { textContent: "Truth" }),
        this.truthTable,
        el("h3", { textContent: "Instruments: reading and true value" }),
        this.instrumentTable,
        el("h3", { textContent: "Reactivity by source (pcm)" }),
        this.bars,
      ]),
    ]);
    this.setOuterDt(0.01);
  }

  /** A new session is loaded: set its outer step and clear the timeline. */
  setSession(outerDt: number): void {
    this.timeline.reset();
    this.setOuterDt(outerDt);
    this.drawTimeline();
  }

  private setOuterDt(outerDt: number): void {
    this.outerDt = outerDt;
    this.stepText.textContent = formatOuterStep(outerDt);
    this.rate.replaceChildren(...ratesFor(outerDt).map((r) => new Option(`${r}×`, String(r))));
    this.rate.value = "1";
  }

  onSnapshot(m: SnapshotMsg): void {
    const s = m.snapshot;
    this.lastFaults = m.faults;
    this.timeline.setEnd(s.t);
    const tr = s.truth;
    const rows: [string, string][] = [
      ["t", `${s.t.toFixed(2)} s`],
      ["power", formatPower(tr.power)],
      ["period", formatPeriod(tr.period)],
      ["fuel", `${kelvinToCelsius(tr.fuelTemp).toFixed(2)} °C`],
      ["coolant", `${kelvinToCelsius(tr.coolantTemp).toFixed(2)} °C`],
      ["iodine", Number(tr.iodine).toPrecision(4)],
      ["xenon", Number(tr.xenon).toPrecision(4)],
      ["peak power", `${formatPower(tr.peakPower)} at ${Number(tr.peakTime).toFixed(3)} s`],
      ["mode", String(tr.mode)],
    ];
    this.truthTable.replaceChildren(...rows.map(([k, v]) => el("tr", {}, [el("th", { textContent: k }), el("td", { textContent: v })])));
    this.instrumentTable.replaceChildren(
      el("tr", {}, ["instrument", "reading", "true value", "fault"].map((h) => el("th", { textContent: h }))),
      ...instrumentRows(this.lib.instruments, s, m.faults).map((r) => {
        const row = el("tr", {}, [
          el("td", { textContent: r.id }),
          el("td", { textContent: formatSignal(r.signal, r.indicated) }),
          el("td", { textContent: formatSignal(r.signal, r.truth) }),
          el("td", { textContent: r.fault ?? "" }),
        ]);
        row.dataset["instrument"] = r.id;
        return row;
      }),
    );
    const { bars, totalPcm } = reactivityBars(tr.reactivity);
    this.bars.replaceChildren(
      ...bars.map((b) => {
        const fill = el("div", { className: `vr-inst-fill${b.pcm < 0 ? " neg" : ""}` });
        fill.style.width = `${(b.size * 100).toFixed(1)}%`;
        const row = el("div", { className: "vr-inst-barrow" }, [
          el("span", { textContent: b.source }),
          el("div", { className: "vr-bar-track" }, [fill]),
          el("span", { textContent: formatPcm(b.pcm) }),
        ]);
        row.dataset["source"] = b.source;
        return row;
      }),
      el("div", { className: "vr-inst-total", textContent: `total ${formatPcm(totalPcm)} pcm` }),
    );
    const lines = activeFaultLines(m.faults, tr.pumps);
    this.activeList.replaceChildren(...(lines.length ? lines : ["none"]).map((l) => el("li", { textContent: l })));
    this.drawTimeline();
  }

  onClock(m: ClockMsg): void {
    this.paused = m.paused;
    this.play.textContent = m.paused ? "play" : "pause";
    this.rate.value = String(m.rate);
    const limit = m.limited ? ` (limited: ${m.limited}${m.reason ? `, ${m.reason}` : ""})` : "";
    this.clockText.textContent = `${m.paused ? "paused" : `${m.achievedRate.toFixed(1)}× achieved`}${limit}, step ${m.step}`;
  }

  onEvents(events: Record<string, any>[]): void {
    this.timeline.onEvents(events);
    this.drawTimeline();
  }

  onRewound(t: number): void {
    this.timeline.rewoundTo(t);
    this.drawTimeline();
  }

  private askRewind(step: number): void {
    this.pendingStep = step;
    const t = step * this.outerDt;
    this.confirmBox.hidden = false;
    this.confirmBox.replaceChildren(
      `Rewind to step ${step} (t = ${t.toFixed(2)} s)? Later actions go to the old timeline. `,
      button("rewind", "rewind-yes", () => void this.rewind()),
      button("cancel", "rewind-no", () => this.closeConfirm()),
    );
  }

  private closeConfirm(): void {
    this.pendingStep = null;
    this.confirmBox.hidden = true;
  }

  private async rewind(): Promise<void> {
    const step = this.pendingStep;
    this.closeConfirm();
    if (step === null) return;
    try {
      const m = await this.client.rewind(step);
      this.message.textContent = `rewound to step ${m.step}`;
    } catch (err) {
      this.message.textContent = `rewind failed: ${String(err)}`;
    }
  }

  private async send(cmd: Record<string, unknown>): Promise<void> {
    const ack = await this.client.command(cmd, undefined, "instructor");
    const label = faultLabel(cmd as Record<string, any>);
    if (ack.status === "accepted") {
      this.timeline.onFault(ack.t, label);
      this.message.textContent = `${label}: accepted at t = ${ack.t.toFixed(2)} s`;
    } else {
      this.message.textContent = `${label}: ${describe(ack)}`;
    }
    this.drawTimeline();
  }

  private drawTimeline(): void {
    const marks = this.timeline.markers().map((mk) => {
      const d = el("div", { className: `vr-inst-mark ${mk.kind}`, title: `${mk.label} (t = ${mk.t.toFixed(2)} s)` });
      d.style.left = `${(this.timeline.position(mk.t) * 100).toFixed(2)}%`;
      d.dataset["kind"] = mk.kind;
      return d;
    });
    this.bar.replaceChildren(...marks);
    this.bar.dataset["end"] = this.timeline.endT.toFixed(2);
  }
}
