"""
OSSARTH — mcp_tools/process_mcp.py

Process lifecycle management.
Uses subprocess.Popen for real execution but maintains a simulated process table
in resource_state rather than reading from `ps` or `/proc`.
"""
from __future__ import annotations
import os
import shlex
import signal
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional
from mcp_tools.tool_base import mcp_tool
from kernel_sim.resource_state import get_resource_state

_PROCESS_TIMEOUT = int(os.getenv("OSSARTH_PROCESS_TIMEOUT_SECONDS", "10"))

# Track real subprocess.Popen handles by PID for kill support
_live_processes: dict[int, subprocess.Popen] = {}


@mcp_tool()
def list_processes() -> list:
    """Return the current simulated process table."""
    state = get_resource_state()
    return list(state.get("process_table"))


@mcp_tool()
def start_process(
    cmd: str,
    name: Optional[str] = None,
    timeout_seconds: int = _PROCESS_TIMEOUT,
) -> dict:
    """
    Run a command via subprocess. Adds it to the simulated process table.
    Returns stdout, stderr, returncode, and pid.
    """
    # Security: never pass to shell; use shlex.split
    try:
        args = shlex.split(cmd)
    except ValueError as e:
        raise ValueError(f"Could not parse command '{cmd}': {e}")

    if not args:
        raise ValueError("Empty command")

    process_name = name or args[0]
    state = get_resource_state()

    t0 = time.perf_counter()
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )

    # Add to simulated process table immediately
    pid = state.add_process({
        "name": process_name,
        "cmd": cmd,
        "cpu_percent": 0.0,
        "memory_mb": 0.0,
        "status": "running",
    })
    # Store real PID too (for kill)
    _live_processes[pid] = proc

    try:
        stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_seconds)
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        state.remove_process(pid)
        _live_processes.pop(pid, None)
        raise TimeoutError(
            f"Process '{cmd}' exceeded timeout of {timeout_seconds}s and was killed."
        )

    duration_ms = (time.perf_counter() - t0) * 1000

    # Remove from table once finished (short-lived process)
    state.remove_process(pid)
    _live_processes.pop(pid, None)

    return {
        "pid": pid,
        "cmd": cmd,
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
        "duration_ms": round(duration_ms, 2),
    }


@mcp_tool()
def kill_process(pid: int) -> bool:
    """
    Kill a process by PID. Sends SIGTERM, then SIGKILL after 3 seconds.
    Removes from simulated process table.
    """
    state = get_resource_state()

    # Try to kill the real subprocess if we have a handle
    proc = _live_processes.get(pid)
    if proc is not None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass
        _live_processes.pop(pid, None)

    # Remove from simulated table
    removed = state.remove_process(pid)
    return removed


@mcp_tool()
def get_process_info(pid: int) -> dict:
    """Return the process table entry for a given PID."""
    state = get_resource_state()
    entry = state.get_process(pid)
    if entry is None:
        return {"error": f"No process with PID {pid} found in process table."}
    return entry
