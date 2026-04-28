"""
OSSARTH — mcp_tools/process_mcp.py

Process lifecycle management.
- list_processes: reads REAL running processes from psutil (not simulated state)
- start_process: runs a real subprocess, tracks it in resource_state during execution
- kill_process: terminates a tracked subprocess
- get_process_info: returns info about a tracked process
"""
from __future__ import annotations
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional
from mcp_tools.tool_base import mcp_tool
from kernel_sim.resource_state import get_resource_state

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

_PROCESS_TIMEOUT = int(os.getenv("OSSARTH_PROCESS_TIMEOUT_SECONDS", "10"))

# Track real subprocess.Popen handles by our simulated PID for kill support
_live_processes: dict[int, subprocess.Popen] = {}

# How many real OS processes to show in the table (keep it manageable for the UI)
_PROC_TABLE_LIMIT = 30


@mcp_tool()
def list_processes() -> list:
    """Return a list of currently running OS processes with CPU and memory usage."""
    if HAS_PSUTIL:
        procs = []
        try:
            for proc in psutil.process_iter([
                "pid", "name", "cmdline", "cpu_percent",
                "memory_info", "status", "create_time"
            ]):
                try:
                    info = proc.info
                    cmd = " ".join(info.get("cmdline") or [])
                    mem_mb = round(
                        (info.get("memory_info") or psutil._pslinux.pmem(0, 0)).rss / (1024 * 1024), 1
                    ) if info.get("memory_info") else 0.0
                    started = datetime.fromtimestamp(
                        info.get("create_time") or 0, tz=timezone.utc
                    ).isoformat()
                    procs.append({
                        "pid": info["pid"],
                        "name": info.get("name", "?"),
                        "cmd": cmd[:80] if cmd else "",
                        "cpu_percent": round(info.get("cpu_percent") or 0.0, 1),
                        "memory_mb": mem_mb,
                        "status": info.get("status", "unknown"),
                        "started": started,
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                    continue

            # Sort by CPU usage descending, take top N
            procs.sort(key=lambda p: p["cpu_percent"], reverse=True)
            result = procs[:_PROC_TABLE_LIMIT]

            # Mirror into resource_state so dashboard SSE also picks it up
            state = get_resource_state()
            state.mutate(lambda s: setattr(s, "process_table", result))

            return result

        except Exception as e:
            # Fallback to simulated table on unexpected error
            state = get_resource_state()
            return list(state.get("process_table"))
    else:
        # psutil not available — return simulated table
        state = get_resource_state()
        return list(state.get("process_table"))


@mcp_tool()
def start_process(
    cmd: str,
    name: Optional[str] = None,
    timeout_seconds: int = _PROCESS_TIMEOUT,
) -> dict:
    """
    Run a shell command. Tracks it in the process table while running.
    Returns stdout, stderr, returncode, and pid.
    """
    try:
        args = shlex.split(cmd, posix=(os.name != "nt"))
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
    sim_pid = state.add_process({
        "name": process_name,
        "cmd": cmd,
        "cpu_percent": 0.0,
        "memory_mb": 0.0,
        "status": "running",
        "started": datetime.now(tz=timezone.utc).isoformat(),
    })
    _live_processes[sim_pid] = proc

    try:
        stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_seconds)
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        state.remove_process(sim_pid)
        _live_processes.pop(sim_pid, None)
        raise TimeoutError(
            f"Process '{cmd}' exceeded timeout of {timeout_seconds}s and was killed."
        )

    duration_ms = (time.perf_counter() - t0) * 1000

    # Remove from table once finished (short-lived process)
    state.remove_process(sim_pid)
    _live_processes.pop(sim_pid, None)

    return {
        "pid": sim_pid,
        "cmd": cmd,
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
        "duration_ms": round(duration_ms, 2),
    }


@mcp_tool()
def kill_process(pid: int) -> bool:
    """
    Kill a process by PID. Removes it from the process table.
    """
    state = get_resource_state()

    # Try real subprocess handle if we have one
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

    # Also attempt to kill via psutil if it's a real PID
    if HAS_PSUTIL:
        try:
            os_proc = psutil.Process(pid)
            os_proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            pass

    removed = state.remove_process(pid)
    return removed


@mcp_tool()
def get_process_info(pid: int) -> dict:
    """Return details about a running process by PID."""
    # Check our simulated table first
    state = get_resource_state()
    entry = state.get_process(pid)
    if entry:
        return entry

    # Fall back to psutil for real OS processes
    if HAS_PSUTIL:
        try:
            p = psutil.Process(pid)
            info = p.as_dict(attrs=[
                "pid", "name", "cmdline", "cpu_percent",
                "memory_info", "status", "create_time"
            ])
            return {
                "pid": pid,
                "name": info.get("name", "?"),
                "cmd": " ".join(info.get("cmdline") or []),
                "cpu_percent": round(info.get("cpu_percent") or 0.0, 1),
                "memory_mb": round((info.get("memory_info") or psutil._common.pmem(0, 0)).rss / (1024 * 1024), 1),
                "status": info.get("status", "unknown"),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            pass

    return {"error": f"No process with PID {pid} found."}
