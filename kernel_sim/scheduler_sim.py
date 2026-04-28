"""
OSSARTH — kernel_sim/scheduler_sim.py

Background daemon thread that simulates a round-robin OS scheduler.
Runs every 1 second, updating:
  - scheduler_queue (round-robin order of active processes)
  - context_switches_per_sec
  - cpu_per_core (load distributed across cores)
  - uptime_seconds
"""
from __future__ import annotations
import random
import threading
import time

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
from kernel_sim.resource_state import ResourceState, get_resource_state


class SchedulerSim(threading.Thread):
    """
    Round-robin scheduler simulation.
    Runs as a daemon thread — exits cleanly when the main process exits.
    """

    def __init__(self, state: ResourceState | None = None, tick_interval: float = 1.0) -> None:
        super().__init__(daemon=True, name="ossarth-scheduler")
        self._state = state or get_resource_state()
        self._tick_interval = tick_interval
        self._stop_event = threading.Event()
        self._tick_count = 0

    def run(self) -> None:
        """Main scheduler loop. Never exits — exceptions are caught and logged."""
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as e:
                # Log but never exit — scheduler must keep running
                pass
            time.sleep(self._tick_interval)

    def stop(self) -> None:
        """Signal the scheduler to stop."""
        self._stop_event.set()

    def _tick(self) -> None:
        """One scheduler tick — update all simulated scheduler state."""
        self._tick_count += 1

        # Read current process table (under lock via state accessor)
        process_table = list(self._state.get("process_table"))

        # Build round-robin queue from process names
        process_names = [
            p.get("name", f"pid-{p.get('pid', '?')}")
            for p in process_table
        ]

        # Add some baseline system processes if table is empty (for demo realism)
        if not process_names:
            process_names = ["idle", "sched/0", "kworker"]

        # Rotate the queue by one position each tick (round-robin simulation)
        if process_names:
            rotated = process_names[self._tick_count % len(process_names):] + \
                      process_names[:self._tick_count % len(process_names)]
        else:
            rotated = []

        # Calculate context switches per second
        # Formula: active_threads × switches_per_thread_per_sec
        active_threads = self._state.get("active_threads")
        base_switches = max(active_threads, 1) * random.uniform(60, 120)
        # Add jitter for realism
        context_switches = base_switches + random.uniform(-base_switches * 0.1, base_switches * 0.1)

        # Distribute CPU load across cores
        if HAS_PSUTIL:
            # Use real system metrics if available
            try:
                total_cpu = psutil.cpu_percent(interval=None)
                cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
                mem = psutil.virtual_memory()
                real_ram_mb = mem.used / (1024 * 1024)
                real_total_ram = mem.total / (1024 * 1024)
            except Exception:
                # Fallback to simulated on error
                total_cpu = self._state.get("cpu_usage_percent")
                num_cores = self._state.get("total_cpu_cores")
                cpu_per_core = self._distribute_cpu_across_cores(total_cpu, num_cores)
                real_ram_mb = None
        else:
            total_cpu = self._state.get("cpu_usage_percent")
            num_cores = self._state.get("total_cpu_cores")
            cpu_per_core = self._distribute_cpu_across_cores(total_cpu, num_cores)
            real_ram_mb = None

        # Apply all updates atomically
        def apply_updates(state):
            state.scheduler_queue = rotated[:8]  # Show max 8 in queue
            state.context_switches_per_sec = round(context_switches, 0)
            state.cpu_per_core = cpu_per_core
            
            if HAS_PSUTIL and real_ram_mb is not None:
                state.cpu_usage_percent = total_cpu
                state.used_ram_mb = int(real_ram_mb)
                state.total_ram_mb = int(real_total_ram)
            else:
                # Add small random CPU drift for realism (idle jitter)
                jitter = random.uniform(-1.5, 1.5)
                state.cpu_usage_percent = max(
                    3.0, min(95.0, state.cpu_usage_percent + jitter)
                )

        self._state.mutate(apply_updates)
        self._state.flush_to_file()

    def _distribute_cpu_across_cores(self, total_cpu: float, num_cores: int) -> list:
        """
        Distribute total CPU% across cores with realistic variance.
        Some cores carry more load than others.
        """
        if total_cpu <= 0:
            return [random.uniform(0.5, 2.0) for _ in range(num_cores)]

        # Give most load to first few cores (common in practice)
        weights = [
            random.uniform(1.5, 2.5),  # core 0 — usually busiest
            random.uniform(1.2, 2.0),  # core 1
            random.uniform(0.8, 1.5),  # core 2
            random.uniform(0.6, 1.2),  # core 3
            random.uniform(0.4, 1.0),  # core 4
            random.uniform(0.3, 0.8),  # core 5
            random.uniform(0.2, 0.6),  # core 6
            random.uniform(0.1, 0.4),  # core 7
        ][:num_cores]

        weight_sum = sum(weights)
        per_core = [
            min(99.0, (w / weight_sum) * total_cpu * num_cores / num_cores)
            for w in weights
        ]
        return [round(c, 1) for c in per_core]
