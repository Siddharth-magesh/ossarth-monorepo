"""
OSSARTH — benchmarks/consistency_test.py

B4: Consistency Test
Checks whether the same input produces the same execution graph on
repeated runs. Each of the 10 test commands is run 3 times with 15s gaps.

Scoring per command:
  fully_consistent   — all 3 tool sequences identical
  partially_consistent — 2 of 3 match
  inconsistent       — all 3 differ

Output: benchmarks/results/consistency_results.json
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


def sequences_equal(a: list, b: list) -> bool:
    return a == b


def run_consistency_benchmark() -> None:
    print("\nOSSARTH — B4 Consistency Benchmark\n")
    print("  Each command runs 3 times. 15s gap between runs.\n")

    registry = ToolRegistry()
    registry.initialize()

    intent_agent = IntentAgent(verbose=False)
    orchestrator  = OrchestratorAgent(tool_registry=registry, verbose=False)

    commands = load_test_commands()
    by_command = []
    consistent_count = 0

    for cmd in commands:
        print(f"  Command {cmd['id']:02d} [{cmd['tier']}]: {cmd['input'][:55]}...")
        run_results = []

        for run_num in range(1, 4):
            try:
                intent = intent_agent.classify(cmd["input"])
                graph  = orchestrator.plan(intent)
                tools  = [s.tool for s in graph.steps]
                run_results.append({
                    "run":       run_num,
                    "task_type": intent.task_type,
                    "tools":     tools,
                    "error":     None,
                })
                print(f"    run {run_num}: {tools}")
            except Exception as e:
                run_results.append({"run": run_num, "task_type": "error", "tools": [], "error": str(e)})
                print(f"    run {run_num}: ERROR — {e}")

            if run_num < 3:
                time.sleep(15)

        # Compare tool sequences pairwise
        seqs = [r["tools"] for r in run_results]
        pairs = [
            sequences_equal(seqs[0], seqs[1]),
            sequences_equal(seqs[0], seqs[2]),
            sequences_equal(seqs[1], seqs[2]),
        ]
        match_count = sum(pairs)

        if match_count == 3:
            consistency = "fully_consistent"
            consistent_count += 1
        elif match_count >= 1:
            consistency = "partially_consistent"
        else:
            consistency = "inconsistent"

        task_types = [r["task_type"] for r in run_results]
        task_type_consistent = len(set(task_types)) == 1

        print(f"    → {consistency} | task_type consistent: {task_type_consistent}\n")

        by_command.append({
            "command_id":           cmd["id"],
            "tier":                 cmd["tier"],
            "input":                cmd["input"],
            "tool_sequence_consistency": consistency,
            "task_type_consistent": task_type_consistent,
            "run_1_tools":          run_results[0]["tools"] if len(run_results) > 0 else [],
            "run_2_tools":          run_results[1]["tools"] if len(run_results) > 1 else [],
            "run_3_tools":          run_results[2]["tools"] if len(run_results) > 2 else [],
        })

    overall_rate = consistent_count / len(commands) if commands else 0

    result = {
        "overall_consistency_rate": round(overall_rate, 3),
        "fully_consistent_count":   consistent_count,
        "total_commands":           len(commands),
        "by_command":               by_command,
    }

    out_path = ROOT / "benchmarks" / "results" / "consistency_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n  Results saved to: {out_path}")
    print("\n" + "═" * 50)
    print("  B4 — CONSISTENCY SUMMARY")
    print("═" * 50)
    print(f"  Overall rate: {overall_rate:.1%}")
    print(f"  Fully consistent: {consistent_count}/{len(commands)}")
    print("═" * 50 + "\n")


if __name__ == "__main__":
    run_consistency_benchmark()
