"""
OSSARTH — kernel_sim/resource_hooks.py

Functions called by the @mcp_tool decorator after every tool execution.
Each hook knows how a given tool type affects resource state and mutates accordingly.
"""
from __future__ import annotations
import math
import random
import threading
from pathlib import Path
from typing import Any, Optional
from kernel_sim.resource_state import get_resource_state


def _schedule_reversal(delay: float, fn) -> None:
    t = threading.Timer(delay, fn)
    t.daemon = True
    t.start()


def on_write_file(path: str, content: str, result: Any) -> None:
    state = get_resource_state()
    content_bytes = len(content.encode("utf-8")) if content else 0
    state.track_file(path, content_bytes)
    bump_mb = max(1, math.ceil(content_bytes / 1024))
    state.bump_ram(bump_mb)
    state.flush_to_file()
    _schedule_reversal(3.0, lambda: (state.bump_ram(-bump_mb), state.flush_to_file()))


def on_read_file(path: str, result: Any) -> None:
    state = get_resource_state()
    try:
        size_bytes = Path(path).stat().st_size
    except Exception:
        size_bytes = 4096
    bump_mb = max(1, math.ceil(size_bytes / 1024))
    state.bump_ram(bump_mb)
    state.flush_to_file()
    _schedule_reversal(5.0, lambda: (state.bump_ram(-bump_mb), state.flush_to_file()))


def on_delete_file(path: str, result: Any) -> None:
    state = get_resource_state()
    state.untrack_file(path)
    state.flush_to_file()


def on_append_file(path: str, content: str, result: Any) -> None:
    state = get_resource_state()
    bump_mb = max(1, math.ceil(len(content.encode("utf-8")) / 1024))
    state.bump_ram(bump_mb)
    state.flush_to_file()
    _schedule_reversal(2.0, lambda: (state.bump_ram(-bump_mb), state.flush_to_file()))


def on_search_directory(path: str, query: str, result: Any) -> None:
    state = get_resource_state()
    cpu_bump = random.uniform(5.0, 10.0)
    result_count = len(result) if isinstance(result, list) else 1
    ram_bump = max(1, min(20, result_count))
    state.bump_cpu(cpu_bump)
    state.bump_ram(ram_bump)
    state.flush_to_file()
    _schedule_reversal(2.0, lambda: (
        state.bump_cpu(-cpu_bump), state.bump_ram(-ram_bump), state.flush_to_file()
    ))


def on_start_process(cmd: str, pid: Optional[int], result: Any) -> None:
    state = get_resource_state()
    cpu_bump = random.uniform(15.0, 25.0)
    ram_bump = random.randint(30, 80)
    state.bump_cpu(cpu_bump)
    state.bump_ram(ram_bump)
    state.bump_threads(1)
    state.flush_to_file()
    _schedule_reversal(10.0, lambda: (
        state.bump_cpu(-cpu_bump), state.bump_ram(-ram_bump),
        state.bump_threads(-1), state.flush_to_file()
    ))


def on_kill_process(pid: int, result: Any) -> None:
    state = get_resource_state()
    state.bump_cpu(-random.uniform(5.0, 15.0))
    state.bump_ram(-random.randint(20, 60))
    state.bump_threads(-1)
    state.flush_to_file()


def on_llm_call(agent_name: str, tokens_used: int = 256) -> None:
    """Called by agents when making an LLM call — shows thinking has a cost."""
    state = get_resource_state()
    ram_bump = max(5, math.ceil((tokens_used * 4) / 1024))
    cpu_bump = random.uniform(2.0, 6.0)
    state.bump_ram(ram_bump)
    state.bump_cpu(cpu_bump)
    state.flush_to_file()
    _schedule_reversal(3.0, lambda: (
        state.bump_ram(-ram_bump), state.bump_cpu(-cpu_bump), state.flush_to_file()
    ))


def on_tool_call(tool_name: str, args: dict, result: Any) -> None:
    """Master dispatcher — called by @mcp_tool decorator after every execution."""
    try:
        if tool_name == "write_file":
            on_write_file(args.get("path", ""), args.get("content", ""), result)
        elif tool_name == "read_file":
            on_read_file(args.get("path", ""), result)
        elif tool_name == "delete_file":
            on_delete_file(args.get("path", ""), result)
        elif tool_name == "append_file":
            on_append_file(args.get("path", ""), args.get("content", ""), result)
        elif tool_name == "search_directory":
            on_search_directory(args.get("path", ""), args.get("query", ""), result)
        elif tool_name == "start_process":
            pid = result.get("pid") if isinstance(result, dict) else None
            on_start_process(args.get("cmd", ""), pid, result)
        elif tool_name == "kill_process":
            on_kill_process(args.get("pid", 0), result)
        elif tool_name in ("get_network_interfaces", "check_port", "get_hostname"):
            state = get_resource_state()
            bump = random.uniform(1.0, 3.0)
            state.bump_cpu(bump)
            state.flush_to_file()
            _schedule_reversal(1.0, lambda: (state.bump_cpu(-bump), state.flush_to_file()))
    except Exception:
        pass  # Never crash the daemon from a hook
