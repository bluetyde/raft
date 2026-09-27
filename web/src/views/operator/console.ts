/**
 * What the operator view may read (docs/m5-operator-design.md section 2): the instrument readings
 * (`indicated`) and the console state. This module is the only place the operator view touches a
 * snapshot, so no physics truth reaches the panel.
 */

export interface RodConsole {
  position: number;
  moving: "in" | "out" | null;
}

export interface ConsoleState {
  t: number;
  /** Rod position indicators (ideal, D2): the drive state, not a physics value. */
  rods: Record<string, RodConsole>;
  mode: string;
  pumps: Record<string, boolean>;
  trips: { latched: string[]; active: string[] };
  tripped: boolean;
  validity: { status: string; reasons: string[] };
}

export interface OperatorView {
  indicated: Record<string, number | null>;
  console: ConsoleState;
}

/** The fields of `truth` the operator view may read. Everything else in `truth` is physics. */
export const CONSOLE_TRUTH_FIELDS = ["rods", "mode", "pumps"] as const;

export function consoleState(snapshot: Record<string, any>): ConsoleState {
  const truth = snapshot.truth ?? {};
  const rods: Record<string, RodConsole> = {};
  for (const [id, r] of Object.entries<any>(truth.rods ?? {})) rods[id] = { position: r.position, moving: r.moving ?? null };
  return {
    t: snapshot.t,
    rods,
    mode: truth.mode,
    pumps: { ...(truth.pumps ?? {}) },
    trips: { latched: [...(snapshot.trips?.latched ?? [])], active: [...(snapshot.trips?.active ?? [])] },
    tripped: Boolean(snapshot.tripped),
    validity: { status: snapshot.validity?.status ?? "unknown", reasons: [...(snapshot.validity?.reasons ?? [])] },
  };
}

export function operatorView(snapshot: Record<string, any>): OperatorView {
  return { indicated: { ...(snapshot.indicated ?? {}) }, console: consoleState(snapshot) };
}

/** A copy of a snapshot with every physics field of `truth` removed (for the truth-guard test). The console fields stay. */
export function stripTruthPhysics(snapshot: Record<string, any>): Record<string, any> {
  const copy = structuredClone(snapshot);
  const kept: Record<string, unknown> = {};
  for (const f of CONSOLE_TRUTH_FIELDS) if (f in (copy.truth ?? {})) kept[f] = copy.truth[f];
  copy.truth = kept;
  return copy;
}
