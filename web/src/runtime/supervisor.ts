import type { DecisionResponse } from "./protocol";

export type SupervisorMode = "DISABLED" | "TRACKING" | "TRIPPED" | "UNAVAILABLE";
export type Intent = "HOLD_TARGET" | "REDUCE_TARGET" | "REQUEST_SCRAM" | "STOP_MOTION";

export interface Candidate {
  id: string;
  text: string;
  intent: Intent;
  targetValue?: number;
}

export class Supervisor {
  public mode: SupervisorMode = "DISABLED";
  private activeCandidates: Map<string, Candidate> = new Map();

  // Deadlines
  private lastObservationWallMs: number = 0;
  private lastObservationSimS: number = 0;
  
  // Configured limits
  private maxWallAgeMs: number = 2000; 
  private maxSimAgeS: number = 1.0;

  public pendingRequest: boolean = false;
  
  public temporalEpoch: number = 0;

  public enableTracking(): void {
    if (this.mode !== "TRIPPED" && this.mode !== "UNAVAILABLE") {
      this.mode = "TRACKING";
    }
  }

  public trip(): void {
    this.mode = "TRIPPED";
  }

  public disable(): void {
    this.mode = "DISABLED";
  }

  public isTracking(): boolean {
    return this.mode === "TRACKING";
  }

  public dispatchObservation(simTimeS: number): Candidate[] {
    this.lastObservationSimS = simTimeS;
    this.lastObservationWallMs = performance.now();
    this.pendingRequest = true;

    this.activeCandidates.clear();
    
    // Generate valid candidates. AI never invents a target.
    const candidates: Candidate[] = [
      { id: "hold", text: "I will HOLD TARGET to engage the automatic PID controller at current power.", intent: "HOLD_TARGET" },
      { id: "reduce", text: "I will REDUCE POWER to push the regulating rod DOWN.", intent: "REDUCE_TARGET" }, // Typically we'd generate a specific target value
      { id: "scram", text: "The reactor is out of control. I will trigger a manual SCRAM immediately.", intent: "REQUEST_SCRAM" }
    ];

    for (const c of candidates) {
      this.activeCandidates.set(c.id, c);
    }

    return candidates;
  }

  /**
   * Checks deadlines. Returns true if supervision is lost.
   */
  public checkDeadlines(currentSimTimeS: number): boolean {
    if (!this.isTracking() || !this.pendingRequest) return false;

    const wallAge = performance.now() - this.lastObservationWallMs;
    const simAge = currentSimTimeS - this.lastObservationSimS;

    if (wallAge > this.maxWallAgeMs || simAge > this.maxSimAgeS) {
      return true; // Supervision lost
    }
    return false;
  }

  public resolveDecision(response: DecisionResponse): Candidate | null {
    this.pendingRequest = false;
    
    if (response.status === "error" || !response.candidateId) {
      return null;
    }

    const candidate = this.activeCandidates.get(response.candidateId);
    if (!candidate) {
      return null; // Unknown or invalid ID
    }

    return candidate;
  }
}
