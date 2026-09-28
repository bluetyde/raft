import type { RuntimeClient } from "../runtime/client";
import type { FromWorker } from "../runtime/protocol";

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
      this.enabled = false;
      this.ws = null;
      this.inferenceInFlight = false;
    };
    this.ws.onerror = (err) => {
      console.error("[JevCopilot] WebSocket error:", err);
      this.enabled = false;
      this.ws = null;
    };
  }

  public disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
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
    if (this.inferenceInFlight) return; // Wait for previous inference to finish

    const s = snapMsg.snapshot;
    let premise = "";
    let hypotheses: string[] = [];

    if (this.role === "operator") {
      // Use truth fields directly since operatorView strips them for the view
      const truth = s.truth ?? {};
      const power    = s.indicated?.["log"]       ?? truth.power ?? 0;
      const period   = truth.period ?? 0;
      const fuelTemp = (truth["temp.fuel"] ?? 293.15) - 273.15; // K to C

      // Cache rod states
      const rods = truth.rods ?? {};
      for (const id of ["shim", "safety", "regulating"]) {
        this.rodPositions[id] = rods[id]?.position ?? 1; // default to 1 (withdrawn) if missing
        this.rodMoving[id]    = rods[id]?.moving ?? null;
      }

      const rodDesc = [
        `Shim: ${(this.rodPositions["shim"]       * 100).toFixed(0)}%`,
        `Safety: ${(this.rodPositions["safety"]   * 100).toFixed(0)}%`,
        `Regulating: ${(this.rodPositions["regulating"] * 100).toFixed(0)}%`,
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

      console.log(`[JevCopilot] AI chose: ${choice}`);
      this.executeChoice(choice);
    } catch (err) {
      console.error("[JevCopilot] JSON decode error:", err);
    }
  }

  private executeChoice(choice: string): void {
    if (this.role === "operator") {
      const desiredMoving: Record<string, string | null> = { shim: null, safety: null, regulating: null };

      if (choice.includes("pull ONE control rod UP")) {
        const AT_LIMIT = 0.99;
        if (this.rodPositions["shim"] < AT_LIMIT) desiredMoving["shim"] = "out";
        else if (this.rodPositions["safety"] < AT_LIMIT) desiredMoving["safety"] = "out";
        else if (this.rodPositions["regulating"] < AT_LIMIT) desiredMoving["regulating"] = "out";
      } else if (choice.includes("push the regulating rod DOWN")) {
        desiredMoving["regulating"] = "in";
      } else if (choice.includes("STOP the control rods")) {
        // all desired moving = null
      } else if (choice.includes("manual SCRAM")) {
        this.client.command({ type: "scram" }, undefined, this.role);
        return;
      }

      // Reconcile desired state with current engine state
      for (const id of ["shim", "safety", "regulating"]) {
        const current = this.rodMoving[id];
        const desired = desiredMoving[id];
        if (current !== desired) {
          this.client.command({ type: "rod.move", rod: id, direction: desired ?? "stop" }, undefined, this.role);
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
