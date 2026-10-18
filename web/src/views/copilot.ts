import type { RuntimeClient } from "../runtime/client";
import type { DecisionRequest, DecisionResponse } from "../runtime/protocol";

export const JEV_URL = "ws://localhost:8000/jev";
/** Wall time the instructor waits between its own requests (ms). */
const INSTRUCTOR_PERIOD_MS = 5000;
/** A request with no reply after this long is given up, so a server that stays connected but never answers does not silence the copilot for ever. */
export const REPLY_TIMEOUT_MS = 30_000;

const INSTRUCTOR_CANDIDATES = [
  { id: "wait", text: "The operator is busy. I will wait and observe." },
  { id: "stick", text: "I will make an instrument read stuck to confuse the operator." },
  { id: "end", text: "The scenario is complete. I will end the simulation." },
];

/**
 * The browser end of the Jev link. The operator copilot only relays: the runtime builds each request,
 * validates each reply and owns the controller. The instructor copilot has its own small loop and never
 * touches the operator supervisor.
 */
export class JevCopilot {
  private enabled = false;
  private ws: WebSocket | null = null;
  private readonly client: RuntimeClient;
  private readonly role: "operator" | "instructor";
  /** Called when the link goes up or down, so the button can follow. */
  public onChange: (on: boolean) => void = () => {};

  // instructor loop state
  private readonly connectionId = `${Math.random().toString(36).slice(2)}`;
  private pending: { requestId: string; step: number; at: number } | null = null;
  /** The last thing that went wrong with the copilot (a reply that never came, a refused command), or null. */
  public lastIssue: string | null = null;
  private lastAsk = 0;
  private step = 0;
  private offSnapshot: (() => void) | null = null;
  private offRequest: (() => void) | null = null;

  constructor(client: RuntimeClient, role: "operator" | "instructor") {
    this.client = client;
    this.role = role;
  }

  public get isOn(): boolean {
    return this.enabled;
  }

  public toggle(): void {
    if (this.enabled || this.ws) this.disconnect();
    else this.connect();
  }

  public disconnect(): void {
    const wasOn = this.enabled || this.ws !== null;
    this.enabled = false;
    this.pending = null;
    this.offSnapshot?.();
    this.offRequest?.();
    this.offSnapshot = this.offRequest = null;
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onclose = ws.onerror = ws.onmessage = ws.onopen = null; // an old socket must not tear down a new one
      ws.close();
    }
    // the runtime stops the rod it was moving and clears its request
    if (this.role === "operator" && wasOn) this.client.supervisorDisable();
    if (wasOn) this.onChange(false);
  }

  /** Supervision is switched on only once the socket is open, so the first request is never dropped. */
  private connect(): void {
    const ws = new WebSocket(JEV_URL);
    this.ws = ws;
    ws.onopen = () => {
      if (this.ws !== ws) return;
      this.enabled = true;
      console.log(`[JevCopilot] Connected as ${this.role}`);
      if (this.role === "operator") {
        this.offRequest = this.client.on("decision_request", (msg) => this.relay(msg.request));
        this.client.supervisorEnable();
      } else {
        this.offSnapshot = this.client.on("snapshot", (msg) => this.onInstructorSnapshot(msg.snapshot));
      }
      this.onChange(true);
    };
    ws.onmessage = (ev) => {
      if (this.ws !== ws || !this.enabled) return;
      let msg: any;
      try {
        msg = JSON.parse(ev.data);
      } catch (err) {
        console.error("[JevCopilot] JSON decode error:", err);
        return;
      }
      if (!msg || typeof msg.requestId !== "string") return;
      // Forward every envelope: ok, shadow and error replies all complete the request.
      if (this.role === "operator") this.client.decisionResponse(msg as DecisionResponse);
      else this.onInstructorReply(msg as DecisionResponse);
    };
    ws.onclose = () => {
      if (this.ws !== ws) return; // a stale socket
      console.warn("[JevCopilot] Disconnected");
      this.disconnect();
    };
    ws.onerror = (err) => console.error("[JevCopilot] WebSocket error:", err);
  }

  private relay(req: DecisionRequest): void {
    if (!this.enabled || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify(req));
  }

  private onInstructorSnapshot(snap: Record<string, any>): void {
    const now = Date.now();
    if (this.pending && now - this.pending.at > REPLY_TIMEOUT_MS) {
      this.lastIssue = `no reply to request ${this.pending.requestId} after ${REPLY_TIMEOUT_MS / 1000} s; asking again`;
      console.warn(`[JevCopilot] ${this.lastIssue}`);
      this.pending = null;
    }
    if (this.pending || now - this.lastAsk < INSTRUCTOR_PERIOD_MS) return;
    this.lastAsk = now;
    const power = snap.truth?.power ?? snap.indicated?.["log"] ?? 0; // the instructor's premise is the true power: a stuck instrument must not be stated as the reactor's power
    const requestId = `${this.connectionId}-${this.step}`;
    this.pending = { requestId, step: this.step, at: now };
    const req: DecisionRequest = {
      protocolVersion: 1,
      sessionId: "instructor",
      temporalEpoch: 0,
      connectionId: this.connectionId,
      requestId,
      observationStep: this.step++,
      observationSimTimeS: snap.t ?? 0,
      role: "instructor",
      premise: `ROLE: Simulation Instructor. GOAL: Provide a challenging but solvable scenario for the operator. Power is ${Number(power).toExponential(3)} W.`,
      candidates: INSTRUCTOR_CANDIDATES,
    };
    this.relay(req);
  }

  private onInstructorReply(res: DecisionResponse): void {
    const p = this.pending;
    if (!p || res.requestId !== p.requestId || res.observationStep !== p.step) return; // not for the request in flight
    this.pending = null;
    if (res.status !== "ok" || !res.candidateId) return; // error and shadow replies choose nothing
    if (res.candidateId === "stick") {
      // schema/command.schema.json has no drift kind, so an AI-triggered fault is a stuck reading
      void this.client.command({ type: "fault.instrument", instrument: "linear", kind: "stuck" }, undefined, "instructor").then((ack) => {
        if (ack.status === "rejected") {
          this.lastIssue = `the engine refused the fault the AI chose: ${ack.reason ?? "no reason given"}`;
          console.warn(`[JevCopilot] ${this.lastIssue}`);
        }
      });
    } else if (res.candidateId === "end") {
      this.client.endScenario();
    }
  }
}

/** The AI operator's mode in words (shared by the operator and instructor panels). */
export function describeSupervision(s: import("../runtime/protocol").SupervisionView): string {
  const w = (x: number) => x.toExponential(2);
  switch (s.mode) {
    case "off":
      return "AI copilot: off";
    case "holding":
      return `AI copilot: holding ${s.target !== null ? w(s.target) + " W" : "power"} with the automatic controller`;
    case "stepping":
      return `AI copilot: stepping a rod (${s.step ?? "moving"}), controller off`;
    case "sequencing":
      return "AI copilot: working the rods by hand toward the goal, controller off";
    default:
      return "AI copilot: on, nothing armed";
  }
}

export function createCopilotButton(copilot: JevCopilot): HTMLButtonElement {
  const btn = document.createElement("button");
  const label = (on: boolean) => (btn.textContent = on ? "Disconnect AI Copilot" : "Connect AI Copilot");
  label(false);
  btn.style.cssText = "margin-left: 10px; padding: 4px 8px; font-weight: bold; cursor: pointer;";
  copilot.onChange = label;
  btn.onclick = () => copilot.toggle();
  return btn;
}
