"""
OSSARTH — benchmarks/latency_test.py

B1: Latency Test
Measures wall-clock time from input to execution completion for each
of the 10 canonical test commands across 4 phases:
  1. Intent classification
  2. Orchestration (execution graph generation)
  3. Tool execution
  4. Total (all above)

Output: benchmarks/results/latency_results.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from mas_core.intent_agent import IntentAgent
from mas_core.orchestrator_agent import OrchestratorAgent
from mas_core.agent_runner import dispatch_execution_graph
from mcp_tools.tool_registry import ToolRegistry


def load_test_commands() -> list:
    with open(ROOT / "benchmarks" / "test_commands.json", "r") as f:
        return json.load(f)


def print_summary(results: list) -> None:
    by_tier: dict[str, list] = {}
    for r in results:
        tier = r["tier"]
        by_tier.setdefault(tier, []).append(r)

    print("\n" + "═" * 60)
    print("  B1 — LATENCY TEST SUMMARY")
    print("═" * 60)
    print(f"  {'Tier':<20} {'Avg Total':>12} {'Intent':>10} {'Orch':>10} {'Exec':>10}")
    print("  " + "─" * 56)

    for tier, items in by_tier.items():
        avg_total = sum(i["total_ms"] for i in items) / len(items)
        avg_intent = sum(i["intent_ms"] for i in items) / len(items)
        avg_orch   = sum(i["orchestration_ms"] for i in items) / len(items)
        avg_exec   = sum(i["execution_ms"] for i in items) / len(items)
        print(f"  {tier:<20} {avg_total:>11.0f}ms {avg_intent:>9.0f}ms {avg_orch:>9.0f}ms {avg_exec:>9.0f}ms")

    all_total = [r["total_ms"] for r in results]
    print(f"\n  Overall avg: {sum(all_total)/len(all_total):.0f}ms")
    print(f"  Min: {min(all_total):.0f}ms   Max: {max(all_total):.0f}ms")
    print("═" * 60 + "\n")


def run_latency_benchmark() -> None:
    print("\nOSSARTH — B1 Latency Benchmark")
    print("Warming up registries...\n")

    registry = ToolRegistry()
    registry.initialize()

    intent_agent = IntentAgent(verbose=False)
    orchestrator = OrchestratorAgent(tool_registry=registry, verbose=False)

    commands = load_test_commands()
    results = []

    for cmd in commands:
        print(f"  Command {cmd['id']:02d} [{cmd['tier']:>14}]: {cmd['input'][:50]}...")
        for run_type in ("cold", "warm"):
            record = {
                "command_id":   cmd["id"],
                "tier":         cmd["tier"],
                "input":        cmd["input"],
                "run_type":     run_type,
            }

            # Phase 1: Intent classification
            t0 = time.perf_counter()
            intent = intent_agent.classify(cmd["input"])
            t1 = time.perf_counter()
            record["intent_ms"] = round((t1 - t0) * 1000, 2)
            record["task_type"] = intent.task_type

            # Phase 2: Orchestration
            t2 = time.perf_counter()
            graph = orchestrator.plan(intent)
            t3 = time.perf_counter()
            record["orchestration_ms"] = round((t3 - t2) * 1000, 2)
            record["tool_count"] = len(graph.steps)

            # Phase 3: Tool execution
            t4 = time.perf_counter()
            tool_results = dispatch_execution_graph(graph, registry, verbose=False)
            t5 = time.perf_counter()
            record["execution_ms"] = round((t5 - t4) * 1000, 2)

            # Total
            record["total_ms"] = round((t5 - t0) * 1000, 2)
            record["bash_equivalent_ms"] = (cmd.get("estimated_bash_seconds") or 0) * 1000
            record["all_tools_succeeded"] = all(r.success for r in tool_results)
            record["tools_used"] = [r.tool for r in tool_results]

            results.append(record)
            print(f"    [{run_type:4}] {record['total_ms']:>7.0f}ms  "
                  f"intent:{record['intent_ms']:.0f}ms  "
                  f"orch:{record['orchestration_ms']:.0f}ms  "
                  f"exec:{record['execution_ms']:.0f}ms  "
                  f"{'OK' if record['all_tools_succeeded'] else 'FAIL'}")

            wait = 5 if run_type == "cold" else 10
            time.sleep(wait)

    # Save results
    out_path = ROOT / "benchmarks" / "results" / "latency_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n  Results saved to: {out_path}")
    print_summary(results)


if __name__ == "__main__":
    run_latency_benchmark()
