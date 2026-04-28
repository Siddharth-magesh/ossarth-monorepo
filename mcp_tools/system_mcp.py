"""
OSSARTH — mcp_tools/system_mcp.py

Lightweight read-only system tools.
Let the Orchestrator answer questions like:
  "how much RAM is being used?"
  "what did I run earlier?"
  "how long has the daemon been running?"
"""
from __future__ import annotations
from mcp_tools.tool_base import mcp_tool


@mcp_tool()
def get_resource_snapshot() -> dict:
    """Return a full snapshot of current simulated system resources."""
    from kernel_sim.resource_state import get_resource_state
    return get_resource_state().to_dict()


@mcp_tool()
def get_uptime() -> float:
    """Return the daemon uptime in seconds."""
    from kernel_sim.resource_state import get_resource_state
    return get_resource_state().to_dict().get("uptime_seconds", 0.0)


@mcp_tool()
def get_command_history(n: int = 10) -> list:
    """Return the last N commands processed by the daemon."""
    # Imported here to avoid circular imports at module load time
    try:
        from mas_core.context_manager import ContextManager
        # The context_manager is a singleton managed by agent_runner
        # For tool calls, we read from the module-level instance
        import mas_core.agent_runner as runner
        if hasattr(runner, "_context_manager"):
            cm = runner._context_manager
            recent = list(cm._history)[-n:]
            return [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "input": e.raw_input,
                    "task_type": e.intent.task_type,
                    "tools_used": [r.tool for r in e.results],
                    "success": e.success,
                    "duration_ms": e.total_duration_ms,
                }
                for e in recent
            ]
    except Exception:
        pass
    return []
