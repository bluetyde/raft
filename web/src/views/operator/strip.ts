/**
 * Strip-chart buffer (section 5 and amendment 1): the last `windowS` of sim time, in buckets of
 * `windowS / buckets`. Each bucket keeps its minimum and maximum (with their times), so a short
 * peak survives at full height however much the buffer thins. Null readings leave a gap.
 */

export interface Bucket {
  /** Bucket start, s of sim time. */
  t0: number;
  min: number;
  tMin: number;
  max: number;
  tMax: number;
}

interface Gap {
  gap: true;
  t: number;
}

/** A point to draw, or a gap. */
export type StripPoint = [t: number, v: number] | null;

function latest(item: Bucket | Gap): number {
  return "gap" in item ? item.t : Math.max(item.tMin, item.tMax);
}

export class StripBuffer {
  private items: (Bucket | Gap)[] = [];
  readonly width: number;

  constructor(
    readonly windowS = 600,
    readonly buckets = 3000,
  ) {
    this.width = windowS / buckets;
  }

  /** Add a reading. A null or non-finite reading adds a gap. A time earlier than the latest drops what came after it (a rewind). */
  push(t: number, v: number | null | undefined): void {
    const last = this.items.at(-1);
    if (last && t < latest(last)) this.dropAfter(t);
    const tail = this.items.at(-1);
    if (v === null || v === undefined || !Number.isFinite(v)) {
      if (!tail || !("gap" in tail)) this.items.push({ gap: true, t });
      return;
    }
    const t0 = Math.floor(t / this.width) * this.width;
    if (tail && !("gap" in tail) && tail.t0 === t0) {
      if (v < tail.min) {
        tail.min = v;
        tail.tMin = t;
      }
      if (v > tail.max) {
        tail.max = v;
        tail.tMax = t;
      }
    } else {
      this.items.push({ t0, min: v, tMin: t, max: v, tMax: t });
    }
    this.trim(t);
  }

  /** Remove everything recorded after sim time t (that timeline is gone after a rewind). */
  dropAfter(t: number): void {
    this.items = this.items.filter((b) => latest(b) <= t);
  }

  private trim(now: number): void {
    const from = now - this.windowS;
    while (this.items.length > 0 && latest(this.items[0]!) < from) this.items.shift();
    while (this.items.length > this.buckets * 2) this.items.shift(); // hard bound, gaps included
  }

  /** Points to draw, oldest first: each bucket's min and max in time order, and null for a gap. */
  points(): StripPoint[] {
    const out: StripPoint[] = [];
    for (const b of this.items) {
      if ("gap" in b) out.push(null);
      else if (b.tMin === b.tMax) out.push(...((b.min === b.max ? [[b.tMin, b.min]] : [[b.tMin, b.min], [b.tMax, b.max]]) as StripPoint[]));
      else if (b.tMin < b.tMax) out.push([b.tMin, b.min], [b.tMax, b.max]);
      else out.push([b.tMax, b.max], [b.tMin, b.min]);
    }
    return out;
  }

  get bucketCount(): number {
    return this.items.filter((b) => !("gap" in b)).length;
  }

  get size(): number {
    return this.items.length;
  }

  /** The highest value kept. */
  get max(): number {
    let m = -Infinity;
    for (const b of this.items) if (!("gap" in b)) m = Math.max(m, b.max);
    return m;
  }
}
