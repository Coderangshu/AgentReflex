import requests

DAEMON_URL = "http://127.0.0.1:8765/predict"
HEALTH_URL = "http://127.0.0.1:8765/health"


def is_daemon_alive(timeout: float = 1.0) -> bool:
    """Check if the local Laya daemon is running and reachable."""
    try:
        resp = requests.get(HEALTH_URL, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def query_laya(state: str, questions: dict, timeout: float = 3.0) -> dict:
    """Send state and questions to the local Laya daemon."""
    try:
        resp = requests.post(
            DAEMON_URL,
            json={"state": state, "questions": questions},
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        return {}
    except Exception:
        return {}
