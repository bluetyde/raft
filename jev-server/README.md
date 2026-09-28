# OpenJev AI Server

This is the Python FastAPI server that hosts the local `openjev/openjev` model. It acts as a WebSocket bridge between the `virtual-reactor` web interface (which provides 30Hz simulation telemetry) and the AI (which runs locally on your GPU).

## Setup

1. Create a virtual environment and install the dependencies:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Run the server:
   ```bash
   python server.py
   ```

## Architecture

The server exposes a WebSocket endpoint at `ws://localhost:8000/ws/{role}`, where `{role}` can be `operator` or `instructor`.

The Web client sends a JSON payload:
```json
{
  "premise": "Power: 50%, Period: +3s. Goal: Keep power stable.",
  "hypotheses": [
    "Move Rod UP",
    "Move Rod DOWN",
    "STOP"
  ]
}
```

The server evaluates these choices in a single forward pass of the cross-encoder and instantly responds:
```json
{
  "choice": "Move Rod DOWN"
}
```
