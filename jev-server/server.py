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

def evaluate_deberta(premise: str, candidates: list[dict]) -> str:
    import torch
    if not model or not tokenizer:
        raise RuntimeError("DeBERTa Model is not loaded.")
        
    hypotheses = [c["text"] for c in candidates]
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
        for i, (cand, score) in enumerate(zip(candidates, scores.tolist())):
            marker = ">> " if i == best_idx else "   "
            logger.info(f"{marker}[{score:6.2f}] {cand['text']}")
            
        return candidates[best_idx]["id"]

def evaluate_mica(premise: str, candidates: list[dict]) -> str:
    from mica.typesafe_server import answer
    from mica.native import prompt_for
    
    if not mica_backend:
        raise RuntimeError("Mica Backend is not loaded.")
    
    # Construct a row object for Mica's prompt builder
    # Note: Mica candidate ids must match the original index, so we pass index as id
    row = {
        'kind': 'choice',
        'state': premise,
        'question': 'What should the operator do next?',
        'candidates': [{'id': str(i), 'text': c["text"]} for i, c in enumerate(candidates)]
    }
    
    prompt = prompt_for(row, tokenizer)
    
    probs = mica_backend.judge([row])
    p = probs[0]
    ans = answer(row, p)
    
    best_idx = int(ans['answer'])
    
    logger.info(f"\n--- AI Copilot Decision (Mica) ---")
    logger.info(f"Premise: {premise}")
    for i, cand in enumerate(candidates):
        prob = p[i]
        marker = ">> " if i == best_idx else "   "
        logger.info(f"{marker}[{prob:5.3f}] {cand['text']}")
        
    return candidates[best_idx]["id"]

def evaluate_hypotheses(premise: str, candidates: list[dict]) -> str:
    if not candidates:
        return ""
    if args.model_backend == "mica":
        return evaluate_mica(premise, candidates)
    else:
        return evaluate_deberta(premise, candidates)

@app.websocket("/ws/{role}")
async def websocket_endpoint(websocket: WebSocket, role: str):
    await websocket.accept()
    logger.info(f"Client connected as {role}")
    if args.shadow:
        logger.info("SHADOW MODE ENABLED. Commands will not be returned to the client.")
    
    try:
        while True:
            data_str = await websocket.receive_text()
            import time
            start_time = time.time()
            try:
                msg = json.loads(data_str)
            except json.JSONDecodeError:
                logger.warning("Received invalid JSON")
                continue
                
            # Parse versioned protocol
            protocol_version = msg.get("protocolVersion")
            if protocol_version != 1:
                logger.warning(f"Unsupported protocol version: {protocol_version}")
                await websocket.send_json({"status": "error", "errorCode": "INVALID_PROTOCOL"})
                continue
                
            req_id = msg.get("requestId")
            session_id = msg.get("sessionId")
            epoch = msg.get("temporalEpoch")
            conn_id = msg.get("connectionId")
            obs_step = msg.get("observationStep")
            
            premise = msg.get("premise", "")
            candidates = msg.get("candidates", [])
            
            if not premise or not candidates:
                await websocket.send_json({
                    "protocolVersion": 1,
                    "sessionId": session_id,
                    "temporalEpoch": epoch,
                    "connectionId": conn_id,
                    "requestId": req_id,
                    "observationStep": obs_step,
                    "status": "error",
                    "errorCode": "INVALID_PAYLOAD"
                })
                continue
                
            try:
                best_candidate_id = await asyncio.to_thread(evaluate_hypotheses, premise, candidates)
                latency_ms = (time.time() - start_time) * 1000
                
                response = {
                    "protocolVersion": 1,
                    "sessionId": session_id,
                    "temporalEpoch": epoch,
                    "connectionId": conn_id,
                    "requestId": req_id,
                    "observationStep": obs_step,
                    "status": "ok",
                    "inferenceDurationMs": latency_ms
                }
                
                if args.shadow:
                    # In shadow mode, we return status OK but no candidateId
                    pass
                else:
                    response["candidateId"] = best_candidate_id
                    
                await websocket.send_json(response)
            except Exception as e:
                logger.error(f"Inference error: {e}")
                await websocket.send_json({
                    "protocolVersion": 1,
                    "sessionId": session_id,
                    "temporalEpoch": epoch,
                    "connectionId": conn_id,
                    "requestId": req_id,
                    "observationStep": obs_step,
                    "status": "error",
                    "errorCode": "INTERNAL_ERROR"
                })
            
    except WebSocketDisconnect:
        logger.info(f"Client {role} disconnected")
    except Exception as e:
        logger.error(f"Error in websocket loop: {e}")

if __name__ == "__main__":
    import uvicorn
    # Need to run with uvicorn programmatically differently if we want argparse
    # But since uvicorn reloads, argparse inside __main__ gets tricky. 
    uvicorn.run("server:app", host="0.0.0.0", port=8000)
