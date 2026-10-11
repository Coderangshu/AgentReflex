import http.client
import json
import os
import socket
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_UDS_PATH = os.environ.get("AGENTREFLEX_SOCKET_PATH", "/tmp/agentreflex.sock")
DAEMON_URL = os.environ.get("AGENTREFLEX_DAEMON_URL", "http://127.0.0.1:8765/predict")
HEALTH_URL = os.environ.get("AGENTREFLEX_HEALTH_URL", "http://127.0.0.1:8765/health")


class UDSHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection over Unix Domain Socket."""

    def __init__(self, socket_path: str, timeout: float = 10.0):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def _query_uds(endpoint: str, payload_bytes: Optional[bytes], method: str = "POST", timeout: float = 10.0) -> Optional[dict]:
    """Attempt HTTP query over Unix Domain Socket."""
    if not (hasattr(socket, "AF_UNIX") and os.path.exists(DEFAULT_UDS_PATH)):
        return None
    conn = None
    try:
        conn = UDSHTTPConnection(DEFAULT_UDS_PATH, timeout=timeout)
        headers = {"Content-Type": "application/json"} if payload_bytes else {}
        conn.request(method, endpoint, body=payload_bytes, headers=headers)
        resp = conn.getresponse()
        if resp.status == 200:
            return json.loads(resp.read().decode("utf-8"))
        return None
    except Exception:
        return None
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def is_daemon_alive(timeout: float = 1.0) -> bool:
    """Check if local Laya daemon is reachable via UDS or TCP fallback."""
    # 1. Try UDS
    uds_res = _query_uds("/health", payload_bytes=None, method="GET", timeout=timeout)
    if uds_res and uds_res.get("status") == "ok":
        return True

    # 2. Fallback to TCP
    try:
        req = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def query_laya(state: str, questions: dict, timeout: float = 10.0) -> dict:
    """Send state and questions to Laya daemon via UDS (with TCP fallback)."""
    payload_bytes = json.dumps({"state": state, "questions": questions}).encode("utf-8")

    # 1. Primary: Unix Domain Socket (zero TCP overhead)
    uds_res = _query_uds("/predict", payload_bytes=payload_bytes, method="POST", timeout=timeout)
    if uds_res is not None:
        return uds_res

    # 2. Fallback: Localhost TCP
    try:
        req = urllib.request.Request(
            DAEMON_URL,
            data=payload_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
            return {}
    except Exception:
        return {}


def trigger_prefetch(tool: str, args: dict, cwd: str = "", timeout: float = 2.0) -> dict:
    """Send speculative prefetch trigger to daemon over UDS."""
    payload_bytes = json.dumps({"tool": tool, "args": args, "cwd": cwd}).encode("utf-8")
    uds_res = _query_uds("/prefetch/trigger", payload_bytes=payload_bytes, method="POST", timeout=timeout)
    return uds_res or {}


def claim_prefetch(tool: str, args: dict, timeout: float = 2.0) -> dict:
    """Claim speculative prefetch result from daemon over UDS."""
    payload_bytes = json.dumps({"tool": tool, "args": args}).encode("utf-8")
    uds_res = _query_uds("/prefetch/claim", payload_bytes=payload_bytes, method="POST", timeout=timeout)
    return uds_res or {}


def invalidate_prefetch(timeout: float = 1.0) -> dict:
    """Invalidate all speculative cache entries in daemon over UDS on mutating actions."""
    uds_res = _query_uds("/prefetch/invalidate", payload_bytes=b"{}", method="POST", timeout=timeout)
    return uds_res or {}
