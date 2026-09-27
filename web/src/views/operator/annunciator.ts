/**
 * Annunciator (D1): tiles derived in the view, one per library trip, per instrument failure and
 * over-range, and one for interlock rejections of this view's own commands.
 * Sequence per tile: a new alarm flashes until acknowledged; an acknowledged alarm stays lit while its
 * condition holds; an alarm whose condition cleared before it was acknowledged keeps flashing until
 * acknowledged, then goes off.
 * Interlock-rejection tiles come from command acknowledgements, so they are not in replays.
 */

export type TileState = "off" | "flashing" | "lit";

export interface Tile {
  id: string;
  label: string;
  kind: "trip" | "failed" | "range" | "interlock";
  state: TileState;
  /** For interlock tiles: the reason text of the last rejection. */
  detail?: string;
}

interface Internal extends Tile {
  active: boolean;
  acked: boolean;
}

export class Annunciator {
  private tiles = new Map<string, Internal>();

  constructor(tripIds: string[], instrumentIds: string[], interlocks: { id: string }[]) {
    for (const id of tripIds) this.add(`trip:${id}`, `trip ${id}`, "trip");
    for (const id of instrumentIds) {
      this.add(`failed:${id}`, `${id} failed`, "failed");
      this.add(`range:${id}`, `${id} out of range`, "range");
    }
    for (const il of interlocks) this.add(`interlock:${il.id}`, `interlock ${il.id}`, "interlock");
  }

  private add(id: string, label: string, kind: Tile["kind"]): void {
    this.tiles.set(id, { id, label, kind, state: "off", active: false, acked: true });
  }

  private set(id: string, active: boolean): void {
    const t = this.tiles.get(id);
    if (!t) return;
    if (active && !t.active) t.acked = false; // a new alarm
    t.active = active;
    t.state = !t.acked ? "flashing" : active ? "lit" : "off";
  }

  /** Update the condition tiles from one operator view. */
  update(trips: { latched: string[]; active: string[] }, instruments: { id: string; failed: boolean; pegged: boolean }[]): void {
    const on = new Set([...trips.latched, ...trips.active]);
    for (const t of this.tiles.values()) if (t.kind === "trip") this.set(t.id, on.has(t.id.slice(5)));
    for (const i of instruments) {
      this.set(`failed:${i.id}`, i.failed);
      this.set(`range:${i.id}`, i.pegged);
    }
  }

  /** An own command was rejected with REJ_INTERLOCK:<id>. The tile flashes until acknowledged, then goes off (an event, not a condition). */
  interlockRejected(reason: string, detail?: string): void {
    const m = /^REJ_INTERLOCK:(.+)$/.exec(reason);
    if (!m) return;
    const t = this.tiles.get(`interlock:${m[1]}`);
    if (!t) return;
    t.active = false;
    t.acked = false;
    t.state = "flashing";
    if (detail !== undefined) t.detail = detail;
  }

  /** Acknowledge every flashing tile. */
  acknowledge(): void {
    for (const t of this.tiles.values()) {
      t.acked = true;
      t.state = t.active ? "lit" : "off";
    }
  }

  /** Forget alarm history, for example after a rewind or a new session (conditions come back with the next update). */
  reset(): void {
    for (const t of this.tiles.values()) {
      t.active = false;
      t.acked = true;
      t.state = "off";
      delete t.detail;
    }
  }

  list(): Tile[] {
    return [...this.tiles.values()].map(({ id, label, kind, state, detail }) => ({ id, label, kind, state, ...(detail ? { detail } : {}) }));
  }
}
