import type { DecisionRequest, DecisionResponse } from "./protocol";

export type SupervisorMode = "DISABLED" | "TRACKING" | "TRIPPED" | "UNAVAILABLE";
export type Intent = "HOLD_TARGET" | "RAISE_TARGET" | "REDUCE_TARGET" | "REQUEST_SCRAM" | "STOP_MOTION";

export interface Candidate {
  id: string;
  text: string;
  intent: Intent;
  targetValue?: number;
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
  public readonly maxWallAgeMs: number = 2000;
  private maxSimAgeS: number = 1.0;

  public pendingRequest: boolean = false;
  /** Identity of the one request in flight; a reply must match all of it. */
  private pendingIdentity: Identity | null = null;

  public temporalEpoch: number = 0;

  /** `now` is the host's wall clock, so tests and replay control the deadlines. */
  constructor(private readonly now: () => number = () => performance.now()) {}

  public enableTracking(port: string): void {
    if (this.mode !== "TRIPPED" && this.mode !== "UNAVAILABLE") {
      this.mode = "TRACKING";
      this.ownerPort = port;
    }
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

  public isTracking(): boolean {
    return this.mode === "TRACKING";
  }

  /** Build the candidates for one request. `target` is the controller's approved target (W), or null when it is not armed; `raiseTo` is the validated higher target, or null when a raise is not allowed. */
  public dispatchObservation(simTimeS: number, target: number | null, raiseTo: number | null = null): Candidate[] {
    this.lastObservationSimS = simTimeS;
    this.lastObservationWallMs = this.now();
    this.pendingRequest = true;

    this.activeCandidates.clear();

    // The AI picks among candidates the runtime validated; it never invents a target.
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
    candidates.push({ id: "stop", text: "I will STOP all rod motion and monitor.", intent: "STOP_MOTION" });
    candidates.push({ id: "scram", text: "The reactor is out of control. I will trigger a manual SCRAM immediately.", intent: "REQUEST_SCRAM" });

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
      this.activeCandidates.clear();
      return null;
    }
    const candidate = this.activeCandidates.get(response.candidateId) ?? null;
    this.activeCandidates.clear();
    return candidate;
  }
}
