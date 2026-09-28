import json
import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jev-server")

MODEL_ID = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Global state
model = None
tokenizer = None
device = "cuda" if torch.cuda.is_available() else "cpu"

@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, tokenizer
    logger.info(f"Loading {MODEL_ID} on {device}...")
    try:
        # Load the model and tokenizer
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_ID, 
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            low_cpu_mem_usage=True
        ).to(device)
        model.eval()
        logger.info("Model loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
    yield
    logger.info("Shutting down...")

app = FastAPI(lifespan=lifespan)

def evaluate_hypotheses(premise: str, hypotheses: list[str]) -> str:
    """Run a single forward pass of the cross encoder over all hypotheses."""
    if not model or not tokenizer:
        return hypotheses[0] if hypotheses else ""
        
    if not hypotheses:
        return ""
        
    # Format inputs for cross-encoder: pairs of (Premise, Hypothesis)
    pairs = [[premise, hyp] for hyp in hypotheses]
    
    with torch.no_grad():
        inputs = tokenizer(pairs, padding=True, truncation=True, return_tensors="pt").to(device)
        outputs = model(**inputs)
        logits = outputs.logits.squeeze()
        
        if logits.dim() == 0:
            scores = logits.unsqueeze(0)
        elif len(logits.shape) > 1:
            scores = logits[:, -1]
        else:
            scores = logits
            
        best_idx = torch.argmax(scores).item()
        
        # Log the decision process so the user can visualize it
        logger.info("\n--- AI Copilot Decision ---")
        logger.info(f"Premise: {premise}")
        for i, (hyp, score) in enumerate(zip(hypotheses, scores.tolist())):
            marker = ">> " if i == best_idx else "   "
            logger.info(f"{marker}[{score:6.2f}] {hyp}")
            
        return hypotheses[best_idx]

@app.websocket("/ws/{role}")
async def websocket_endpoint(websocket: WebSocket, role: str):
    """
    Role is either 'operator' (30Hz control) or 'instructor' (1Hz chaos).
    """
    await websocket.accept()
    logger.info(f"Client connected as {role}")
    
    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                msg = json.loads(data_str)
            except json.JSONDecodeError:
                logger.warning("Received invalid JSON")
                continue
                
            premise = msg.get("premise", "")
            hypotheses = msg.get("hypotheses", [])
            
            if not premise or not hypotheses:
                await websocket.send_json({"error": "Missing premise or hypotheses"})
                continue
                
            best_choice = evaluate_hypotheses(premise, hypotheses)
            
            await websocket.send_json({
                "choice": best_choice
            })
            
    except WebSocketDisconnect:
        logger.info(f"Client {role} disconnected")
    except Exception as e:
        logger.error(f"Error in websocket loop: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
