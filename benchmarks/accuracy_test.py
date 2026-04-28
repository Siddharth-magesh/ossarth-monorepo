"""
OSSARTH — benchmarks/accuracy_test.py

B2: Accuracy Test
Measures correctness of intent classification and execution graph generation
against ground-truth expected values from test_commands.json.

Scoring per command (max 3 points):
  1 — task_type matches expected_task_type
  1 — set of tools used matches expected_tools
  1 — tools in correct order matches expected_tool_order

Output: benchmarks/results/accuracy_results.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from mas_core.intent_agent import IntentAgent
from mas_core.orchestrator_agent import OrchestratorAgent
from mcp_tools.tool_registry import ToolRegistry


def load_test_commands() -> list:
    with open(ROOT / "benchmarks" / "test_commands.json", "r") as f:
        return json.load(f)


def score_command(cmd: dict, intent, graph) -> tuple[int, dict]:
    score = 0
    breakdown = {}

    # Dimension 1: task type
    task_correct = (intent.task_type == cmd["expected_task_type"])
    score += int(task_correct)
    breakdown["task_type"] = {
        "expected": cmd["expected_task_type"],
        "got":      intent.task_type,
        "correct":  task_correct,
    }

    # Dimension 2: tool set
    graph_tools = [step.tool for step in graph.steps]
    set_correct = (set(graph_tools) == set(cmd["expected_tools"]))
    score += int(set_correct)
    breakdown["tool_set"] = {
        "expected": cmd["expected_tools"],
        "got":      graph_tools,
        "correct":  set_correct,
    }

    # Dimension 3: tool order
    order_correct = (graph_tools == cmd["expected_tool_order"])
    score += int(order_correct)
    breakdown["tool_order"] = {
        "expected": cmd["expected_tool_order"],
        "got":      graph_tools,
        "correct":  order_correct,
    }

    return score, breakdown


def print_summary(result: dict) -> None:
    print("\n" + "═" * 60)
    print("  B2 — ACCURACY TEST SUMMARY")
    print("═" * 60)
    print(f"  Overall: {result['total_score']}/{result['max_score']} ({result['accuracy_percent']:.1f}%)\n")

    print(f"  {'Tier':<20} {'Score':>6} {'Max':>6} {'%':>8}")
    print("  " + "─" * 44)
    for tier, data in result["by_tier"].items():
        print(f"  {tier:<20} {data['score']:>6} {data['max']:>6} {data['percent']:>7.1f}%")

    print("\n  Per-command breakdown:")
    for cmd in result["by_command"]:
        ok = "✓" if cmd["score"] == 3 else ("~" if cmd["score"] > 0 else "✗")
        print(f"    [{ok}] cmd {cmd['command_id']:02d}  {cmd['score']}/3  — "
              f"task:{int(cmd['breakdown']['task_type']['correct'])} "
              f"set:{int(cmd['breakdown']['tool_set']['correct'])} "
              f"order:{int(cmd['breakdown']['tool_order']['correct'])}")
        if not cmd["breakdown"]["tool_set"]["correct"]:
            print(f"         expected {cmd['breakdown']['tool_set']['expected']}")
            print(f"         got      {cmd['breakdown']['tool_set']['got']}")
    print("═" * 60 + "\n")


def run_accuracy_benchmark() -> None:
    print("\nOSSARTH — B2 Accuracy Benchmark\n")

    registry = ToolRegistry()
    registry.initialize()

    intent_agent = IntentAgent(verbose=False)
    orchestrator = OrchestratorAgent(tool_registry=registry, verbose=False)

    commands = load_test_commands()
    by_command = []
    by_tier: dict[str, dict] = {}
    total_score = 0

    for cmd in commands:
        print(f"  Testing cmd {cmd['id']:02d} [{cmd['tier']}]: {cmd['input'][:60]}...", end=" ", flush=True)

        try:
            intent = intent_agent.classify(cmd["input"])
            graph  = orchestrator.plan(intent)
            score, breakdown = score_command(cmd, intent, graph)
        except Exception as e:
            print(f"ERROR: {e}")
            score, breakdown = 0, {
                "task_type":  {"expected": cmd["expected_task_type"], "got": "error", "correct": False},
                "tool_set":   {"expected": cmd["expected_tools"],     "got": [],      "correct": False},
                "tool_order": {"expected": cmd["expected_tool_order"],"got": [],      "correct": False},
                "error": str(e),
            }

        total_score += score
        tier = cmd["tier"]
        if tier not in by_tier:
            by_tier[tier] = {"score": 0, "max": 0}
        by_tier[tier]["score"] += score
        by_tier[tier]["max"]   += 3

        by_command.append({
            "command_id": cmd["id"],
            "tier":       tier,
            "input":      cmd["input"],
            "score":      score,
            "breakdown":  breakdown,
        })
        print(f"{score}/3")
        time.sleep(3)  # rate limit breathing room

    max_score = len(commands) * 3
    by_tier_final = {
        t: {**d, "percent": round(d["score"] / d["max"] * 100, 1) if d["max"] > 0 else 0.0}
        for t, d in by_tier.items()
    }

    result = {
        "total_score":      total_score,
        "max_score":        max_score,
        "accuracy_percent": round(total_score / max_score * 100, 1) if max_score > 0 else 0.0,
        "by_tier":          by_tier_final,
        "by_command":       by_command,
    }

    out_path = ROOT / "benchmarks" / "results" / "accuracy_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n  Results saved to: {out_path}")
    print_summary(result)


if __name__ == "__main__":
    run_accuracy_benchmark()
