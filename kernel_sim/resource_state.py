"""
OSSARTH — kernel_sim/resource_state.py

Single source of truth for all simulated hardware and OS resource values.
One global singleton. All reads and writes go through this module.

Thread safety: all mutation methods acquire a threading.Lock.
The dashboard SSE stream reads from a separate thread — always lock before writing.

IPC with dashboard: flush_to_file() writes JSON to disk after every mutation.
The dashboard server reads this file every second for its SSE stream.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ─────────────────────────────────────────────────────────
# Resource State Dataclass
# ─────────────────────────────────────────────────────────

@dataclass
class KernelResourceState:
    """
    Simulated kernel resource model.
    Represents what an AI-controlled kernel would track and expose.
    """

    # ── Hardcoded Hardware Caps (never change at runtime) ──
    total_ram_mb: int = 8192
    total_gpu_vram_mb: int = 4096
    total_cpu_cores: int = 8
    max_scheduler_threads: int = 64
    cpu_clock_ghz: float = 3.6
    storage_total_gb: int = 256

    # ── Live CPU State ──
    cpu_usage_percent: float = 8.0      # baseline idle usage
    cpu_per_core: list = field(
        default_factory=lambda: [
            4.2, 6.8, 5.1, 9.3, 7.7, 3.9, 8.4, 6.1
        ]
    )                                   # 8 cores, baseline idle
    active_threads: int = 12            # baseline system threads

    # ── Live Memory State ──
    used_ram_mb: int = 1200             # baseline OS footprint
    used_gpu_vram_mb: int = 0
    tracked_files: list = field(default_factory=list)

    # ── Live Process State ──
    process_table: list = field(default_factory=list)
    next_pid: int = 1001

    # ── Live Storage State ──
    storage_used_gb: float = 42.3

    # ── Scheduler State ──
    scheduler_queue: list = field(default_factory=list)
    scheduler_algorithm: str = "round_robin"
    context_switches_per_sec: float = 0.0

    # ── Session Metadata ──
    uptime_seconds: float = 0.0
    last_command_latency_ms: float = 0.0
    command_count: int = 0
    daemon_start_time: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ResourceState:
    """
    Thread-safe wrapper around KernelResourceState.
    Singleton — use get_instance() to access the global state.
    """

    _instance: Optional["ResourceState"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._state = KernelResourceState()
        self._lock = threading.Lock()
        self._state_file: Path = Path(
            os.getenv("OSSARTH_STATE_FILE", "ossarth_state.json")
        )
        self._uptime_start: float = time.monotonic()

    # ─────────────────────────────────────────────────────
    # Singleton accessor
    # ─────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "ResourceState":
        """Return the global singleton ResourceState."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ─────────────────────────────────────────────────────
    # Thread-safe attribute access
    # ─────────────────────────────────────────────────────

    def get(self, attr: str) -> Any:
        with self._lock:
            return getattr(self._state, attr)

    def set(self, attr: str, value: Any) -> None:
        with self._lock:
            setattr(self._state, attr, value)

    def mutate(self, fn) -> None:
        """Apply a mutation function under the lock. fn receives the state dataclass."""
        with self._lock:
            fn(self._state)

    # ─────────────────────────────────────────────────────
    # Process table management
    # ─────────────────────────────────────────────────────

    def add_process(self, entry: dict) -> int:
        """Add a process to the table. Returns the assigned PID."""
        with self._lock:
            pid = self._state.next_pid
            self._state.next_pid += 1
            entry["pid"] = pid
            if "started" not in entry:
                entry["started"] = datetime.now(timezone.utc).isoformat()
            if "status" not in entry:
                entry["status"] = "running"
            self._state.process_table.append(entry)
            return pid

    def remove_process(self, pid: int) -> bool:
        """Remove a process from the table by PID. Returns True if found."""
        with self._lock:
            original = len(self._state.process_table)
            self._state.process_table = [
                p for p in self._state.process_table if p.get("pid") != pid
            ]
            return len(self._state.process_table) < original

    def get_process(self, pid: int) -> Optional[dict]:
        """Return the process entry for a given PID, or None."""
        with self._lock:
            for p in self._state.process_table:
                if p.get("pid") == pid:
                    return dict(p)
        return None

    # ─────────────────────────────────────────────────────
    # File tracking
    # ─────────────────────────────────────────────────────

    def track_file(self, path: str, size_bytes: int) -> None:
        with self._lock:
            # Remove old entry for same path if exists
            self._state.tracked_files = [
                f for f in self._state.tracked_files if f.get("path") != path
            ]
            self._state.tracked_files.append({
                "path": path,
                "size_bytes": size_bytes,
                "tracked_at": datetime.now(timezone.utc).isoformat(),
            })

    def untrack_file(self, path: str) -> None:
        with self._lock:
            self._state.tracked_files = [
                f for f in self._state.tracked_files if f.get("path") != path
            ]

    # ─────────────────────────────────────────────────────
    # Bounded mutations (clamp to realistic ranges)
    # ─────────────────────────────────────────────────────

    def bump_cpu(self, delta: float) -> None:
        """Add delta% to CPU usage, clamped to [0, 95]."""
        with self._lock:
            self._state.cpu_usage_percent = max(
                0.0, min(95.0, self._state.cpu_usage_percent + delta)
            )

    def bump_ram(self, delta_mb: int) -> None:
        """Add delta MB to used RAM, clamped to [0, total_ram_mb]."""
        with self._lock:
            self._state.used_ram_mb = max(
                0,
                min(self._state.total_ram_mb, self._state.used_ram_mb + delta_mb),
            )

    def bump_threads(self, delta: int) -> None:
        """Add delta to active_threads, clamped to [0, max_scheduler_threads]."""
        with self._lock:
            self._state.active_threads = max(
                0,
                min(
                    self._state.max_scheduler_threads,
                    self._state.active_threads + delta,
                ),
            )

    # ─────────────────────────────────────────────────────
    # Serialisation
    # ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialise the full state to a JSON-safe dict for the SSE stream."""
        with self._lock:
            s = self._state
            return {
                # Hardware caps
                "total_ram_mb": s.total_ram_mb,
                "total_gpu_vram_mb": s.total_gpu_vram_mb,
                "total_cpu_cores": s.total_cpu_cores,
                "max_scheduler_threads": s.max_scheduler_threads,
                "cpu_clock_ghz": s.cpu_clock_ghz,
                "storage_total_gb": s.storage_total_gb,
                # Live CPU
                "cpu_usage_percent": round(s.cpu_usage_percent, 1),
                "cpu_per_core": [round(c, 1) for c in s.cpu_per_core],
                "active_threads": s.active_threads,
                # Live memory
                "used_ram_mb": s.used_ram_mb,
                "used_gpu_vram_mb": s.used_gpu_vram_mb,
                "tracked_files": s.tracked_files,
                # Live process
                "process_table": list(s.process_table),
                "next_pid": s.next_pid,
                # Storage
                "storage_used_gb": round(s.storage_used_gb, 1),
                # Scheduler
                "scheduler_queue": list(s.scheduler_queue),
                "scheduler_algorithm": s.scheduler_algorithm,
                "context_switches_per_sec": round(s.context_switches_per_sec, 0),
                # Session metadata
                "uptime_seconds": round(time.monotonic() - self._uptime_start, 1),
                "last_command_latency_ms": round(s.last_command_latency_ms, 1),
                "command_count": s.command_count,
                "daemon_start_time": s.daemon_start_time,
            }

    def flush_to_file(self) -> None:
        """
        Write current state to the IPC file for the dashboard process.
        Called after every mutation and every scheduler tick.
        """
        try:
            data = self.to_dict()
            # Write atomically: write to temp file then rename
            tmp = self._state_file.with_suffix(".json.tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"))
            tmp.replace(self._state_file)
        except Exception:
            pass  # Dashboard IPC is best-effort — never crash the daemon

    def reset_to_baseline(self) -> None:
        """Reset all live values to startup defaults. Used between demo runs."""
        with self._lock:
            self._state.cpu_usage_percent = 8.0
            self._state.cpu_per_core = [4.2, 6.8, 5.1, 9.3, 7.7, 3.9, 8.4, 6.1]
            self._state.active_threads = 12
            self._state.used_ram_mb = 1200
            self._state.used_gpu_vram_mb = 0
            self._state.tracked_files = []
            self._state.process_table = []
            self._state.scheduler_queue = []
            self._state.context_switches_per_sec = 0.0
            self._state.last_command_latency_ms = 0.0
            self._state.command_count = 0


# Module-level singleton accessor (convenience)
def get_resource_state() -> ResourceState:
    return ResourceState.get_instance()
