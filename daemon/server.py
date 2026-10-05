import os
import threading
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from laya import Router


def detect_device() -> str:
    env_dev = os.environ.get("LAYA_DEVICE")
    if env_dev:
        return env_dev
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


DEVICE = detect_device()

app = FastAPI(title="sys1-helper Daemon")
router = Router(preload=True, device=DEVICE)

# PyTorch MPS on macOS requires serialization so concurrent threads
# do not overlap command encoding to the Metal buffer.
predict_lock = threading.Lock()


class DecisionPayload(BaseModel):
    state: str
    questions: dict


@app.get("/health")
def health():
    return {"status": "ok", "service": "sys1-helper", "device": DEVICE}


@app.post("/predict")
def predict(payload: DecisionPayload):
    try:
        with predict_lock:
            # If payload exceeds single-window budget (1,200 chars),
            # scan all windows via predict_long to prevent blind spots
            if len(payload.state) > 1200:
                res = router.predict_long(payload.state, payload.questions)
            else:
                res = router.predict(payload.state, payload.questions)
        return res.get("answers", {})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
