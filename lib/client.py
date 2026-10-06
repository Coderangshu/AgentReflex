import json
import urllib.request
import urllib.error

DAEMON_URL = "http://127.0.0.1:8765/predict"
HEALTH_URL = "http://127.0.0.1:8765/health"


def is_daemon_alive(timeout: float = 1.0) -> bool:
    """Check if the local Laya daemon is running and reachable."""
    try:
        req = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def query_laya(state: str, questions: dict, timeout: float = 3.0) -> dict:
    """Send state and questions to the local Laya daemon."""
    try:
        payload = json.dumps({"state": state, "questions": questions}).encode("utf-8")
        req = urllib.request.Request(
            DAEMON_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
            return {}
    except Exception:
        return {}
