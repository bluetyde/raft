/**
 * A small canvas strip chart (D5: no charting dependency). It draws a StripBuffer's points
 * (bucket min and max, so peaks show) against sim time, on a linear or log scale.
 */

import type { StripBuffer } from "./strip";

export interface ChartOptions {
  label: string;
  scale: "linear" | "log";
  /** Fixed range, or null to fit the data. */
  range: [number, number] | null;
  format: (v: number) => string;
}

export class StripChart {
  readonly root: HTMLElement;
  private readonly canvas: HTMLCanvasElement;
  private readonly title: HTMLElement;

  constructor(
    readonly buffer: StripBuffer,
    readonly options: ChartOptions,
  ) {
    this.root = document.createElement("div");
    this.root.className = "vr-chart";
    this.title = document.createElement("div");
    this.title.className = "vr-chart-title";
    this.title.textContent = options.label;
    this.canvas = document.createElement("canvas");
    this.canvas.width = 300;
    this.canvas.height = 70;
    this.root.append(this.title, this.canvas);
  }

  draw(now: number): void {
    const ctx = this.canvas.getContext("2d");
    if (!ctx) return;
    const { width: w, height: h } = this.canvas;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#081524";
    ctx.fillRect(0, 0, w, h);
    const pts = this.buffer.points();
    const vals = pts.filter((p): p is [number, number] => p !== null).map(([, v]) => v);
    if (vals.length === 0) return;
    const log = this.options.scale === "log";
    const tr = (v: number) => (log ? Math.log10(Math.max(v, 1e-30)) : v);
    let [lo, hi] = this.options.range ?? [Math.min(...vals), Math.max(...vals)];
    if (log) [lo, hi] = [tr(lo), tr(hi)];
    if (hi - lo < 1e-12) [lo, hi] = [lo - 1, hi + 1];
    const t1 = now;
    const t0 = now - this.buffer.windowS;
    const x = (t: number) => ((t - t0) / (t1 - t0)) * w;
    const y = (v: number) => h - 2 - ((Math.min(hi, Math.max(lo, tr(v))) - lo) / (hi - lo)) * (h - 4);
    ctx.strokeStyle = "#7fd3a8";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let pen = false;
    for (const p of pts) {
      if (p === null) {
        pen = false;
        continue;
      }
      if (pen) ctx.lineTo(x(p[0]), y(p[1]));
      else ctx.moveTo(x(p[0]), y(p[1]));
      pen = true;
    }
    ctx.stroke();
    ctx.fillStyle = "#9fb3c8";
    ctx.font = "10px system-ui, sans-serif";
    const top = log ? 10 ** hi : hi;
    const bottom = log ? 10 ** lo : lo;
    ctx.fillText(this.options.format(top), 4, 11);
    ctx.fillText(this.options.format(bottom), 4, h - 4);
  }
}
