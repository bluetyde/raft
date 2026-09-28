import type { RuntimeClient } from "../runtime/client";
import type { FromWorker } from "../runtime/protocol";

export class JevCopilot {
  private ws: WebSocket | null = null;
  private client: RuntimeClient;
  private role: "operator" | "instructor";
  private enabled: boolean = false;
  /** Track the last choice so we only act when the decision changes. */
  private lastChoice: string | null = null;
  /** Latest rod positions (0–1) from the most recent snapshot. */
  private rodPositions: Record<string, number> = {};

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
    };
    this.ws.onmessage = (event) => {
      this.handleMessage(event.data);
    };
    this.ws.onclose = () => {
      console.log("[JevCopilot] Disconnected");
      this.enabled = false;
      this.ws = null;
      this.lastChoice = null;
    };
    this.ws.onerror = (err) => {
      console.error("[JevCopilot] WebSocket error:", err);
      this.enabled = false;
      this.ws = null;
    };
  }

  private disconnect(): void {
    if (this.ws) {
      this.ws.close();
    }
  }

  public onSnapshot(snapMsg: Extract<FromWorker, { kind: "snapshot" }>, scenarioState?: any): void {
    if (!this.enabled || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }

    const s = snapMsg.snapshot;
    let premise = "";
    let hypotheses: string[] = [];

    if (this.role === "operator") {
      const power    = s.indicated?.["power"]     ?? 0;
      const period   = s.indicated?.["period"]    ?? 0;
      const fuelTemp = s.indicated?.["temp.fuel"] ?? 0;

      // Rod positions (0–1 fraction, 1 = fully withdrawn)
      const rodRegulating = s.rods?.["regulating"] ?? s.indicated?.["rod.regulating"] ?? null;
      const rodShim       = s.rods?.["shim"]       ?? s.indicated?.["rod.shim"]       ?? null;
      const rodSafety     = s.rods?.["safety"]     ?? s.indicated?.["rod.safety"]     ?? null;

      // Cache for executeChoice to read when deciding which rod to move
      if (rodRegulating !== null) this.rodPositions["regulating"] = rodRegulating;
      if (rodShim       !== null) this.rodPositions["shim"]       = rodShim;
      if (rodSafety     !== null) this.rodPositions["safety"]     = rodSafety;

      const rodDesc = [
        rodShim       !== null ? `Shim: ${(rodShim       * 100).toFixed(0)}%` : null,
        rodSafety     !== null ? `Safety: ${(rodSafety   * 100).toFixed(0)}%` : null,
        rodRegulating !== null ? `Regulating: ${(rodRegulating * 100).toFixed(0)}%` : null,
      ].filter(Boolean).join(", ");

      // Determine reactor phase
      const isShutdown = power < 1e-6;
      const isStartup  = !isShutdown && period > 30;  // period > 30s = slow, controlled rise
      const isStable   = !isShutdown && Math.abs(period) > 100;
      const isDanger   = !isShutdown && period < 10;

      let phaseDesc: string;
      if (isShutdown)     phaseDesc = "The reactor is SHUTDOWN (power is essentially zero).";
      else if (isDanger)  phaseDesc = `Power is ${power.toExponential(3)} W. Period is dangerously short at ${period.toFixed(1)} s — reactor is accelerating rapidly.`;
      else if (isStartup) phaseDesc = `Power is ${power.toExponential(3)} W. Period is ${period.toFixed(1)} s — reactor is rising in a controlled startup.`;
      else if (isStable)  phaseDesc = `Power is ${power.toExponential(3)} W. Period is ${period.toFixed(1)} s — reactor is stable.`;
      else                phaseDesc = `Power is ${power.toExponential(3)} W. Period is ${period.toFixed(1)} s.`;

      const rodLine  = rodDesc ? ` Rod positions — ${rodDesc}.` : "";
      const tempLine = ` Fuel Temperature is ${fuelTemp.toFixed(1)} °C.`;

      premise = `ROLE: Nuclear Reactor Operator. GOAL: Bring the reactor to operating power, maintain safe power levels, avoid SCRAMs. CURRENT STATE: ${phaseDesc}${rodLine}${tempLine}`;

      hypotheses = [
        "The reactor needs more reactivity. I will pull ONE control rod UP to raise power.",
        "Power is rising safely. I will STOP the control rods and monitor until stable.",
        "Power is rising too fast or the period is dangerously short. I will push the regulating rod DOWN.",
        "The reactor is out of control. I will trigger a manual SCRAM immediately.",
      ];
    } else {
      // Instructor
      const power = s.indicated?.["power"] ?? 0;
      const scenarioText = scenarioState ? JSON.stringify(scenarioState) : "No active scenario.";
      premise = `ROLE: Simulation Instructor. GOAL: Provide a challenging but solvable scenario for the operator. CURRENT STATE: ${scenarioText}. Power is ${power.toExponential(3)} W.`;

      hypotheses = [
        "The operator is busy. I will wait and observe.",
        "I will trigger an instrument drift fault to confuse the operator.",
        "I will jam a control rod (stuck) to see how they react.",
        "The scenario is complete. I will end the simulation."
      ];
    }

    this.ws.send(JSON.stringify({ premise, hypotheses }));
  }

  private handleMessage(data: string): void {
    try {
      const msg = JSON.parse(data);
      if (msg.error) {
        console.error("[JevCopilot] Server error:", msg.error);
        return;
      }
      const choice = msg.choice;
      if (!choice) return;

      // Only act when the decision changes — avoids hammering the engine
      // with the same rod command every tick when nothing has changed.
      if (choice === this.lastChoice) return;
      this.lastChoice = choice;

      console.log(`[JevCopilot] AI chose: ${choice}`);
      this.executeChoice(choice);
    } catch (err) {
      console.error("[JevCopilot] JSON decode error:", err);
    }
  }

  private executeChoice(choice: string): void {
    if (this.role === "operator") {
      if (choice.includes("pull ONE control rod UP")) {
        // Startup priority: shim first (most reactivity worth), then safety, then regulating.
        // Only move ONE rod at a time to avoid period-short SCRAM.
        const pos = this.rodPositions;
        const AT_LIMIT = 0.99; // treat ≥99% as fully withdrawn
        if ((pos["shim"]       ?? 1) < AT_LIMIT) {
          this.client.command({ type: "rod.move", rod: "shim",       direction: "out" });
        } else if ((pos["safety"]   ?? 1) < AT_LIMIT) {
          this.client.command({ type: "rod.move", rod: "safety",     direction: "out" });
        } else if ((pos["regulating"] ?? 1) < AT_LIMIT) {
          this.client.command({ type: "rod.move", rod: "regulating", direction: "out" });
        }
        // All rods already at limit — nothing to do, model will re-evaluate next tick
      } else if (choice.includes("push the regulating rod DOWN")) {
        this.client.command({ type: "rod.move", rod: "regulating", direction: "in" });
      } else if (choice.includes("STOP the control rods")) {
        // Stop whichever rods are moving
        this.client.command({ type: "rod.move", rod: "shim",       direction: "stop" });
        this.client.command({ type: "rod.move", rod: "safety",     direction: "stop" });
        this.client.command({ type: "rod.move", rod: "regulating", direction: "stop" });
      } else if (choice.includes("manual SCRAM")) {
        this.client.command({ type: "trip.manual" });
      }
    } else {
      if (choice.includes("jam a control rod")) {
        this.client.command({ type: "fault.rod", rod: "transient", kind: "stuck" });
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
