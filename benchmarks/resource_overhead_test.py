"""
OSSARTH — benchmarks/resource_overhead_test.py

B3: Resource Overhead Test
Measures CPU and RAM consumed by the OSSARTH daemon process itself
while idle and under active load.

Requires: psutil (already in requirements.txt)
Output: benchmarks/results/overhead_results.json
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

try:
    import psutil
except ImportError:
    print("ERROR: psutil not installed. Run: pip install psutil")
    sys.exit(1)


def sample_process(proc: psutil.Process, samples: int = 30, interval: float = 1.0) -> list:
    readings = []
    for _ in range(samples):
        try:
            mem = proc.memory_info()
            readings.append({
                "cpu_percent":  proc.cpu_percent(interval=interval),
                "rss_mb":       mem.rss / 1024 ** 2,
                "vms_mb":       mem.vms / 1024 ** 2,
                "num_threads":  proc.num_threads(),
                "timestamp":    time.time(),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break
    return readings


def summarize(samples: list) -> dict:
    if not samples:
        return {}
    cpu = [s["cpu_percent"] for s in samples]
    rss = [s["rss_mb"]      for s in samples]
    return {
        "cpu_percent_avg":  round(statistics.mean(cpu), 2),
        "cpu_percent_peak": round(max(cpu), 2),
        "rss_mb_avg":       round(statistics.mean(rss), 2),
        "rss_mb_peak":      round(max(rss), 2),
        "sample_count":     len(samples),
    }


def run_with_sampling(proc: psutil.Process, n_commands: int = 5) -> list:
    """Run a few MAS commands while sampling in a background thread."""
    active_samples = []
    stop_flag = threading.Event()

    def sampler():
        while not stop_flag.is_set():
            try:
                mem = proc.memory_info()
                active_samples.append({
                    "cpu_percent":  proc.cpu_percent(interval=0.5),
                    "rss_mb":       mem.rss / 1024 ** 2,
                    "vms_mb":       mem.vms / 1024 ** 2,
                    "num_threads":  proc.num_threads(),
                    "timestamp":    time.time(),
                })
            except Exception:
                break

    t = threading.Thread(target=sampler, daemon=True)
    t.start()

    # Run a few commands through the MAS
    try:
        from mas_core.intent_agent import IntentAgent
        from mas_core.orchestrator_agent import OrchestratorAgent
        from mas_core.agent_runner import dispatch_execution_graph
        from mcp_tools.tool_registry import ToolRegistry

        registry = ToolRegistry()
        registry.initialize()
        intent_agent = IntentAgent(verbose=False)
        orchestrator = OrchestratorAgent(tool_registry=registry, verbose=False)

        test_inputs = [
            "list all running processes",
            "show me what files are in the ossarth workspace",
            "what is the hostname of this machine",
        ][:n_commands]

        for inp in test_inputs:
            intent = intent_agent.classify(inp)
            graph  = orchestrator.plan(intent)
            dispatch_execution_graph(graph, registry, verbose=False)
            time.sleep(2)
    except Exception as e:
        print(f"  Warning during active phase: {e}")

    stop_flag.set()
    t.join(timeout=3)
    return active_samples


def run_overhead_benchmark() -> None:
    print("\nOSSARTH — B3 Resource Overhead Benchmark\n")

    proc = psutil.Process(os.getpid())
    # Prime cpu_percent (first call always returns 0)
    proc.cpu_percent(interval=None)

    print("  Phase 1: Sampling idle baseline (30 seconds)...")
    print("  (Do not send any commands during this time)\n")
    time.sleep(5)  # let things settle
    idle_samples = sample_process(proc, samples=30, interval=1.0)

    print("  Phase 2: Running active commands while sampling...")
    active_samples = run_with_sampling(proc, n_commands=3)

    idle_summary   = summarize(idle_samples)
    active_summary = summarize(active_samples)

    delta = {}
    if idle_summary and active_summary:
        delta = {
            "cpu_percent": round(active_summary["cpu_percent_avg"] - idle_summary["cpu_percent_avg"], 2),
            "rss_mb":      round(active_summary["rss_mb_avg"]      - idle_summary["rss_mb_avg"], 2),
        }

    result = {
        "idle":           idle_summary,
        "active":         active_summary,
        "overhead_delta": delta,
    }

    out_path = ROOT / "benchmarks" / "results" / "overhead_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n  Results saved to: {out_path}")
    print("\n" + "═" * 60)
    print("  B3 — RESOURCE OVERHEAD SUMMARY")
    print("═" * 60)
    print(f"  {'Mode':<10} {'CPU avg':>10} {'CPU peak':>10} {'RAM avg':>10} {'RAM peak':>10}")
    print("  " + "─" * 46)
    if idle_summary:
        print(f"  {'Idle':<10} {idle_summary['cpu_percent_avg']:>9.1f}% {idle_summary['cpu_percent_peak']:>9.1f}% "
              f"{idle_summary['rss_mb_avg']:>8.0f}MB {idle_summary['rss_mb_peak']:>8.0f}MB")
    if active_summary:
        print(f"  {'Active':<10} {active_summary['cpu_percent_avg']:>9.1f}% {active_summary['cpu_percent_peak']:>9.1f}% "
              f"{active_summary['rss_mb_avg']:>8.0f}MB {active_summary['rss_mb_peak']:>8.0f}MB")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    run_overhead_benchmark()
