#!/usr/bin/env bash
set -e

TOOLKIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$TOOLKIT_ROOT/.daemon.pid"
LOG_FILE="$TOOLKIT_ROOT/daemon.log"

PYTHON_BIN="python3"
if [ -f "$TOOLKIT_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$TOOLKIT_ROOT/.venv/bin/python"
fi

if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "Laya daemon already running with PID $PID"
    exit 0
  fi
fi

# Also check if port 8765 is responding
if curl -s http://127.0.0.1:8765/health > /dev/null 2>&1; then
  echo "Laya daemon is already healthy and listening on http://127.0.0.1:8765"
  exit 0
fi

if [ ! -f "$TOOLKIT_ROOT/.venv/bin/python" ]; then
  echo "⚠️  Virtual environment not detected at .venv"
  echo "    Recommended setup:"
  echo "    python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
fi

echo "Starting AgentReflex Laya daemon in background..."
echo "(First run downloads ~300MB Laya model weights to your environment)..."
nohup "$PYTHON_BIN" "$TOOLKIT_ROOT/daemon/server.py" > "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"

echo "Daemon process started with PID $PID (logs: $LOG_FILE)"

# Wait up to 30 seconds for daemon to finish loading / downloading checkpoint
for i in {1..60}; do
  if curl -s http://127.0.0.1:8765/health > /dev/null 2>&1; then
    echo "✅ AgentReflex daemon is healthy at http://127.0.0.1:8765"
    exit 0
  fi
  sleep 0.5
done

echo "⚠️ Daemon started, but health check is taking longer than expected. Check logs: $LOG_FILE"
