# OpenJev (System One AI) Integration Plan

## The Concept: System One vs. System Two
In a nuclear reactor, a prompt-critical excursion can spike power by 10,000% in a fraction of a second. Traditional LLMs (System Two thinking) take seconds to generate text and are far too slow to prevent a meltdown. 

We require a **System One (Reflexive) AI**—a model designed for instant, intuitive, millisecond-level decision making.

## The Solution: OpenJev
Instead of training a custom Reinforcement Learning agent from scratch, we will use **[OpenJev](https://huggingface.co/openjev/openjev)**.
OpenJev is an open-source, open-weights System One decision model. It is a "cross-encoder" that does not generate text. Instead, you feed it a **Premise** (the current situation) and a list of **Hypotheses** (the choices), and in a single forward pass (milliseconds), it outputs the calibrated probability of the best choice.

Crucially, **OpenJev requires zero training**. You simply change the JSON prompt to change its behavior.

## Dual AI Architecture: Instructor and Operator
Because OpenJev is dynamically prompted via JSON, we can use the exact same local model to run two distinct AI personas simultaneously by just passing different JSON schemas:

### 1. The Jev Operator
*   **Role:** Fly the reactor. Keep it safe, follow orders, and prevent SCRAMs.
*   **Premise JSON:** Raw telemetry (`Power: 50%, Period: +3s, Control Rod: 150 steps, Target: 100%`).
*   **Hypotheses (Choices):** `["Move Rod UP", "Move Rod DOWN", "STOP", "Trigger Manual SCRAM"]`
*   **Frequency:** 10Hz to 30Hz.

### 2. The Jev Instructor
*   **Role:** Oversee the simulation, introduce chaos, and evaluate the Operator.
*   **Premise JSON:** Scenario state (`Goal: Start up to 100kW. Current Power: 50kW. Time elapsed: 5 mins.`).
*   **Hypotheses (Choices):** `["Wait", "Trigger Pump Failure", "Jam Control Rod", "Mark Scenario Complete"]`
*   **Frequency:** 1Hz.

## The Roadmap: Exact Steps to OpenJev

To get to the point where we can boot up OpenJev, we must finish the underlying simulation infrastructure first.

### Step 1: Finalize Milestone 6 (Fault Injection)
Before the Jev Instructor can introduce chaos, the physics engine must support it.
*   Implement `rod_stuck`, `instrument_drift`, and `scram_failure` faults in the core engine.
*   Expose these faults to the TypeScript command bus.

### Step 2: The Local AI Server (`/jev-server`)
Since the Web UI runs in a browser (TypeScript), and OpenJev runs on your local GPU (Python/PyTorch), we need a bridge.
*   Create a local Python FastAPI/WebSocket server in `virtual-reactor/jev-server/`.
*   Load the `openjev/openjev` model weights into GPU memory.
*   Listen for incoming WebSocket connections.

### Step 3: Web UI Telemetry Client
*   Add a "Connect AI Copilot" button to the Operator and Instructor panels in the browser.
*   Write a serializer that takes the massive 30Hz `snapshot` binary object and compresses it into a tiny JSON string containing only the critical variables (Power, Period, Temps, Rod positions).
*   Stream this JSON to the `jev-server` over the WebSocket.

### Step 4: Prompt Engineering & Loop Tuning
*   Write the formatting functions that translate the telemetry JSON into the strict "Premise / Hypotheses" format required by OpenJev.
*   Tune the loop speed. If 30Hz overloads the local GPU, we throttle the Jev Operator to 10Hz, which is still fast enough to catch a period excursion before a trip.

---
**Next Actions:** Once M6 is officially wrapped, we will begin Step 1 of this plan.
