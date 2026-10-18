import type { DecisionRequest, DecisionResponse } from "./protocol";
import type { SequenceOffers } from "./sequencer";

export type SupervisorMode = "DISABLED" | "TRACKING" | "TRIPPED" | "UNAVAILABLE";
export type Intent = "HOLD_TARGET" | "RAISE_TARGET" | "REDUCE_TARGET" | "WITHDRAW_ROD" | "INSERT_ROD" | "ENGAGE_HOLD" | "WAIT" | "REQUEST_SCRAM" | "STOP_MOTION";

export interface Candidate {
  id: string;
  text: string;
  intent: Intent;
  /** A validated target power (W), or for a rod step the position where it ends. */
  targetValue?: number;
  /** The rod a step moves. */
  rod?: string;
}

export interface DispatchOptions {
  target: number | null;
  raiseTo: number | null;
  allowScram: boolean;
  sequencing: boolean;
  offers: SequenceOffers;
}

/** A lowered target is this fraction of the approved one, and never below the floor (W). */
export const REDUCE_FACTOR = 0.5;
export const TARGET_FLOOR_W = 1e-6;
/** A raised target is this multiple of the approved one. */
export const RAISE_FACTOR = 2;
/** A raised target never exceeds this fraction of the power-high trip setpoint. */
export const RAISE_CEILING_FRACTION = 0.5;
/** Raises are at least this far apart (s of sim time). */
export const RAISE_COOLDOWN_S = 20;
/** No raise while the period is positive and shorter than this (s). */
export const RAISE_MIN_PERIOD_S = 60;

interface Identity {
  sessionId: string;
  temporalEpoch: number;
  connectionId: string;
  requestId: string;
  observationStep: number;
}

export class Supervisor {
  public mode: SupervisorMode = "DISABLED";
  /** The window that turned supervision on; only it may answer, and requests go only to it. */
  public ownerPort: string | null = null;
  private activeCandidates: Map<string, Candidate> = new Map();

  // Deadlines
  private lastObservationWallMs: number = 0;
  private lastObservationSimS: number = 0;

  // Configured limits
  public readonly maxWallAgeMs: number;
  private maxSimAgeS: number;
  /** Least wall time between two requests, and the extra wait after an error reply (ms). */
  private readonly minIntervalMs: number;
  private readonly errorBackoffMs: number;
  private nextAllowedWall = 0;

  public pendingRequest: boolean = false;
  /** Identity of the one request in flight; a reply must match all of it. */
  private pendingIdentity: Identity | null = null;

  public temporalEpoch: number = 0;

  /** `now` is the host's wall clock, so tests and replay control the deadlines. */
  constructor(
    private readonly now: () => number = () => performance.now(),
    limits: { maxWallAgeMs?: number; maxSimAgeS?: number; minIntervalMs?: number; errorBackoffMs?: number } = {},
  ) {
    this.maxWallAgeMs = limits.maxWallAgeMs ?? 2000;
    this.maxSimAgeS = limits.maxSimAgeS ?? 1.0;
    this.minIntervalMs = limits.minIntervalMs ?? 500;
    this.errorBackoffMs = limits.errorBackoffMs ?? 2000;
  }

  /** Turn supervision on for `port`. False (nothing changed) if it is tripped or unavailable, or another window already owns it. */
  public enableTracking(port: string): boolean {
    if (this.mode === "TRIPPED" || this.mode === "UNAVAILABLE") return false;
    if (this.ownerPort !== null && this.ownerPort !== port) return false;
    this.mode = "TRACKING";
    this.ownerPort = port;
    return true;
  }

  public trip(): void {
    this.mode = "TRIPPED";
    this.invalidate();
  }

  public disable(): void {
    this.mode = "DISABLED";
    this.ownerPort = null;
    this.invalidate();
  }

  /** Forget the request in flight and its candidates, so no late reply can act. */
  public invalidate(): void {
    this.pendingRequest = false;
    this.pendingIdentity = null;
    this.activeCandidates.clear();
  }

  /** True when enough wall time has passed since the last request (and its error backoff). */
  public canDispatch(): boolean {
    return this.now() >= this.nextAllowedWall;
  }

  public isTracking(): boolean {
    return this.mode === "TRACKING";
  }

  /**
   * Build the candidates for one request. The runtime has already checked each one; the AI picks, it never invents.
   * `target` is the controller's approved target (W), or null when it is off; `raiseTo` is a validated higher target;
   * `sequencing` is true while the AI steps rods with the controller off; `offers` are the allowed rod steps.
   */
  public dispatchObservation(simTimeS: number, o: DispatchOptions): Candidate[] {
    this.lastObservationSimS = simTimeS;
    this.lastObservationWallMs = this.now();
    this.nextAllowedWall = this.lastObservationWallMs + this.minIntervalMs;
    this.pendingRequest = true;

    this.activeCandidates.clear();

    const { target, raiseTo, allowScram, sequencing, offers } = o;
    const pct = (x: number) => `${Math.round(x * 100)}%`;
    const candidates: Candidate[] = [];
    if (target !== null) {
      candidates.push({ id: "hold", text: "I will HOLD TARGET and keep the automatic controller at the current power.", intent: "HOLD_TARGET" });
      if (raiseTo !== null) {
        candidates.push({
          id: "raise",
          text: `I will RAISE THE TARGET power to ${raiseTo.toExponential(2)} W and let the controller bring power up carefully.`,
          intent: "RAISE_TARGET",
          targetValue: raiseTo,
        });
      }
      const lower = target * REDUCE_FACTOR;
      if (lower >= TARGET_FLOOR_W) {
        candidates.push({
          id: "reduce",
          text: `I will LOWER THE TARGET power to ${lower.toExponential(2)} W and let the controller bring power down safely.`,
          intent: "REDUCE_TARGET",
          targetValue: lower,
        });
      }
    }
    if (sequencing) {
      candidates.push({ id: "wait", text: "I will WAIT and watch the power settle before the next rod step.", intent: "WAIT" });
    }
    if (offers.withdraw) {
      candidates.push({
        id: "withdraw",
        text: `I will WITHDRAW the ${offers.withdraw.rod} rod one small step (to ${pct(offers.withdraw.to)} out) to bring power up toward the goal.`,
        intent: "WITHDRAW_ROD",
        rod: offers.withdraw.rod,
        targetValue: offers.withdraw.to,
      });
    }
    if (offers.insert) {
      candidates.push({
        id: "insert",
        text: `I will INSERT the ${offers.insert.rod} rod one small step (to ${pct(offers.insert.to)} out) to bring power down toward the goal.`,
        intent: "INSERT_ROD",
        rod: offers.insert.rod,
        targetValue: offers.insert.to,
      });
    }
    if (offers.engage) {
      candidates.push({ id: "engage", text: "I will let the automatic controller take over and HOLD the power here, working toward the goal with the regulating rod.", intent: "ENGAGE_HOLD" });
    }
    if (target !== null) candidates.push({ id: "stop", text: "I will STOP all rod motion and monitor.", intent: "STOP_MOTION" });
    // A SCRAM is offered only in a real emergency (the runtime decides); the protection system trips on its own regardless.
    if (allowScram) {
      candidates.push({ id: "scram", text: "The reactor is out of control. I will trigger a manual SCRAM immediately.", intent: "REQUEST_SCRAM" });
    }

    for (const c of candidates) {
      this.activeCandidates.set(c.id, c);
    }

    return candidates;
  }

  /** Record the identity of the request just sent. */
  public expect(req: DecisionRequest): void {
    const { sessionId, temporalEpoch, connectionId, requestId, observationStep } = req;
    this.pendingIdentity = { sessionId, temporalEpoch, connectionId, requestId, observationStep };
  }

  /** True while `requestId` is the request in flight. */
  public isPending(requestId: string): boolean {
    return this.pendingRequest && this.pendingIdentity?.requestId === requestId;
  }

  /** True when the request in flight has waited longer than the wall limit. */
  public wallExpired(): boolean {
    return this.pendingRequest && this.now() - this.lastObservationWallMs > this.maxWallAgeMs;
  }

  /** Checks deadlines. Returns true if supervision is lost. */
  public checkDeadlines(currentSimTimeS: number): boolean {
    if (!this.isTracking() || !this.pendingRequest) return false;
    return this.wallExpired() || currentSimTimeS - this.lastObservationSimS > this.maxSimAgeS;
  }

  /**
   * Match a reply to the request in flight. A reply for anything else is dropped and leaves that request
   * pending. A matching error or shadow reply completes the request but chooses nothing.
   */
  public resolveDecision(response: DecisionResponse): Candidate | null {
    const id = this.pendingIdentity;
    if (!id || !this.pendingRequest || this.mode !== "TRACKING") return null;
    if (
      response.requestId !== id.requestId ||
      response.sessionId !== id.sessionId ||
      response.connectionId !== id.connectionId ||
      response.temporalEpoch !== id.temporalEpoch ||
      response.observationStep !== id.observationStep ||
      response.temporalEpoch !== this.temporalEpoch
    ) {
      return null;
    }
    this.pendingRequest = false;
    this.pendingIdentity = null;

    if (response.status !== "ok" || !response.candidateId) {
      if (response.status === "error") this.nextAllowedWall = this.now() + this.errorBackoffMs; // do not hammer a failing server
      this.activeCandidates.clear();
      return null;
    }
    const candidate = this.activeCandidates.get(response.candidateId) ?? null;
    this.activeCandidates.clear();
    return candidate;
  }
}
