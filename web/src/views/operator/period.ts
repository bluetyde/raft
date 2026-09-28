/**
 * Period meter derived from a log power channel (D3): a least-squares slope of ln(reading) over a
 * sliding window of sim time. Amendment 2: skip null and pegged readings and points from before a
 * rewind; show nothing ("—") when too few points remain or in pulse mode.
 * With the libraries' log-channel noise (1–2 % per reading), a 2 s window measures periods of a few
 * seconds to tens of seconds. A slope smaller than three times its standard error reads as steady (∞).
 */

export interface PeriodOptions {
  /** Window length, s of sim time. */
  windowS: number;
  /** Fewest points in the window for a reading. */
  minPoints: number;
  /** The points must span at least this fraction of the window. */
  minSpanFraction: number;
}

export const DEFAULT_PERIOD_OPTIONS: PeriodOptions = { windowS: 2, minPoints: 8, minSpanFraction: 0.5 };

/** A period in s, or `null` for "—" (no reading). `Infinity` means steady (no measurable slope). */
export type PeriodReading = number | null;

export class PeriodEstimator {
  private pts: [t: number, lnP: number][] = [];
  readonly options: PeriodOptions;

  constructor(options: Partial<PeriodOptions> = {}) {
    this.options = { ...DEFAULT_PERIOD_OPTIONS, ...options };
  }

  /** Forget every point, for example after a rewind or a new session. */
  reset(): void {
    this.pts = [];
  }

  /**
   * Add a reading at sim time t. `pegged` readings and nulls are skipped (their value is not the power).
   * A time earlier than the last point means a rewind: the older points belong to another timeline, so they go.
   */
  push(t: number, reading: number | null | undefined, pegged: boolean): void {
    const last = this.pts.at(-1);
    if (last && t < last[0]) this.pts = [];
    if (last && t === last[0]) return; // the same snapshot twice
    const from = t - this.options.windowS;
    while (this.pts.length > 0 && this.pts[0]![0] < from) this.pts.shift();
    if (reading === null || reading === undefined || !Number.isFinite(reading) || reading <= 0 || pegged) return;
    this.pts.push([t, Math.log(reading)]);
  }

  /** The period, or null ("—") when there are too few points or the reactor is in pulse mode. */
  read(mode: string): PeriodReading {
    if (mode === "pulse") return null;
    const n = this.pts.length;
    if (n < this.options.minPoints) return null;
    const span = this.pts[n - 1]![0] - this.pts[0]![0];
    if (span < this.options.minSpanFraction * this.options.windowS) return null;
    let st = 0;
    let sy = 0;
    for (const [t, y] of this.pts) {
      st += t;
      sy += y;
    }
    const mt = st / n;
    const my = sy / n;
    let sxx = 0;
    let sxy = 0;
    for (const [t, y] of this.pts) {
      sxx += (t - mt) * (t - mt);
      sxy += (t - mt) * (y - my);
    }
    const slope = sxy / sxx; // 1/s
    if (!Number.isFinite(slope)) return Infinity;
    // The slope's standard error from the scatter about the line. A slope smaller than three times its
    // error is not a measurable period (noise on a slow change), so the meter reads steady instead of jumping.
    // (2 sigma let about 10 % of noise-only windows through as long, random periods.)
    let ss = 0;
    for (const [t, y] of this.pts) {
      const r = y - my - slope * (t - mt);
      ss += r * r;
    }
    const se = n > 2 ? Math.sqrt(ss / (n - 2) / sxx) : Infinity;
    if (Math.abs(slope) < Math.max(1e-6, 3 * se)) return Infinity;
    return 1 / slope;
  }

  get size(): number {
    return this.pts.length;
  }
}
