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

The server listens on this machine only (`127.0.0.1`; set `JEV_HOST` and `JEV_PORT` to change) and accepts only browser pages served from this machine (`JEV_ALLOWED_ORIGINS`, comma separated, adds others). Requests are bounded: 100 000 characters a message, 32 candidates, one inference at a time. It has no authentication, so do not expose it on a network you do not trust. The package versions in `requirements.txt` are the ones it was run with.

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
