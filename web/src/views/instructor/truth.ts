/**
 * The instructor's truth panel (docs/m6-instructor-design.md §3): exact values from `snapshot.truth`,
 * each instrument's reading next to the true value it measures, and the reactivity by source.
 * Only the instructor and explorer views may read truth (ARCHITECTURE §2).
 */

import type { ActiveFaults } from "../../runtime/protocol";
import { formatPower } from "../explorer/live";
import { kelvinToCelsius } from "../operator/meters";

/** 1 pcm = 1e-5 in reactivity. */
export const PCM = 1e-5;

export const REACTIVITY_SOURCES = ["reference", "calibration", "rods", "fuel", "coolant", "xenon", "fault"] as const;

export interface ReactivityBar {
  source: string;
  pcm: number;
  /** Bar length from 0 to 1, relative to the largest source. */
  size: number;
}

export function reactivityBars(reactivity: Record<string, number>): { bars: ReactivityBar[]; totalPcm: number } {
  const values = REACTIVITY_SOURCES.map((s) => ({ source: s, pcm: (reactivity[s] ?? 0) / PCM }));
  const largest = Math.max(1e-12, ...values.map((v) => Math.abs(v.pcm)));
  return {
    bars: values.map((v) => ({ ...v, size: Math.abs(v.pcm) / largest })),
    totalPcm: (reactivity["total"] ?? 0) / PCM,
  };
}

export interface InstrumentRow {
  id: string;
  signal: string;
  indicated: number | null;
  truth: number | null;
  fault: string | null;
}

/** Each instrument's reading next to the true value of its signal (for example `truth.power`), and its fault. */
export function instrumentRows(
  instruments: { id: string; signal: string }[],
  snapshot: Record<string, any>,
  faults: ActiveFaults | undefined,
): InstrumentRow[] {
  return instruments.map((ins) => {
    const key = ins.signal.startsWith("truth.") ? ins.signal.slice("truth.".length) : null;
    const v = key !== null ? snapshot["truth"]?.[key] : undefined;
    return {
      id: ins.id,
      signal: ins.signal,
      indicated: snapshot["indicated"]?.[ins.id] ?? null,
      truth: typeof v === "number" ? v : null,
      fault: faults?.instruments[ins.id] ?? null,
    };
  });
}

/** A value of a signal as the truth panel shows it: power in W, temperatures in °C, others with 5 digits. */
export function formatSignal(signal: string, v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  if (signal === "truth.power") return formatPower(v);
  if (signal === "truth.fuelTemp" || signal === "truth.coolantTemp") return `${kelvinToCelsius(v).toFixed(2)} °C`;
  return v.toPrecision(5);
}

/** A reactivity in pcm with one decimal, without "-0.0". */
export function formatPcm(pcm: number): string {
  const text = pcm.toFixed(1);
  return text === "-0.0" ? "0.0" : text;
}

/** The active faults as short lines: instrument faults, inserted reactivity, and pumps that are off. */
export function activeFaultLines(faults: ActiveFaults | undefined, pumps: Record<string, boolean> | undefined): string[] {
  const out: string[] = [];
  for (const [id, kind] of Object.entries(faults?.instruments ?? {}).sort(([a], [b]) => a.localeCompare(b))) out.push(`instrument ${id}: ${kind}`);
  if (faults && Math.abs(faults.extraRho) > 1e-15) out.push(`reactivity inserted: ${formatPcm(faults.extraRho / PCM)} pcm`);
  for (const [id, on] of Object.entries(pumps ?? {})) if (!on) out.push(`pump ${id}: off`);
  return out;
}
