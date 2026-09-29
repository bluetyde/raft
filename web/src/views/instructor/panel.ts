/**
 * The instructor panel (M6 slice S1, docs/m6-instructor-design.md §3): time bar, timeline with rewind,
 * faults, and the truth panel. It sends commands as clientId "instructor".
 */

import type { Ack, RuntimeClient } from "../../runtime/client";
import { RUNTIME_REJECTIONS, type ActiveFaults, type BranchSummary, type FromWorker, type ScenarioView, type SessionFile } from "../../runtime/protocol";
import type { ScenarioFile } from "../../runtime/scenario";
import { download, timeTag, traceInWorker } from "./export";
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
  /** The library's files again (the CSV worker loads its own copy). */
  files(): Promise<Record<string, ArrayBuffer>>;
  /** The library id, for file names. */
  libraryId: string;
  /** The scenarios shipped for this library (docs/m5-scenarios-design.md). */
  scenarios?: ScenarioFile[];
  /** Start a scenario: a new session of its library. */
  startScenario?(file: ScenarioFile): void;
  /** The scenario file with this id (a version 3 session file names its scenario). */
  findScenario?(id: string): ScenarioFile | undefined;
}

type SnapshotMsg = Extract<FromWorker, { kind: "snapshot" }>;
type ClockMsg = Extract<FromWorker, { kind: "clock" }>;
type TimelineMsg = Extract<FromWorker, { kind: "timeline" }>;

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

import { JevCopilot, createCopilotButton } from "../copilot";

export class InstructorPanel {
  readonly root: HTMLElement;
  readonly timeline = new Timeline();
  private readonly copilot: JevCopilot;
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
  private readonly noteInput: HTMLInputElement;
  private readonly noteList: HTMLElement;
  private readonly compare: HTMLElement;
  private readonly exportText: HTMLElement;
  private lastTimeline: TimelineMsg | null = null;
  private readonly scenarioBox: HTMLElement;
  /** The running scenario as the worker last sent it (for tests). */
  scenario: ScenarioView | null = null;
  private lastSnapshot: Record<string, any> | null = null;
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

    // ---- history: notes and branches ----
    this.noteInput = el("input", { type: "text", placeholder: "note at the current time", maxLength: 500 });
    this.noteInput.dataset["inst"] = "note-text";
    const addNote = button("add note", "note-add", () => {
      const text = this.noteInput.value.trim();
      if (!text) return;
      this.client.annotate(text);
      this.noteInput.value = "";
    });
    this.noteList = el("ul", { className: "vr-inst-notes" });
    this.noteList.dataset["inst"] = "notes";
    this.compare = el("table", { className: "vr-inst-table" });
    this.compare.dataset["inst"] = "branches";

    // ---- scenario ----
    const scenarioSelect = el("select");
    scenarioSelect.dataset["inst"] = "scenario-choice";
    for (const sc of opts.scenarios ?? []) scenarioSelect.append(new Option(sc.title, sc.id));
    const startScenario = button("start scenario", "scenario-start", () => {
      const sc = (opts.scenarios ?? []).find((x) => x.id === scenarioSelect.value);
      if (sc) opts.startScenario?.(sc);
    });
    startScenario.disabled = (opts.scenarios ?? []).length === 0;
    const endScenario = button("end scenario", "scenario-end", () => this.client.endScenario());
    this.scenarioBox = el("div", { className: "vr-inst-scenario" });
    this.scenarioBox.dataset["inst"] = "scenario";
    this.scenarioBox.textContent = "no scenario";

    // ---- export ----
    const exportSession = button("session file", "export-session", () => void this.exportSession());
    const exportCsv = button("CSV (every 0.1 s)", "export-csv", () => void this.exportCsv());
    const importInput = el("input", { type: "file", accept: ".json,application/json" });
    importInput.dataset["inst"] = "import";
    importInput.onchange = () => void this.importFile(importInput);
    this.exportText = el("div", { className: "vr-inst-message" });
    this.exportText.dataset["inst"] = "export-message";

    this.copilot = new JevCopilot(client, "instructor");
    const copilotBtn = createCopilotButton(this.copilot);

    const hdr = el("div", { className: "vr-row" }, [
      el("h2", { textContent: "Instructor Panel" }),
      copilotBtn
    ]);
    hdr.style.justifyContent = "space-between";
    hdr.style.marginBottom = "10px";

    this.root = el("div", { className: "vr-instructor" }, [
      hdr,
      el("section", {}, [
        el("h3", { textContent: "Time" }),
        el("div", { className: "vr-row" }, [this.play, this.rate, step, this.clockText]),
        el("div", { className: "vr-row" }, ["outer step: ", this.stepText, outer, restart]),
      ]),
      el("section", {}, [
        el("h3", { textContent: "Scenario" }),
        el("div", { className: "vr-row" }, [scenarioSelect, startScenario, endScenario]),
        this.scenarioBox,
      ]),
      el("section", {}, [el("h3", { textContent: "Timeline (click to rewind)" }), this.bar, this.confirmBox]),
      el("section", {}, [
        el("h3", { textContent: "Notes" }),
        el("div", { className: "vr-row" }, [this.noteInput, addNote]),
        this.noteList,
        el("h3", { textContent: "Branches (compare)" }),
        el("div", { className: "vr-inst-scroll" }, [this.compare]),
      ]),
      el("section", {}, [
        el("h3", { textContent: "Export and import" }),
        el("div", { className: "vr-row" }, [exportSession, exportCsv, "import:", importInput]),
        this.exportText,
      ]),
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
    this.lastSnapshot = s;
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
    this.drawCompare();
  }

  /** The worker's scenario state: goals with their status, the scripted events and the score. */
  onScenario(m: Extract<FromWorker, { kind: "scenario" }>): void {
    const sc = m.scenario;
    this.scenario = sc;
    if (!sc) {
      this.scenarioBox.replaceChildren("no scenario");
      return;
    }
    const mark = { waiting: "·", open: "○", met: "✓", failed: "✗" } as const;
    const goals = el(
      "ol",
      { className: "vr-inst-goals" },
      sc.goals.map((g) => {
        const li = el("li", { className: g.status }, [`${mark[g.status]} ${g.text}${g.t !== null ? ` (t = ${g.t.toFixed(1)} s)` : ""}`]);
        li.dataset["goal"] = g.id;
        li.dataset["status"] = g.status;
        return li;
      }),
    );
    const s = sc.score;
    const score = el("div", { className: "vr-inst-score" });
    score.dataset["inst"] = "scenario-score";
    score.textContent =
      `goals met ${s.met} of ${s.total}${s.failed ? `, failed ${s.failed}` : ""}, unexpected trips ${s.trips}` +
      `${sc.endedAt !== null ? ` (ended at t = ${sc.endedAt.toFixed(1)} s)` : sc.done ? " (done)" : ""}`;
    this.scenarioBox.replaceChildren(
      el("strong", { textContent: sc.title }),
      el("div", { className: "vr-inst-note", textContent: sc.brief }),
      goals,
      score,
      el("div", {
        className: "vr-inst-note",
        textContent: `allowed controls: ${sc.allow.join(", ") || "none"}. Scripted events: ${sc.events.map((e) => `t = ${e.t.toFixed(2)} s ${e.note}`).join("; ") || "none"}.`,
      }),
    );
  }

  /** The worker's timeline: marks, notes, and the branches for the compare table. */
  onTimeline(m: TimelineMsg): void {
    this.lastTimeline = m;
    const fork = m.current.parent !== null ? m.current.forkStep * this.outerDt : null;
    this.timeline.set(m.marks, m.annotations, fork);
    this.noteList.replaceChildren(
      ...m.annotations.map((a) => {
        const li = el("li", {}, [
          `t = ${a.t.toFixed(2)} s: ${a.text} `,
          button("delete", `note-delete-${a.id}`, () => this.client.deleteAnnotation(a.id)),
        ]);
        li.dataset["note"] = String(a.id);
        return li;
      }),
    );
    this.drawTimeline();
    this.drawCompare();
  }

  /** Amendment 4: each branch's fork step and command count next to its final values. The current row uses the latest snapshot. */
  private drawCompare(): void {
    const m = this.lastTimeline;
    if (!m) return;
    const head = ["branch", "parent", "fork step", "commands", "notes", "end t", "power", "fuel", "xenon", "tripped", ""];
    const row = (b: BranchSummary, current: boolean) => {
      const f = current && this.lastSnapshot ? this.liveFinal(this.lastSnapshot) : b.final;
      const tr = el("tr", { className: current ? "current" : "" }, [
        el("td", { textContent: `${b.id}${current ? " (current)" : ""}` }),
        el("td", { textContent: b.parent === null ? "—" : String(b.parent) }),
        el("td", { textContent: String(b.forkStep) }),
        el("td", { textContent: String(b.commandCount) }),
        el("td", { textContent: String(current ? m.annotations.length : b.annotationCount) }),
        el("td", { textContent: `${f.t.toFixed(2)} s` }),
        el("td", { textContent: formatPower(f.power) }),
        el("td", { textContent: `${kelvinToCelsius(f.fuelTemp).toFixed(2)} °C` }),
        el("td", { textContent: f.xenon.toPrecision(4) }),
        el("td", { textContent: f.tripped ? `yes (${f.latched.join(", ") || "active"})` : "no" }),
        el("td", {}, current ? [] : [button("switch", `branch-switch-${b.id}`, () => void this.switchTo(b.id))]),
      ]);
      tr.dataset["branch"] = String(b.id);
      return tr;
    };
    this.compare.replaceChildren(
      el("tr", {}, head.map((h) => el("th", { textContent: h }))),
      row(m.current, true),
      ...[...m.branches].reverse().map((b) => row(b, false)),
    );
  }

  private liveFinal(s: Record<string, any>): BranchSummary["final"] {
    return {
      t: s.t,
      power: s.truth.power,
      fuelTemp: s.truth.fuelTemp,
      coolantTemp: s.truth.coolantTemp,
      xenon: s.truth.xenon,
      tripped: s.tripped,
      latched: [...s.trips.latched],
    };
  }

  private async switchTo(id: number): Promise<void> {
    try {
      const m = await this.client.switchBranch(id);
      this.message.textContent = `switched to branch ${id} (step ${m.step})`;
    } catch (err) {
      this.message.textContent = `switch failed: ${String(err)}`;
    }
  }

  private async exportSession(): Promise<void> {
    const file = await this.client.exportSession();
    const t = file.endStep * this.outerDt;
    download(`${this.opts.libraryId}-${timeTag(t)}.session.json`, JSON.stringify(file), "application/json");
    this.exportText.textContent = `session file: ${file.session.commands.length} commands, ${file.annotations?.length ?? 0} notes, t = ${t.toFixed(2)} s`;
  }

  private async exportCsv(): Promise<void> {
    this.exportText.textContent = "writing the CSV (replaying the session in a separate worker)…";
    const file = await this.client.exportSession();
    const reply = await traceInWorker(await this.opts.files(), file, 0.1);
    if (!reply.ok) {
      this.exportText.textContent = `CSV failed: ${reply.message}`;
      return;
    }
    download(`${this.opts.libraryId}-${timeTag(file.endStep * this.outerDt)}.csv`, reply.csv, "text/csv");
    this.exportText.textContent = `CSV: ${reply.rows} rows`;
  }

  private async importFile(input: HTMLInputElement): Promise<void> {
    const f = input.files?.[0];
    if (!f) return;
    try {
      const file = JSON.parse(await f.text()) as SessionFile;
      const scenario = file.scenario ? this.opts.findScenario?.(file.scenario.id) : undefined;
      if (file.scenario && !scenario) throw new Error(`this app does not ship the scenario ${file.scenario.id}`);
      const m = await this.client.importSession(file, scenario);
      this.exportText.textContent = `imported ${f.name}: step ${m.step}, t = ${m.t.toFixed(2)} s`;
    } catch (err) {
      this.exportText.textContent = `import failed: ${String(err)}`;
    }
    input.value = "";
  }

  onClock(m: ClockMsg): void {
    this.paused = m.paused;
    this.play.textContent = m.paused ? "play" : "pause";
    this.rate.value = String(m.rate);
    const limit = m.limited ? ` (limited: ${m.limited}${m.reason ? `, ${m.reason}` : ""})` : "";
    this.clockText.textContent = `${m.paused ? "paused" : `${m.achievedRate.toFixed(1)}× achieved`}${limit}, step ${m.step}`;
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
      `Rewind to step ${step} (t = ${t.toFixed(2)} s)? The current timeline is kept as a branch. `,
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
      this.message.textContent = `${label}: accepted at t = ${ack.t.toFixed(2)} s`;
    } else {
      this.message.textContent = `${label}: ${describe(ack)}`;
    }
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

  dispose(): void {
    this.copilot.disconnect();
  }
}
