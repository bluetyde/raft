import type { RuntimeClient } from "../runtime/client";
import type { FromWorker } from "../runtime/protocol";

export class JevCopilot {
  private ws: WebSocket | null = null;
  private client: RuntimeClient;
  private role: "operator" | "instructor";
  private enabled: boolean = false;

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
      const power = s.indicated?.["power"] ?? 0;
      const period = s.indicated?.["period"] ?? 0;
      const fuelTemp = s.indicated?.["temp.fuel"] ?? 0;
      
      premise = `ROLE: Nuclear Reactor Operator. GOAL: Maintain safe power levels, avoid SCRAMs, and stabilize the reactor. CURRENT STATE: Power is ${power.toExponential(3)} W, Period is ${period.toFixed(2)} seconds, Fuel Temperature is ${fuelTemp.toFixed(1)} K.`;
      
      // If period is dangerously short, we might want to drop rods or scram.
      hypotheses = [
        "The reactor is stable. I will STOP the control rods and wait.",
        "Power is too low. I will pull the control rod UP to increase reactivity.",
        "Power is rising too fast. I will push the control rod DOWN to reduce reactivity.",
        "The reactor is out of control. I will trigger a manual SCRAM immediately."
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

      console.log(`[JevCopilot] AI chose: ${choice}`);
      this.executeChoice(choice);
    } catch (err) {
      console.error("[JevCopilot] JSON decode error:", err);
    }
  }

  private executeChoice(choice: string): void {
    if (this.role === "operator") {
      if (choice.includes("pull the control rod UP")) {
        this.client.command({ type: "rod.move", rod: "CR1", direction: "out" });
      } else if (choice.includes("push the control rod DOWN")) {
        this.client.command({ type: "rod.move", rod: "CR1", direction: "in" });
      } else if (choice.includes("STOP")) {
        this.client.command({ type: "rod.move", rod: "CR1", direction: "stop" });
      } else if (choice.includes("manual SCRAM")) {
        this.client.command({ type: "trip.manual" });
      }
    } else {
      // Instructor choices
      if (choice.includes("jam a control rod")) {
        this.client.command({ type: "fault.rod", rod: "CR1", kind: "stuck" });
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
