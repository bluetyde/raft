/**
 * Rod sequencing for the AI operator. The AI never picks a rod, a distance or a speed: this module decides which
 * step is allowed, and the runtime executes it. A step moves one rod by a small fixed travel, then stops; the
 * next step waits for power to settle. The regulating rod is not stepped: it belongs to the power controller.
 * The transient (pulse) rod is never moved by the AI.
 */

/** Travel of one step, as a fraction of the rod's full travel. */
export const STEP_TRAVEL = 0.05;
/** Least simulation time between the end of one step and the start of the next (s). */
export const STEP_SETTLE_S = 15;
/** No new withdraw step while the period is positive and shorter than this (s). */
export const WITHDRAW_MIN_PERIOD_S = 60;
/** A running withdraw step is stopped if the period is positive and shorter than this (s). */
export const ABORT_PERIOD_S = 20;
/** Power counts as "at the goal" between these fractions of it. */
export const BAND_LOW = 0.8;
export const BAND_HIGH = 1.25;
/** Above this multiple of the goal, with the period positive, the runtime hands over to the controller by itself. */
export const GUARD_FACTOR = 1.5;
/** Rods in the order they are withdrawn, and in the order they are inserted. */
export const WITHDRAW_ORDER = ["safety", "shim"];
export const INSERT_ORDER = ["shim", "safety"];
const AT_TOP = 0.99;
const AT_BOTTOM = 0.01;

export interface RodStep {
  rod: string;
  direction: "out" | "in";
  /** Position (0 = in, 1 = out) where the step ends. */
  to: number;
}

export interface SequenceContext {
  power: number;
  goal: number | null;
  /** Reactor period (s); negative when power falls. */
  period: number;
  t: number;
  rods: Record<string, { position: number }>;
  /** A protection trip is active or latched. */
  tripped: boolean;
}

export interface SequenceOffers {
  withdraw: RodStep | null;
  insert: RodStep | null;
  /** The controller may take over and hold the power where it is. */
  engage: boolean;
}

export class RodSequencer {
  /** True while the AI steps rods and the power controller is off. */
  sequencing = false;
  plan: RodStep | null = null;
  private lastEndT = -Infinity;

  reset(): void {
    this.sequencing = false;
    this.plan = null;
    this.lastEndT = -Infinity;
  }

  private settled(ctx: SequenceContext): boolean {
    return this.plan === null && ctx.t - this.lastEndT >= STEP_SETTLE_S;
  }

  /** What the AI may choose right now. All null/false without a goal: no goal, no stepping. */
  offers(ctx: SequenceContext): SequenceOffers {
    const none: SequenceOffers = { withdraw: null, insert: null, engage: false };
    if (ctx.goal === null || ctx.tripped || this.plan !== null) return none;
    const ratio = ctx.power / ctx.goal;
    // The coarse rods have no travel left: only the controller (regulating rod) can go further, so it may take over now.
    const travelLeft = (order: string[], dir: "out" | "in") =>
      order.some((id) => ctx.rods[id] !== undefined && (dir === "out" ? ctx.rods[id]!.position < AT_TOP : ctx.rods[id]!.position > AT_BOTTOM));
    const exhausted = (ratio < BAND_LOW && !travelLeft(WITHDRAW_ORDER, "out")) || (ratio > BAND_HIGH && !travelLeft(INSERT_ORDER, "in"));
    if (!this.settled(ctx)) return { ...none, engage: this.sequencing && exhausted };
    const out: SequenceOffers = { ...none };
    if (ratio < BAND_LOW && !(ctx.period > 0 && ctx.period < WITHDRAW_MIN_PERIOD_S)) {
      const rod = WITHDRAW_ORDER.find((id) => ctx.rods[id] !== undefined && ctx.rods[id]!.position < AT_TOP);
      if (rod) out.withdraw = { rod, direction: "out", to: Math.min(1, ctx.rods[rod]!.position + STEP_TRAVEL) };
    }
    if (ratio > BAND_HIGH) {
      const rod = INSERT_ORDER.find((id) => ctx.rods[id] !== undefined && ctx.rods[id]!.position > AT_BOTTOM);
      if (rod) out.insert = { rod, direction: "in", to: Math.max(0, ctx.rods[rod]!.position - STEP_TRAVEL) };
    }
    out.engage = this.sequencing && ((ratio >= BAND_LOW && ratio <= BAND_HIGH) || exhausted);
    return out;
  }

  /** The same step, if it is still offered now (a reply may be a moment old). */
  stillOffered(step: RodStep, ctx: SequenceContext): boolean {
    const o = this.offers(ctx);
    const now = step.direction === "out" ? o.withdraw : o.insert;
    return now !== null && now.rod === step.rod && Math.abs(now.to - step.to) < 1e-9;
  }

  start(step: RodStep): void {
    this.sequencing = true;
    this.plan = step;
  }

  /**
   * Called every step while a step runs. Returns why the rod must stop now, or null to keep going.
   * A step ends at its travel, when power reaches the goal, or when the period gets short.
   */
  check(ctx: SequenceContext): "done" | "goal" | "period" | "tripped" | null {
    const p = this.plan;
    if (!p) return null;
    if (ctx.tripped) return "tripped";
    const pos = ctx.rods[p.rod]?.position ?? p.to;
    if (p.direction === "out" ? pos >= p.to - 1e-9 : pos <= p.to + 1e-9) return "done";
    if (ctx.goal !== null) {
      if (p.direction === "out" && ctx.power >= ctx.goal) return "goal";
      if (p.direction === "in" && ctx.power <= ctx.goal) return "goal";
    }
    if (p.direction === "out" && ctx.period > 0 && ctx.period < ABORT_PERIOD_S) return "period";
    return null;
  }

  finish(t: number): void {
    this.plan = null;
    this.lastEndT = t;
  }

  /** Power far above the goal and still rising while no step runs: the runtime hands over to the controller. */
  needsGuard(ctx: SequenceContext): boolean {
    return this.sequencing && this.plan === null && ctx.goal !== null && ctx.power > ctx.goal * GUARD_FACTOR && ctx.period > 0;
  }
}
