from __future__ import annotations
import asyncio
import os
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Optional
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from laya import Router

sys.path.append(str(Path(__file__).resolve().parent.parent))

DEFAULT_UDS_PATH = os.environ.get("AGENTREFLEX_SOCKET_PATH", "/tmp/agentreflex.sock")
TCP_HOST = os.environ.get("AGENTREFLEX_HOST", "127.0.0.1")
TCP_PORT = int(os.environ.get("AGENTREFLEX_PORT", 8765))


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

app = FastAPI(title="AgentReflex Daemon")
router = Router(preload=True, device=DEVICE)

# PyTorch MPS on macOS requires serialization so concurrent threads
# do not overlap command encoding to the Metal buffer.
predict_lock = threading.Lock()


from lib.server_logger import log_server_event, log_activity, SERVER_LOG_FILE


class DecisionPayload(BaseModel):
    state: str
    questions: dict


class ActivityPayload(BaseModel):
    project: str = ""
    agent: str = ""
    tool: str = ""
    args: Any = {}
    response: Any = ""
    status: str = "success"
    duration_ms: Optional[float] = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "agentreflex",
        "device": DEVICE,
        "socket": DEFAULT_UDS_PATH if os.path.exists(DEFAULT_UDS_PATH) else None,
        "log_file": str(SERVER_LOG_FILE),
    }


@app.post("/log_activity")
def log_activity_endpoint(payload: ActivityPayload):
    log_activity(
        project=payload.project,
        agent=payload.agent,
        tool=payload.tool,
        args=payload.args,
        response=payload.response,
        status=payload.status,
        duration_ms=payload.duration_ms,
    )
    return {"status": "logged"}


@app.get("/logs")
def get_recent_logs(lines: int = 50):
    if not SERVER_LOG_FILE.exists():
        return {"lines": []}
    try:
        content = SERVER_LOG_FILE.read_text(encoding="utf-8", errors="replace")
        all_lines = [l for l in content.splitlines() if l.strip()]
        return {"lines": all_lines[-lines:], "total_lines": len(all_lines)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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


async def run_servers():
    config_tcp = uvicorn.Config(app, host=TCP_HOST, port=TCP_PORT, log_level="warning")
    server_tcp = uvicorn.Server(config_tcp)
    tasks = [server_tcp.serve()]

    has_uds = hasattr(socket, "AF_UNIX") and sys.platform != "win32"
    if has_uds:
        if os.path.exists(DEFAULT_UDS_PATH):
            try:
                os.remove(DEFAULT_UDS_PATH)
            except OSError:
                pass
        config_uds = uvicorn.Config(app, uds=DEFAULT_UDS_PATH, log_level="warning")
        server_uds = uvicorn.Server(config_uds)
        tasks.append(server_uds.serve())

    log_server_event(
        "STARTUP",
        f"Daemon listening on device={DEVICE} (tcp={TCP_HOST}:{TCP_PORT}, uds={DEFAULT_UDS_PATH if has_uds else 'none'})",
    )
    try:
        await asyncio.gather(*tasks)
    finally:
        log_server_event("SHUTDOWN", "Daemon stopped")
        if has_uds and os.path.exists(DEFAULT_UDS_PATH):
            try:
                os.remove(DEFAULT_UDS_PATH)
            except OSError:
                pass


if __name__ == "__main__":
    asyncio.run(run_servers())
