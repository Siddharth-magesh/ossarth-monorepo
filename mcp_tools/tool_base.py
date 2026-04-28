"""
OSSARTH — mcp_tools/tool_base.py

Base decorator and contract for all MCP tool functions.

Every tool function must be decorated with @mcp_tool.
The decorator provides:
  - Exception catching (tools never raise — always return ToolResult)
  - Timing (duration_ms on every result)
  - Resource hook dispatch (calls resource_hooks.on_tool_call after every call)
  - Verbose logging
"""
from __future__ import annotations
import functools
import os
import time
from typing import Any, Callable
from mas_core.schemas import ToolResult


def mcp_tool(step: int = 0, tool_name: str = ""):
    """
    Decorator factory for MCP tool functions.

    Usage:
        @mcp_tool()
        def read_file(path: str) -> str:
            ...

    The decorated function:
    - Returns ToolResult on success or failure
    - Never raises
    - Calls resource_hooks.on_tool_call() after execution
    """
    def decorator(fn: Callable) -> Callable:
        name = tool_name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> ToolResult:
            verbose = os.getenv("OSSARTH_VERBOSE", "false").lower() == "true"
            # Step number may be injected by the runner
            _step = kwargs.pop("_step", step) or 0

            if verbose:
                print(f"  [TOOL] {name}({kwargs})")

            t0 = time.perf_counter()
            result_output = None
            error_msg = None
            success = False

            try:
                result_output = fn(*args, **kwargs)
                success = True
            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                if verbose:
                    print(f"  [TOOL ERROR] {name}: {error_msg}")

            duration_ms = (time.perf_counter() - t0) * 1000

            tool_result = ToolResult(
                step=_step,
                tool=name,
                success=success,
                output=result_output,
                error=error_msg,
                duration_ms=round(duration_ms, 2),
            )

            # Dispatch resource hook (never crash on hook failure)
            try:
                from kernel_sim.resource_hooks import on_tool_call
                all_args = {**dict(zip(fn.__code__.co_varnames, args)), **kwargs}
                on_tool_call(name, all_args, result_output)
            except Exception:
                pass

            if verbose:
                status = "OK" if success else "FAIL"
                print(f"  [TOOL {status}] {name} → {duration_ms:.1f}ms")

            return tool_result

        wrapper._is_mcp_tool = True
        wrapper._tool_name = name
        return wrapper

    return decorator
