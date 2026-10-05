.PHONY: install start stop status install-hooks test clean

VENV := .venv
PYTHON := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
PID_FILE := .daemon.pid

install:
	$(PYTHON) -m pip install -e . || $(PYTHON) -m pip install "laya>=0.1.0" "fastapi>=0.110.0" "uvicorn>=0.28.0" "requests>=2.31.0"

start:
	@./scripts/start_daemon.sh

stop:
	@if [ -f $(PID_FILE) ]; then \
		PID=$$(cat $(PID_FILE)); \
		echo "Stopping Laya daemon (PID $$PID)..."; \
		kill $$PID 2>/dev/null || true; \
		rm -f $(PID_FILE); \
		echo "Daemon stopped."; \
	else \
		echo "PID file not found. Trying pkill..."; \
		pkill -f "daemon/server.py" || echo "No running daemon found."; \
	fi

status:
	@curl -s -f http://127.0.0.1:8765/health && echo " Daemon is running healthy." || echo " Daemon is not responding."

install-hooks:
	@./scripts/install_hooks.sh $(TARGET)

test:
	$(PYTHON) -m unittest discover -s tests -p "*_test.py"

simulate:
	@$(PYTHON) ./scripts/simulate_check.py

clean:
	rm -f $(PID_FILE) daemon.log
