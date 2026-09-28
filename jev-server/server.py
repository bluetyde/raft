import json
import logging
import asyncio
import argparse
import sys
import os
from contextlib import asynccontextmanager

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jev-server")

# Global state
args = None
model = None
tokenizer = None
device = "cpu"
mica_backend = None

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-backend", type=str, choices=["deberta", "mica"], default="mica")
    parser.add_argument("--shadow", action="store_true", help="Run Mica in shadow mode without returning commands")
    return parser.parse_args()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global args, model, tokenizer, device, mica_backend
    args = parse_args()

    if args.model_backend == "deberta":
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        MODEL_ID = "cross-encoder/nli-deberta-v3-small"
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading {MODEL_ID} on {device}...")
        try:
            tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
            model = AutoModelForSequenceClassification.from_pretrained(
                MODEL_ID, 
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                low_cpu_mem_usage=True
            ).to(device)
            model.eval()
            logger.info("DeBERTa loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load DeBERTa: {e}")
    else:
        # Load Mica using llama.cpp direct backend
        logger.info("Loading Mica via llama.cpp direct_backend...")
        mica_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Mica-v0.1-4B"))
        if mica_root not in sys.path:
            sys.path.append(mica_root)
        
        try:
            from mica.direct_backend import DirectJudge
            
            # Using tokenizer from HuggingFace
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained("sky7350/Mica-v0.1-4B")
            
            model_path = os.path.join(mica_root, "mica-v0.1-4b-Q5_K_M.gguf")
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Mica GGUF missing at {model_path}")
            
            mica_backend = DirectJudge(
                model_path, 
                tokenizer, 
                runtime_dir=os.path.join(mica_root, "runtime"),
                n_gpu_layers=99,
                n_ctx=4096
            )
            logger.info("Mica loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load Mica: {e}")

    yield
    logger.info("Shutting down...")

app = FastAPI(lifespan=lifespan)

def evaluate_deberta(premise: str, hypotheses: list[str]) -> str:
    import torch
    if not model or not tokenizer:
        raise RuntimeError("DeBERTa Model is not loaded.")
        
    pairs = [[premise, hyp] for hyp in hypotheses]
    with torch.no_grad():
        inputs = tokenizer(pairs, padding=True, truncation=True, return_tensors="pt").to(device)
        outputs = model(**inputs)
        logits = outputs.logits.squeeze()
        
        if logits.dim() == 0:
            scores = logits.unsqueeze(0)
        elif len(logits.shape) > 1 and logits.shape[-1] == 3:
            scores = logits[:, 1]
        elif len(logits.shape) > 1:
            scores = logits[:, -1]
        else:
            scores = logits
            
        best_idx = torch.argmax(scores).item()
        
        logger.info("\n--- AI Copilot Decision (DeBERTa) ---")
        logger.info(f"Premise: {premise}")
        for i, (hyp, score) in enumerate(zip(hypotheses, scores.tolist())):
            marker = ">> " if i == best_idx else "   "
            logger.info(f"{marker}[{score:6.2f}] {hyp}")
            
        return hypotheses[best_idx]

def evaluate_mica(premise: str, hypotheses: list[str]) -> str:
    import time
    from mica.typesafe_server import answer
    from mica.native import prompt_for
    
    if not mica_backend:
        raise RuntimeError("Mica Backend is not loaded.")
    
    start_time = time.time()
    # Construct a row object for Mica's prompt builder
    row = {
        'kind': 'choice',
        'state': premise,
        'question': 'What should the operator do next?',
        'candidates': [{'id': str(i), 'text': hyp} for i, hyp in enumerate(hypotheses)]
    }
    
    prompt = prompt_for(row, tokenizer)
    
    # Run prefill and get probabilities
    # direct_backend.judge takes a list of rows
    probs = mica_backend.judge([row])
    p = probs[0]
    ans = answer(row, p)
    latency_ms = (time.time() - start_time) * 1000
    
    best_idx = int(ans['answer'])
    
    logger.info(f"\n--- AI Copilot Decision (Mica - {latency_ms:.1f}ms) ---")
    logger.info(f"Premise: {premise}")
    for i, hyp in enumerate(hypotheses):
        prob = p[i]
        marker = ">> " if i == best_idx else "   "
        logger.info(f"{marker}[{prob:5.3f}] {hyp}")
        
    return hypotheses[best_idx]

def evaluate_hypotheses(premise: str, hypotheses: list[str]) -> str:
    if not hypotheses:
        return ""
    if args.model_backend == "mica":
        return evaluate_mica(premise, hypotheses)
    else:
        return evaluate_deberta(premise, hypotheses)

@app.websocket("/ws/{role}")
async def websocket_endpoint(websocket: WebSocket, role: str):
    await websocket.accept()
    logger.info(f"Client connected as {role}")
    if args.shadow:
        logger.info("SHADOW MODE ENABLED. Commands will not be returned to the client.")
    
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
                
            try:
                best_choice = await asyncio.to_thread(evaluate_hypotheses, premise, hypotheses)
                
                # In shadow mode, we don't send the choice back to trigger action
                if args.shadow:
                    # Still send an empty choice so the UI knows we finished the inference cycle
                    # (to clear inferenceInFlight)
                    await websocket.send_json({"choice": ""})
                else:
                    await websocket.send_json({"choice": best_choice})
            except Exception as e:
                logger.error(f"Inference error: {e}")
                await websocket.send_json({"error": str(e)})
            
    except WebSocketDisconnect:
        logger.info(f"Client {role} disconnected")
    except Exception as e:
        logger.error(f"Error in websocket loop: {e}")

if __name__ == "__main__":
    import uvicorn
    # Need to run with uvicorn programmatically differently if we want argparse
    # But since uvicorn reloads, argparse inside __main__ gets tricky. 
    uvicorn.run("server:app", host="0.0.0.0", port=8000)
