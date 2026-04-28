#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# OSSARTH — Linux/Mac Launch Script
# Run from the repo root: ./os_customization/launch.sh
# ─────────────────────────────────────────────────────────

set -e

# Check .env exists
if [ ! -f ".env" ]; then
    echo "[ERROR] .env file not found."
    echo "Copy .env.example to .env and fill in your GROQ_API_KEY."
    exit 1
fi

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "[OSSARTH] Virtual environment activated."
else
    echo "[OSSARTH] No venv found — using system Python."
    echo "          Run: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
fi

# Create logs directory
mkdir -p logs

# Check if Ollama is running
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[OSSARTH] Ollama detected."
else
    echo "[OSSARTH] WARNING: Ollama not detected on localhost:11434"
    echo "          Start with: ollama serve"
    echo "          Or set OSSARTH_LLM_PROVIDER=groq in .env"
    echo ""
fi

# Start dashboard in background
echo "[OSSARTH] Starting dashboard server on port 8000..."
python -m uvicorn dashboard.server:app --host 0.0.0.0 --port 8000 > logs/dashboard.log 2>&1 &
DASHBOARD_PID=$!
echo "[OSSARTH] Dashboard PID: $DASHBOARD_PID"

# Wait for dashboard to be ready
sleep 2

# Open browser if display is available
if command -v xdg-open &> /dev/null && [ -n "$DISPLAY" ]; then
    xdg-open http://localhost:8000 &> /dev/null &
elif command -v open &> /dev/null; then
    open http://localhost:8000 &
fi

echo "[OSSARTH] Dashboard available at http://localhost:8000"
echo "[OSSARTH] Starting OSSARTH daemon (REPL)..."
echo ""

# Start REPL in foreground (blocking)
python -m mas_core.agent_runner "$@"

# Cleanup on exit
echo ""
echo "[OSSARTH] Shutting down dashboard (PID $DASHBOARD_PID)..."
kill $DASHBOARD_PID 2>/dev/null || true
echo "[OSSARTH] Shutdown complete."
