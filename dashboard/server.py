"""
OSSARTH — dashboard/server.py

FastAPI backend for the System Monitor Dashboard.

Endpoints:
  GET  /           → serves static/index.html
  GET  /metrics    → SSE stream of resource_state every second
  GET  /history    → last N seconds of resource snapshots (for sparklines)
  POST /command    → run a natural language command through the full MAS
  GET  /history/commands → last 20 command log entries from context_manager
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# Force UTF-8 encoding for Windows console (fixes cp1252 errors for ✓ and ✗ characters)
for stream in (sys.stdout, sys.stderr):
    if stream.encoding.lower() != "utf-8" and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

import time
from collections import deque
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

# ─────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────

app = FastAPI(
    title="OSSARTH System Monitor",
    description="Real-time dashboard for the OSSARTH AI OS daemon",
    version="0.1.0",
)

STATIC_DIR = Path(__file__).parent / "static"
STATE_FILE = Path(os.getenv("OSSARTH_STATE_FILE", "ossarth_state.json"))
DASHBOARD_PORT = int(os.getenv("OSSARTH_DASHBOARD_PORT", "8000"))

# Ensure workspace is resolved to an absolute path for the MAS pipeline
workspace = os.getenv("OSSARTH_WORKSPACE", "./ossarth_workspace")
workspace_path = str(Path(workspace).resolve())
os.environ["OSSARTH_WORKSPACE"] = workspace_path
Path(workspace_path).mkdir(parents=True, exist_ok=True)

# History ring buffer: last 300 snapshots (5 minutes at 1/sec)
_history: deque[dict] = deque(maxlen=300)
_last_state: dict = {}


# ─────────────────────────────────────────────────────────
# State reading (from IPC file written by daemon)
# ─────────────────────────────────────────────────────────

def _read_state() -> dict:
    """Read the current resource state from the IPC file."""
    global _last_state
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _last_state = data
            return data
    except Exception:
        pass
    return _last_state or {
        "cpu_usage_percent": 0,
        "used_ram_mb": 0,
        "total_ram_mb": 8192,
        "used_gpu_vram_mb": 0,
        "total_gpu_vram_mb": 4096,
        "active_threads": 0,
        "process_table": [],
        "scheduler_queue": [],
        "context_switches_per_sec": 0,
        "uptime_seconds": 0,
        "command_count": 0,
        "cpu_per_core": [0] * 8,
    }


# ─────────────────────────────────────────────────────────
# Background task: populate history ring buffer
# ─────────────────────────────────────────────────────────

async def _history_collector():
    """Collect one state snapshot per second into the ring buffer."""
    while True:
        snapshot = _read_state()
        snapshot["_ts"] = time.time()
        _history.append(snapshot)
        await asyncio.sleep(1.0)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_history_collector())


# ─────────────────────────────────────────────────────────
# GET /
# ─────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return JSONResponse({"error": "index.html not found"}, status_code=404)
    return FileResponse(str(index_path))


# Mount static files (CSS, JS)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─────────────────────────────────────────────────────────
# GET /metrics  — SSE stream
# ─────────────────────────────────────────────────────────

async def _sse_generator() -> AsyncGenerator[str, None]:
    """Yield SSE events every second."""
    tick = 0
    while True:
        state = _read_state()
        data = json.dumps(state, separators=(",", ":"))
        yield f"data: {data}\n\n"
        tick += 1
        # Keepalive comment every 15 seconds
        if tick % 15 == 0:
            yield ": keepalive\n\n"
        await asyncio.sleep(1.0)


@app.get("/metrics")
async def metrics_sse():
    """Server-Sent Events endpoint — streams resource state every second."""
    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────────────────
# GET /history
# ─────────────────────────────────────────────────────────

@app.get("/history")
async def get_history(seconds: int = 60):
    """Return the last N seconds of resource snapshots for sparklines."""
    snapshots = list(_history)
    cutoff = time.time() - seconds
    filtered = [s for s in snapshots if s.get("_ts", 0) >= cutoff]
    # Strip the internal timestamp key before returning
    return JSONResponse([{k: v for k, v in s.items() if k != "_ts"} for s in filtered])


# ─────────────────────────────────────────────────────────
# GET /history/commands
# ─────────────────────────────────────────────────────────

@app.get("/history/commands")
async def get_command_history():
    """Return last 20 command log entries from the context manager."""
    try:
        import mas_core.agent_runner as runner
        if hasattr(runner, "_context_manager") and runner._context_manager:
            cm = runner._context_manager
            recent = list(cm._history)[-20:]
            return JSONResponse([
                {
                    "timestamp": e.timestamp.isoformat(),
                    "input": e.raw_input,
                    "task_type": e.intent.task_type,
                    "tools_used": [r.tool for r in e.results],
                    "success": e.success,
                    "duration_ms": e.total_duration_ms,
                    "results": [
                        {
                            "tool": r.tool,
                            "success": r.success,
                            "output": str(r.output)[:200] if r.output else None,
                            "error": r.error,
                        }
                        for r in e.results
                    ],
                }
                for e in recent
            ])
    except Exception:
        pass
    return JSONResponse([])


# ─────────────────────────────────────────────────────────
# POST /command
# ─────────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    input: str


@app.post("/command")
async def run_command(req: CommandRequest):
    """
    Accept a natural language command, run it through the full MAS pipeline,
    and return the results.
    """
    raw_input = req.input.strip()
    if not raw_input:
        raise HTTPException(status_code=400, detail="Input cannot be empty")

    try:
        # Import the MAS components — they may or may not be running in the same process
        from mas_core.intent_agent import IntentAgent
        from mas_core.orchestrator_agent import OrchestratorAgent
        from mcp_tools.tool_registry import ToolRegistry
        from mas_core.agent_runner import dispatch_execution_graph

        registry = ToolRegistry()
        registry.initialize()

        intent_agent = IntentAgent(verbose=False)
        orchestrator = OrchestratorAgent(tool_registry=registry, verbose=False)

        t0 = time.perf_counter()

        # Run in a thread pool to avoid blocking the async event loop
        loop = asyncio.get_event_loop()
        intent = await loop.run_in_executor(None, intent_agent.classify, raw_input)
        graph = await loop.run_in_executor(None, orchestrator.plan, intent)
        results = await loop.run_in_executor(
            None, dispatch_execution_graph, graph, registry, False
        )

        total_ms = (time.perf_counter() - t0) * 1000

        return JSONResponse({
            "input": raw_input,
            "intent": intent.model_dump(),
            "graph": [s.model_dump() for s in graph.steps],
            "results": [
                {
                    "step": r.step,
                    "tool": r.tool,
                    "success": r.success,
                    "output": str(r.output)[:500] if r.output is not None else None,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                }
                for r in results
            ],
            "duration_ms": round(total_ms, 2),
            "all_succeeded": all(r.success for r in results),
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "state_file": str(STATE_FILE), "state_file_exists": STATE_FILE.exists()}


# ─────────────────────────────────────────────────────────
# Dev entrypoint
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "dashboard.server:app",
        host="0.0.0.0",
        port=DASHBOARD_PORT,
        reload=False,
        log_level="warning",
    )
