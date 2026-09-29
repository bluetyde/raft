import { describe, expect, it } from "vitest";
import { ABORT_PERIOD_S, RodSequencer, STEP_SETTLE_S, STEP_TRAVEL, type SequenceContext } from "./sequencer";

const ctx = (over: Partial<SequenceContext> = {}): SequenceContext => ({
  power: 1,
  goal: 10,
  period: 1e9,
  t: 100,
  rods: { safety: { position: 0.5 }, shim: { position: 0.5 }, regulating: { position: 0.5 }, transient: { position: 0 } },
  tripped: false,
  ...over,
});

describe("RodSequencer offers", () => {
  it("offers nothing without a goal, or while tripped", () => {
    const s = new RodSequencer();
    expect(s.offers(ctx({ goal: null }))).toEqual({ withdraw: null, insert: null, engage: false });
    expect(s.offers(ctx({ tripped: true })).withdraw).toBeNull();
  });

  it("below the goal: withdraws safety first, then shim, never regulating or transient", () => {
    const s = new RodSequencer();
    expect(s.offers(ctx()).withdraw).toEqual({ rod: "safety", direction: "out", to: 0.5 + STEP_TRAVEL });
    const safetyFull = ctx({ rods: { safety: { position: 1 }, shim: { position: 0.2 }, regulating: { position: 0 }, transient: { position: 0 } } });
    expect(s.offers(safetyFull).withdraw).toEqual({ rod: "shim", direction: "out", to: 0.2 + STEP_TRAVEL });
    const allFull = ctx({ rods: { safety: { position: 1 }, shim: { position: 1 }, regulating: { position: 0 }, transient: { position: 0 } } });
    expect(s.offers(allFull).withdraw).toBeNull();
  });

  it("does not withdraw while the period is short and positive, or before power settles", () => {
    const s = new RodSequencer();
    expect(s.offers(ctx({ period: 30 })).withdraw).toBeNull();
    expect(s.offers(ctx({ period: -30 })).withdraw).not.toBeNull();
    s.start({ rod: "safety", direction: "out", to: 0.55 });
    s.finish(100);
    expect(s.offers(ctx({ t: 100 + STEP_SETTLE_S - 1 })).withdraw).toBeNull();
    expect(s.offers(ctx({ t: 100 + STEP_SETTLE_S })).withdraw).not.toBeNull();
  });

  it("above the goal: inserts shim first, then safety, and stops at the bottom", () => {
    const s = new RodSequencer();
    const high = ctx({ power: 100 });
    expect(s.offers(high).insert).toEqual({ rod: "shim", direction: "in", to: 0.5 - STEP_TRAVEL });
    const shimIn = ctx({ power: 100, rods: { safety: { position: 0.3 }, shim: { position: 0 }, regulating: { position: 0.5 }, transient: { position: 0 } } });
    expect(s.offers(shimIn).insert?.rod).toBe("safety");
    const allIn = ctx({ power: 100, rods: { safety: { position: 0 }, shim: { position: 0 }, regulating: { position: 0.5 }, transient: { position: 0 } } });
    expect(s.offers(allIn).insert).toBeNull();
  });

  it("offers the hand-over only while sequencing and near the goal", () => {
    const s = new RodSequencer();
    expect(s.offers(ctx({ power: 10 })).engage).toBe(false); // not sequencing
    s.sequencing = true;
    expect(s.offers(ctx({ power: 10 })).engage).toBe(true);
    expect(s.offers(ctx({ power: 1 })).engage).toBe(false);
    expect(s.offers(ctx({ power: 100 })).engage).toBe(false);
  });

  it("offers the controller when the coarse rods have no travel left", () => {
    const s = new RodSequencer();
    s.sequencing = true;
    const full = { safety: { position: 1 }, shim: { position: 1 }, regulating: { position: 0 }, transient: { position: 0 } };
    const o = s.offers(ctx({ power: 1, rods: full }));
    expect(o.withdraw).toBeNull();
    expect(o.engage).toBe(true); // below the goal, nothing left to withdraw: the regulating rod is the controller's
    const notExhausted = s.offers(ctx({ power: 1 }));
    expect(notExhausted.engage).toBe(false);
  });

  it("a stale reply is refused: the step must still be the offered one", () => {
    const s = new RodSequencer();
    const step = s.offers(ctx()).withdraw!;
    expect(s.stillOffered(step, ctx())).toBe(true);
    expect(s.stillOffered(step, ctx({ period: 10 }))).toBe(false);
    expect(s.stillOffered({ ...step, rod: "transient" }, ctx())).toBe(false);
  });
});

describe("RodSequencer step and guard", () => {
  const start = () => {
    const s = new RodSequencer();
    s.start({ rod: "safety", direction: "out", to: 0.55 });
    return s;
  };

  it("ends at its travel, at the goal, on a short period, or on a trip", () => {
    expect(start().check(ctx({ rods: { safety: { position: 0.5 } } }))).toBeNull();
    expect(start().check(ctx({ rods: { safety: { position: 0.55 } } }))).toBe("done");
    expect(start().check(ctx({ power: 10 }))).toBe("goal");
    expect(start().check(ctx({ period: ABORT_PERIOD_S - 1 }))).toBe("period");
    expect(start().check(ctx({ tripped: true }))).toBe("tripped");
  });

  it("an insert step ends when power falls to the goal, and a short period does not abort it", () => {
    const s = new RodSequencer();
    s.start({ rod: "shim", direction: "in", to: 0.45 });
    expect(s.check(ctx({ power: 100, period: 5 }))).toBeNull();
    expect(s.check(ctx({ power: 10 }))).toBe("goal");
  });

  it("the guard hands over only when sequencing, idle, far above the goal and rising", () => {
    const s = new RodSequencer();
    s.sequencing = true;
    expect(s.needsGuard(ctx({ power: 20, period: 50 }))).toBe(true);
    expect(s.needsGuard(ctx({ power: 20, period: -50 }))).toBe(false);
    expect(s.needsGuard(ctx({ power: 12, period: 50 }))).toBe(false);
    s.start({ rod: "safety", direction: "out", to: 0.55 });
    expect(s.needsGuard(ctx({ power: 20, period: 50 }))).toBe(false);
  });
});
