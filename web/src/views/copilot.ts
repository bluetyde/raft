import type { RuntimeClient } from "../runtime/client";
import type { FromWorker } from "../runtime/protocol";

class PIDController {
  private kp = 0.2;
  private ki = 0.01;
  private kd = 1.5;

  private target: number | null = null;
  private integral = 0;
  private prevError = 0;
  private lastT: number | null = null;

  public isEnabled(): boolean {
    return this.target !== null;
  }

  public setTarget(target: number): void {
    if (this.target === target) return;
    console.log(`[PID] Target set to ${target.toExponential(2)} W`);
    this.target = target;
    this.integral = 0;
    this.prevError = 0;
    this.lastT = null;
  }

  public disable(): void {
    if (this.target !== null) console.log(`[PID] Disabled`);
    this.target = null;
  }

  public update(current: number, t: number): string | null {
    if (this.target === null) return null;
    if (this.lastT === null) {
      this.lastT = t;
      return null;
    }
    
    const dt = t - this.lastT;
    if (dt <= 0) return null;
    this.lastT = t;

    // Use log10 error to handle 0W vs 10kW smoothly
    const logTarget = Math.log10(Math.max(this.target, 1e-6));
    const logCurrent = Math.log10(Math.max(current, 1e-6));
    const error = logTarget - logCurrent;
    
    this.integral += error * dt;
    this.integral = Math.max(-10, Math.min(10, this.integral)); // Anti-windup
    
    const derivative = (error - this.prevError) / dt;
    this.prevError = error;

    const output = (this.kp * error) + (this.ki * this.integral) + (this.kd * derivative);
    
    const threshold = 0.1; // Wider deadband to avoid chattering
    if (output > threshold) return "out";
    if (output < -threshold) return "in";
    return "stop";
  }
}


export class JevCopilot {
  private ws: WebSocket | null = null;
  private client: RuntimeClient;
  private role: "operator" | "instructor";
  private enabled: boolean = false;
  /** True when a request is waiting for a server response (prevents flooding). */
  private inferenceInFlight: boolean = false;
  /** Latest rod positions (0–1) from the most recent snapshot. */
  private rodPositions: Record<string, number> = {};
  /** Latest moving state of rods from the most recent snapshot. */
  private rodMoving: Record<string, string | null> = {};
  
  private pid = new PIDController();
  private lastPower: number = 0;
  private currentT: number = 0;
  private inferenceT: number | null = null;

  constructor(client: RuntimeClient, role: "operator" | "instructor") {
    this.client = client;
    this.role = role;
  }

  public toggle(): void {
    if (this.enabled) {
      this.disconnect();
    } else {
      this.connect();
    }
  }

  private connect(): void {
    this.ws = new WebSocket(`ws://localhost:8000/ws/${this.role}`);
    this.ws.onopen = () => {
      console.log(`[JevCopilot] Connected as ${this.role}`);
      this.enabled = true;
      this.inferenceInFlight = false;
    };
    this.ws.onmessage = (event) => {
      this.handleMessage(event.data);
    };
    this.ws.onclose = () => {
      console.log("[JevCopilot] Disconnected");
      this.ws = null;
      this.cleanup();
    };
    this.ws.onerror = (err) => {
      console.error("[JevCopilot] WebSocket error:", err);
      this.ws = null;
      this.cleanup();
    };
  }

  public disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.cleanup();
  }

  private cleanup(): void {
    this.pid.disable();
    this.enabled = false;
    this.inferenceInFlight = false;

    // Safety: Stop any ongoing rod motion initiated by the copilot
    if (this.role === "operator") {
      this.client.command({ type: "rod.move", rod: "shim",       direction: "stop" }, undefined, this.role);
      this.client.command({ type: "rod.move", rod: "safety",     direction: "stop" }, undefined, this.role);
      this.client.command({ type: "rod.move", rod: "regulating", direction: "stop" }, undefined, this.role);
    }
  }

  public onSnapshot(snapMsg: Extract<FromWorker, { kind: "snapshot" }>, scenarioState?: any): void {
    if (!this.enabled || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    const s = snapMsg.snapshot;
    this.currentT = s.t ?? 0;

    let premise = "";
    let hypotheses: string[] = [];

    if (this.role === "operator") {
      const truth = s.truth ?? {};
      const power    = s.indicated?.["log"]       ?? truth.power ?? 0;
      const period   = truth.period ?? 0;
      const fuelTemp = (truth.fuelTemp ?? 293.15) - 273.15; // K to C
      const t        = s.t ?? 0;

      this.lastPower = power;

      // Cache rod states
      const rods = truth.rods ?? {};
      for (const id of ["shim", "safety", "regulating"]) {
        this.rodPositions[id] = rods[id]?.position ?? 1; // default to 1 (withdrawn) if missing
        this.rodMoving[id]    = rods[id]?.moving ?? null;
      }
      
      // Execute fast Reflex PID Loop (30Hz)
      if (this.pid.isEnabled()) {
        let pidCmd = this.pid.update(power, t);
        if (pidCmd !== null) {
          if (pidCmd === "out" && (this.rodPositions["regulating"] ?? 1) >= 0.99) pidCmd = "stop";
          if (pidCmd === "in" && (this.rodPositions["regulating"] ?? 1) <= 0.01) pidCmd = "stop";
          
          const currentMoving = this.rodMoving["regulating"] ?? "stop";
          if (currentMoving !== pidCmd) {
            this.client.command({ type: "rod.move", rod: "regulating", direction: pidCmd }, undefined, this.role);
            this.rodMoving["regulating"] = pidCmd === "stop" ? null : pidCmd; // optimistic
          }
        }
      }
    }

    if (this.inferenceInFlight) return; // Wait for previous inference to finish

    if (this.role === "operator") {
      const truth = s.truth ?? {};
      const power    = s.indicated?.["log"]       ?? truth.power ?? 0;
      const period   = truth.period ?? 0;
      const fuelTemp = (truth.fuelTemp ?? 293.15) - 273.15; // K to C
      
      const rodDesc = [
        `Shim: ${((this.rodPositions["shim"] ?? 1)       * 100).toFixed(0)}%`,
        `Safety: ${((this.rodPositions["safety"] ?? 1)   * 100).toFixed(0)}%`,
        `Regulating: ${((this.rodPositions["regulating"] ?? 1) * 100).toFixed(0)}%`,
      ].join(", ");

      // Determine reactor phase
      const isShutdown = power < 1e-6;
      const isDanger   = !isShutdown && period > 0 && period < 10;
      const isStartup  = !isShutdown && period > 30;
      const isStable   = !isShutdown && (period < 0 || period > 100);

      let phaseDesc: string;
      if (isShutdown)     phaseDesc = "The reactor is SHUTDOWN (power is essentially zero).";
      else if (isDanger)  phaseDesc = `Power is ${power.toExponential(3)} W. Period is dangerously short at ${period.toFixed(1)} s — reactor is accelerating rapidly.`;
      else if (isStartup) phaseDesc = `Power is ${power.toExponential(3)} W. Period is ${period.toFixed(1)} s — reactor is rising in a controlled startup.`;
      else if (isStable)  phaseDesc = `Power is ${power.toExponential(3)} W. Period is ${period.toFixed(1)} s — reactor is stable or falling.`;
      else                phaseDesc = `Power is ${power.toExponential(3)} W. Period is ${period.toFixed(1)} s.`;

      premise = `ROLE: Nuclear Reactor Operator. GOAL: Bring the reactor to operating power, maintain safe power levels, avoid SCRAMs. CURRENT STATE: ${phaseDesc} Rod positions — ${rodDesc}. Fuel Temperature is ${fuelTemp.toFixed(1)} °C.`;

      hypotheses = [
        "The reactor needs more reactivity. I will pull ONE control rod UP to raise power.",
        "Power is rising safely. I will STOP the control rods and monitor until stable.",
        "Power is rising too fast or the period is dangerously short. I will push the regulating rod DOWN.",
        "The reactor is out of control. I will trigger a manual SCRAM immediately.",
      ];
    } else {
      // Instructor
      const power = s.indicated?.["log"] ?? s.truth?.power ?? 0;
      const scenarioText = scenarioState ? JSON.stringify(scenarioState) : "No active scenario.";
      premise = `ROLE: Simulation Instructor. GOAL: Provide a challenging but solvable scenario for the operator. CURRENT STATE: ${scenarioText}. Power is ${power.toExponential(3)} W.`;

      hypotheses = [
        "The operator is busy. I will wait and observe.",
        "I will trigger an instrument drift fault to confuse the operator.",
        "I will jam a control rod (stuck) to see how they react.",
        "The scenario is complete. I will end the simulation."
      ];
    }

    this.inferenceInFlight = true;
    this.inferenceT = this.currentT;
    this.ws.send(JSON.stringify({ premise, hypotheses }));
  }

  private handleMessage(data: string): void {
    this.inferenceInFlight = false;
    if (!this.enabled) return;

    try {
      const msg = JSON.parse(data);
      if (msg.error) {
        console.error("[JevCopilot] Server error:", msg.error);
        return;
      }
      const choice = msg.choice;
      if (!choice) return;

      if (this.inferenceT !== null && this.currentT - this.inferenceT > 5.0) {
        console.warn(`[JevCopilot] Rejecting stale AI response (age: ${(this.currentT - this.inferenceT).toFixed(2)}s)`);
        return;
      }

      console.log(`[JevCopilot] AI chose: ${choice}`);
      this.executeChoice(choice);
    } catch (err) {
      console.error("[JevCopilot] JSON decode error:", err);
    }
  }

  private executeChoice(choice: string): void {
    if (this.role === "operator") {
      const desiredMoving: Record<string, string | null> = { shim: null, safety: null, regulating: null };
      let updatePid = false;

      if (choice.includes("pull ONE control rod UP")) {
        this.pid.disable();
        const AT_LIMIT = 0.99;
        if ((this.rodPositions["shim"] ?? 1) < AT_LIMIT) desiredMoving["shim"] = "out";
        else if ((this.rodPositions["safety"] ?? 1) < AT_LIMIT) desiredMoving["safety"] = "out";
        else if ((this.rodPositions["regulating"] ?? 1) < AT_LIMIT) desiredMoving["regulating"] = "out";
      } else if (choice.includes("push the regulating rod DOWN")) {
        this.pid.disable();
        desiredMoving["regulating"] = "in";
      } else if (choice.includes("STOP the control rods")) {
        // Let the PID handle holding the current power with the regulating rod
        updatePid = true;
      } else if (choice.includes("manual SCRAM")) {
        this.pid.disable();
        this.client.command({ type: "scram" }, undefined, this.role);
        return;
      }

      if (updatePid && this.lastPower > 0) {
        if (!this.pid.isEnabled()) {
          desiredMoving["regulating"] = "stop"; // Finding 5
          this.pid.setTarget(this.lastPower);   // Finding 2
        }
      }

      // Reconcile desired state with current engine state
      for (const id of ["shim", "safety", "regulating"]) {
        // If PID is taking over regulating, skip manual reconcile for it UNLESS we explicitly requested a stop
        if (updatePid && id === "regulating" && desiredMoving["regulating"] !== "stop") continue;

        const current = this.rodMoving[id] ?? "stop";
        const desired = desiredMoving[id] ?? "stop";
        if (current !== desired) {
          this.client.command({ type: "rod.move", rod: id, direction: desired }, undefined, this.role);
          this.rodMoving[id] = desired === "stop" ? null : desired;
        }
      }
    } else {
      if (choice.includes("jam a control rod")) {
        this.client.command({ type: "fault.rod", rod: "transient", kind: "stuck" }, undefined, this.role);
      } else if (choice.includes("instrument drift fault")) {
        this.client.command({ type: "fault.instrument", instrument: "linear", kind: "drift" }, undefined, this.role);
      } else if (choice.includes("end the simulation")) {
        this.client.endScenario();
      }
    }
  }
}

export function createCopilotButton(copilot: JevCopilot): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.textContent = "Connect AI Copilot";
  btn.style.cssText = "margin-left: 10px; padding: 4px 8px; font-weight: bold; cursor: pointer;";
  btn.onclick = () => {
    copilot.toggle();
    btn.textContent = btn.textContent === "Connect AI Copilot" ? "Disconnect AI Copilot" : "Connect AI Copilot";
  };
  return btn;
}


