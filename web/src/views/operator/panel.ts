/**
 * The operator panel (M5, docs/m5-operator-design.md). Built from the library's instruments, trips,
 * interlocks, rods and modes. It reads a snapshot only through `operatorView` (instruments and console
 * state), and it sends commands through the command bus as clientId "operator".
 */

import type { Ack, RuntimeClient } from "../../runtime/client";
import { RUNTIME_REJECTIONS, type FromWorker, type ScenarioView } from "../../runtime/protocol";
import { formatPeriod, formatPower } from "../explorer/live";
import { Annunciator } from "./annunciator";
import { StripChart } from "./chart";
import { operatorView, type OperatorView } from "./console";
import { isPegged, kelvinToCelsius, meterReading, metersFrom, unitOf, type InstrumentSpec, type Meter } from "./meters";
import { PeriodEstimator } from "./period";
import { allowedTypes, formatElapsed, goalLine, scoreText } from "./scenario";
import { chartPoints, StripBuffer } from "./strip";

export interface OperatorLibrary {
  instruments: InstrumentSpec[];
  trips: { id: string }[];
  interlocks: { id: string; reason?: string }[];
  rods: { id: string; pulseCapable: boolean }[];
  modes: string[];
  /** Present when the library has soluble boron: the range the plant accepts (ppm) and the rate it moves at. */
  boron?: { range: [number, number]; maxRatePpmPerS: number };
}

type SnapshotMsg = Extract<FromWorker, { kind: "snapshot" }>;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> = {}, children: (Node | string)[] = []) {
  const e = document.createElement(tag);
  Object.assign(e, props);
  for (const c of children) e.append(c);
  return e;
}

function display(m: Meter, v: number): string {
  if (m.role === "power") return formatPower(v);
  if (unitOf(m.role) === "°C") return `${kelvinToCelsius(v).toFixed(1)} °C`;
  return v.toPrecision(4);
}

const RATES = [0.1, 1, 10, 100];
const SCRAM_COVER_MS = 5000;

import { JevCopilot, createCopilotButton, describeSupervision } from "../copilot";
import { createValidityBanner } from "../validity";

export class OperatorPanel {
  readonly root: HTMLElement;
  readonly meters: Meter[];
  readonly periodSource: Meter | null;
  readonly period = new PeriodEstimator();
  readonly annunciator: Annunciator;
  readonly charts: { meter: Meter | "period"; buffer: StripBuffer; chart: StripChart }[] = [];
  private readonly copilot: JevCopilot;
  private readonly meterEls = new Map<string, { bar: HTMLElement; value: HTMLElement; flag: HTMLElement }>();
  private readonly periodEl: HTMLElement;
  private readonly rodEls = new Map<string, { pos: HTMLElement; down: HTMLElement; up: HTMLElement; fire?: HTMLButtonElement }>();
  private readonly tileBox: HTMLElement;
  private readonly message: HTMLElement;
  private readonly mode: HTMLSelectElement;
  private readonly scramCover: HTMLButtonElement;
  private readonly scram: HTMLButtonElement;
  private coverTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly play: HTMLButtonElement;
  private readonly clockText: HTMLElement;
  private readonly rate: HTMLSelectElement;
  private paused = true;
  private lastT = -Infinity;
  /** The last view the panel drew (for tests: the panel never holds more than this). */
  lastView: OperatorView | null = null;
  /** The running scenario as the worker last sent it (goal statuses only), or null. */
  scenario: ScenarioView | null = null;
  private readonly scenarioBox: HTMLElement;
  private readonly elapsed: HTMLElement;
  /** Each control with the command type it sends, so a scenario's allowed controls can disable the others (D7a). */
  private readonly controls: { el: HTMLButtonElement | HTMLSelectElement | HTMLInputElement; type: string }[] = [];
  private boronReading: HTMLElement | null = null;
  private boronInput: HTMLInputElement | null = null;
  private boronInputTouched = false;
  /** Whether an instructor fault was active at the last snapshot (for the faultsVisible tile). */
  private faultActive = false;

  constructor(
    private readonly client: RuntimeClient,
    private readonly lib: OperatorLibrary,
    /** timeControls: false in an operator window, where the instructor sets the time (the worker refuses it anyway). */
    private readonly opts: { timeControls?: boolean } = {},
  ) {
    this.meters = metersFrom(lib.instruments);
    const power = this.meters.filter((m) => m.role === "power");
    this.periodSource = power.find((m) => m.scale === "log") ?? power[0] ?? null;
    this.annunciator = new Annunciator(
      ["manual", ...lib.trips.map((t) => t.id).filter((id) => id !== "manual")], // a manual SCRAM latches "manual
      this.meters.map((m) => m.id),
      lib.interlocks,
    );

    const meterRows = this.meters.map((m) => {
      const bar = el("div", { className: "vr-bar-fill" });
      const value = el("span", { className: "vr-value" });
      const flag = el("span", { className: "vr-flag" });
      this.meterEls.set(m.id, { bar, value, flag });
      const row = el("div", { className: "vr-meter" }, [
        el("span", { className: "vr-meter-name", textContent: `${m.id} (${m.scale})` }),
        el("div", { className: "vr-bar-track" }, [bar]),
        value,
        flag,
      ]);
      row.dataset["meter"] = m.id;
      return row;
    });
    this.periodEl = el("span", { className: "vr-value", textContent: "—" });
    const periodRow = el("div", { className: "vr-meter" }, [
      el("span", {
        className: "vr-meter-name",
        textContent: "period",
        title: this.periodSource
          ? `Derived from ${this.periodSource.id}: least-squares slope over ${this.period.options.windowS} s of sim time. "—" in pulse mode or with too few readings.`
          : "No power channel to derive it from.",
      }),
      this.periodEl,
    ]);
    periodRow.dataset["meter"] = "period";

    const rodRows = lib.rods.map((r) => {
      const pos = el("span", { className: "vr-pos", textContent: "–" });
      const down = el("span", { className: "vr-light", textContent: "rod down" });
      down.dataset["light"] = `${r.id}:down`;
      const up = el("span", { className: "vr-light", textContent: "up limit" });
      up.dataset["light"] = `${r.id}:up`;
      const b = (label: string, cmd: Record<string, unknown>, op: string) => {
        const btn = el("button", { textContent: label, onclick: () => void this.send(cmd) });
        btn.dataset["op"] = `${r.id}:${op}`;
        this.controls.push({ el: btn, type: String(cmd["type"]) });
        return btn;
      };
      const buttons = [
        b("▼ in", { type: "rod.move", rod: r.id, direction: "in" }, "in"),
        b("■", { type: "rod.move", rod: r.id, direction: "stop" }, "stop"),
        b("▲ out", { type: "rod.move", rod: r.id, direction: "out" }, "out"),
      ];
      let fire: HTMLButtonElement | undefined;
      if (r.pulseCapable) {
        fire = b("FIRE", { type: "rod.fire", rod: r.id }, "fire");
        buttons.push(fire);
      }
      this.rodEls.set(r.id, { pos, down, up, ...(fire ? { fire } : {}) });
      return el("div", { className: "vr-rodrow" }, [
        el("span", { className: "vr-rodname", textContent: r.id }),
        pos,
        down,
        up,
        ...buttons,
      ]);
    });

    this.mode = el("select", {}, lib.modes.map((m) => el("option", { value: m, textContent: m })));
    this.mode.dataset["op"] = "mode";
    this.mode.onchange = () => void this.send({ type: "mode.set", mode: this.mode.value });

    this.scramCover = el("button", { textContent: "lift SCRAM cover", className: "vr-cover", onclick: () => this.openCover() });
    this.scramCover.dataset["op"] = "scram-cover";
    this.scram = el("button", { textContent: "SCRAM", className: "vr-scram", onclick: () => this.pressScram() });
    this.scram.dataset["op"] = "scram";
    this.scram.hidden = true;
    const reset = el("button", { textContent: "reset trips", onclick: () => void this.send({ type: "trip.reset" }) });
    reset.dataset["op"] = "reset";
    this.controls.push({ el: this.mode, type: "mode.set" }, { el: reset, type: "trip.reset" }, { el: this.scramCover, type: "scram" }, { el: this.scram, type: "scram" });

    let boronSection: HTMLElement | null = null;
    if (lib.boron) {
      const [lo, hi] = lib.boron.range;
      this.boronReading = el("span", { className: "vr-value", textContent: "–" });
      this.boronReading.dataset["op"] = "boron-reading";
      this.boronInput = el("input", { type: "number", min: String(lo), max: String(hi), step: "1" });
      this.boronInput.dataset["op"] = "boron-input";
      this.boronInput.oninput = () => (this.boronInputTouched = true);
      const setBtn = el("button", {
        textContent: "set boron",
        onclick: () => {
          const ppm = Number(this.boronInput!.value);
          if (this.boronInput!.value === "" || !Number.isFinite(ppm)) {
            this.message.textContent = "enter a boron concentration in ppm";
            return;
          }
          this.boronInputTouched = false;
          void this.send({ type: "boron.set", ppm });
        },
      });
      setBtn.dataset["op"] = "boron-set";
      this.controls.push({ el: this.boronInput, type: "boron.set" }, { el: setBtn, type: "boron.set" });
      boronSection = el("section", { className: "vr-row" }, [
        el("h3", { textContent: "Boron" }),
        this.boronReading,
        el("span", { className: "vr-note", textContent: `(${lo} to ${hi} ppm, moves at ${lib.boron.maxRatePpmPerS} ppm/s)` }),
        this.boronInput,
        setBtn,
      ]);
    }

    this.elapsed = el("span", { className: "vr-scn-elapsed" });
    this.elapsed.dataset["op"] = "scenario-elapsed";
    this.scenarioBox = el("section", { className: "vr-scenario", hidden: true });
    this.scenarioBox.dataset["op"] = "scenario";

    this.tileBox = el("div", { className: "vr-tiles" });
    const ack = el("button", { textContent: "acknowledge", onclick: () => this.acknowledge() });
    ack.dataset["op"] = "ack";

    this.play = el("button", { textContent: "▶ run", onclick: () => this.client.setTime({ paused: !this.paused }) });
    this.play.dataset["op"] = "play";
    const rate = el("select", {}, RATES.map((r) => el("option", { value: String(r), textContent: `${r}×` })));
    this.rate = rate;
    rate.value = "1";
    rate.dataset["op"] = "rate";
    rate.onchange = () => this.client.setTime({ rate: Number(rate.value) });
    this.clockText = el("span", { className: "vr-opclock" });

    const chartSources: (Meter | "period")[] = [...power, "period", ...this.meters.filter((m) => m.role === "fuelTemp").slice(0, 1)];
    for (const src of chartSources) {
      const buffer = new StripBuffer(600, 3000);
      const chart =
        src === "period"
          ? new StripChart(buffer, { label: "period (s, last 10 min)", scale: "linear", range: [-60, 60], format: (v) => `${v.toFixed(0)} s` })
          : new StripChart(buffer, {
              label: `${src.id} (last 10 min)`,
              scale: src.scale,
              range: src.range,
              format: (v) => display(src, v),
            });
      this.charts.push({ meter: src, buffer, chart });
    }

    this.message = el("div", { className: "vr-note" });
    this.copilot = new JevCopilot(client, "operator");
    const copilotBtn = createCopilotButton(this.copilot);

    const aiStatus = el("div", { className: "vr-note" });
    aiStatus.dataset["op"] = "ai-status";
    client.on("supervision", (m) => {
      aiStatus.textContent = describeSupervision(m.state) + (m.state.lastAction ? ` - last: ${m.state.lastAction}` : "");
    });

    const hdr = el("div", { className: "vr-row" }, [
      el("h2", { textContent: "Operator Panel" }),
      copilotBtn
    ]);
    hdr.style.justifyContent = "space-between";
    hdr.style.marginBottom = "10px";

    this.root = el("div", { className: "vr-operator" }, [
      hdr,
      createValidityBanner(client),
      aiStatus,
      this.scenarioBox,
      el("section", {}, [el("h3", { textContent: "Instruments" }), ...meterRows, periodRow]),
      el("section", {}, [el("h3", { textContent: "Annunciator" }), this.tileBox, ack]),
      el("section", {}, [el("h3", { textContent: "Rods" }), ...rodRows]),
      ...(boronSection ? [boronSection] : []),
      el("section", { className: "vr-row" }, [el("label", {}, ["mode ", this.mode]), reset, this.scramCover, this.scram]),
      el("section", {}, [el("h3", { textContent: "Strip charts" }), ...this.charts.map((c) => c.chart.root)]),
      el(
        "section",
        { className: "vr-row" },
        this.opts.timeControls === false
          ? [el("span", { className: "vr-note", textContent: "time (set by the instructor):" }), this.clockText]
          : [el("span", { className: "vr-note", textContent: "time (instructor):" }), this.play, rate, this.clockText],
      ),
      this.message,
    ]);
    window.addEventListener("keydown", this.onKey);
    this.renderTiles();
  }

  private onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") this.closeCover();
  };

  private openCover(): void {
    this.scramCover.hidden = true;
    this.scram.hidden = false;
    if (this.coverTimer) clearTimeout(this.coverTimer);
    this.coverTimer = setTimeout(() => this.closeCover(), SCRAM_COVER_MS);
  }

  private closeCover(): void {
    if (this.coverTimer) clearTimeout(this.coverTimer);
    this.coverTimer = null;
    this.scramCover.hidden = false;
    this.scram.hidden = true;
  }

  private pressScram(): void {
    void this.send({ type: "scram", reason: "operator" });
    this.closeCover();
  }

  private acknowledge(): void {
    this.annunciator.acknowledge();
    this.renderTiles();
  }

  private async send(cmd: Record<string, unknown>): Promise<Ack> {
    const ack = await this.client.command(cmd, undefined, "operator");
    const what = String(cmd["type"]);
    if (ack.status === "rejected") {
      const reason = ack.reason ?? "";
      const il = /^REJ_INTERLOCK:(.+)$/.exec(reason);
      const text = il ? this.lib.interlocks.find((x) => x.id === il[1])?.reason : RUNTIME_REJECTIONS[reason];
      this.annunciator.interlockRejected(reason, text);
      this.renderTiles();
      this.message.textContent = `${what} rejected: ${reason}${text ? ` (${text})` : ""}`;
    } else {
      this.message.textContent = `${what} accepted`;
    }
    return ack;
  }

  onClock(m: Extract<FromWorker, { kind: "clock" }>): void {
    this.paused = m.paused;
    this.play.textContent = m.paused ? "▶ run" : "⏸ pause";
    // the rate can also come from the instructor panel, so the menu follows the clock (and gains that rate if it lacks it)
    const rate = String(m.rate);
    if (![...this.rate.options].some((o) => o.value === rate)) this.rate.append(new Option(`${m.rate}×`, rate));
    this.rate.value = rate;
    this.clockText.textContent = m.paused ? "paused" : `${m.achievedRate.toPrecision(3)}× achieved`;
  }

  /** After a rewind or a session import: the alarm history belongs to another timeline. */
  onRewound(replaced = false): void {
    this.annunciator.reset();
    this.period.reset();
    // a switched or imported timeline is another history: the old readings must not stay on the charts
    if (replaced) for (const c of this.charts) c.buffer.dropAfter(-Infinity);
    this.renderTiles();
  }

  onSnapshot(msg: SnapshotMsg): void {
    const view = operatorView(msg.snapshot);
    this.lastView = view;
    const t = view.console.t;
    if (t < this.lastT) this.onRewound();
    this.lastT = t;

    // meters
    const states: { id: string; failed: boolean; pegged: boolean }[] = [];
    for (const m of this.meters) {
      const v = view.indicated[m.id];
      const r = meterReading(m, v);
      const e = this.meterEls.get(m.id)!;
      e.bar.style.width = `${(100 * r.fraction).toFixed(1)}%`;
      e.value.textContent = r.failed ? "FAILED" : display(m, v!);
      e.flag.textContent = r.peg === "over" ? "OVER" : r.peg === "under" ? "UNDER" : "";
      states.push({ id: m.id, failed: r.failed, pegged: r.peg !== null });
    }

    // period (amendment 2): extremes are not used here; they are not evenly spaced readings
    if (this.periodSource) {
      const v = view.indicated[this.periodSource.id];
      this.period.push(t, v, isPegged(this.periodSource, v));
    }
    const p = this.period.read(view.console.mode);
    this.periodEl.textContent = p === null ? "—" : formatPeriod(p);

    // charts (amendment 1): the extremes since the last snapshot, then the current reading
    for (const c of this.charts) {
      if (c.meter === "period") {
        c.buffer.push(t, p === null || !Number.isFinite(p) ? null : Math.max(-60, Math.min(60, p)));
        continue;
      }
      const id = c.meter.id;
      for (const [tt, v] of chartPoints(t, view.indicated[id], msg.extremes?.[id])) c.buffer.push(tt, v);
    }
    for (const c of this.charts) c.chart.draw(t);

    // rods, mode, alarms
    for (const [id, r] of Object.entries(view.console.rods)) {
      const e = this.rodEls.get(id);
      if (!e) continue;
      e.pos.textContent = `${(100 * r.position).toFixed(1)} %${r.moving ? (r.moving === "out" ? " ▲" : " ▼") : ""}`;
      e.down.classList.toggle("on", r.position <= 1e-6);
      e.up.classList.toggle("on", r.position >= 1 - 1e-6);
      if (e.fire) e.fire.disabled = view.console.mode !== "pulse" || !this.allows("rod.fire");
    }
    if (this.mode.value !== view.console.mode) this.mode.value = view.console.mode;
    if (this.boronReading && view.console.boron) {
      const b = view.console.boron;
      this.boronReading.textContent = `${b.ppm.toFixed(1)} ppm${b.target !== null ? ` → ${b.target.toFixed(0)}` : ""}`;
      if (this.boronInput && !this.boronInputTouched && document.activeElement !== this.boronInput) this.boronInput.value = (b.target ?? b.ppm).toFixed(0);
    }
    this.annunciator.update(view.console.trips, states);
    // a scenario with faultsVisible shows one tile while an instructor fault is active (M6 D4b); otherwise there is no tile
    const f = msg.faults;
    this.faultActive = f !== undefined && (Object.keys(f.instruments).length > 0 || Math.abs(f.extraRho) > 1e-15);
    this.annunciator.instructorFault(this.scenario?.faultsVisible === true, this.faultActive);
    this.renderTiles();
    if (this.scenario) this.elapsed.textContent = `elapsed ${formatElapsed(t)}`;
  }

  private allows(type: string): boolean {
    const allowed = allowedTypes(this.scenario);
    return allowed === null || allowed.has(type);
  }

  /** The worker's scenario view (D7a): the strip, and the controls the scenario allows. Null when no scenario runs. */
  onScenario(v: ScenarioView | null): void {
    this.scenario = v;
    for (const c of this.controls) {
      const ok = this.allows(c.type);
      c.el.disabled = !ok;
      c.el.title = ok ? "" : "not allowed in this scenario";
    }
    // the scenario message can come after the snapshot, so the tile is set here too (with the last snapshot's faults)
    this.annunciator.instructorFault(v?.faultsVisible === true, this.faultActive);
    this.renderTiles();
    if (!v) {
      this.scenarioBox.hidden = true;
      this.scenarioBox.replaceChildren();
      return;
    }
    const hints = el("ul", { className: "vr-scn-hints", hidden: true }, v.hints.map((h) => el("li", { textContent: h })));
    hints.dataset["op"] = "scenario-hints";
    const hintButton = el("button", {
      textContent: `hints (${v.hints.length})`,
      disabled: v.hints.length === 0,
      onclick: () => (hints.hidden = !hints.hidden),
    });
    hintButton.dataset["op"] = "scenario-hint-toggle";
    const goals = el(
      "ol",
      { className: "vr-scn-goals" },
      v.goals.map((g) => {
        const li = el("li", { className: g.status, textContent: goalLine(g) });
        li.dataset["goal"] = g.id;
        li.dataset["status"] = g.status;
        return li;
      }),
    );
    const score = scoreText(v);
    const scoreEl = el("div", { className: "vr-scn-score", textContent: score ?? "", hidden: score === null });
    scoreEl.dataset["op"] = "scenario-score";
    this.scenarioBox.hidden = false;
    this.scenarioBox.replaceChildren(
      el("h3", { textContent: `Scenario: ${v.title}` }),
      el("p", { className: "vr-scn-brief", textContent: v.brief }),
      goals,
      el("div", { className: "vr-row" }, [hintButton, this.elapsed]),
      hints,
      scoreEl,
    );
  }

  private renderTiles(): void {
    this.tileBox.replaceChildren(
      ...this.annunciator.list().map((tile) => {
        const d = el("div", { className: `vr-tile ${tile.state}`, textContent: tile.label, title: tile.detail ?? "" });
        d.dataset["tile"] = tile.id;
        d.dataset["state"] = tile.state;
        return d;
      }),
    );
  }

  dispose(): void {
    window.removeEventListener("keydown", this.onKey);
    this.closeCover();
    this.copilot.disconnect();
  }
}
