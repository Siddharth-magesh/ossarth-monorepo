"""
OSSARTH — mas_core/orchestrator_agent.py

Second stage of the MAS pipeline.
Takes a classified IntentSchema → returns an ExecutionGraph.

The tool catalog is injected at runtime from tool_registry so the
model can never hallucinate a tool name — it only sees tools that exist.
"""

from __future__ import annotations

import json
import sys
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from mas_core import llm_client
from mas_core.prompts import ERROR_CORRECTION_PROMPT, ORCHESTRATOR_SYSTEM_PROMPT
from mas_core.schemas import ExecutionGraph, ExecutionStep, IntentSchema

# Max tokens for orchestration responses (JSON array of steps — 1000 is ample)
ORCHESTRATOR_MAX_TOKENS = 1000


# ─────────────────────────────────────────────────────────
# Orchestrator Agent class
# ─────────────────────────────────────────────────────────

class OrchestratorAgent:
    """
    Takes a classified intent and produces an ordered execution graph.

    Usage:
        agent = OrchestratorAgent(tool_registry=registry)
        graph = agent.plan(intent)
        for step in graph.steps:
            print(step.tool, step.args)
    """

    def __init__(
        self,
        tool_registry=None,
        verbose: bool = False,
    ) -> None:
        """
        Args:
            tool_registry: The ToolRegistry instance. If provided, tool names
                           in the generated graph are validated against it.
                           Also used to inject the tool catalog into the prompt.
            verbose:       If True, print debug info during planning.
        """
        self.tool_registry = tool_registry
        self.verbose = verbose

    def plan(self, intent: IntentSchema) -> ExecutionGraph:
        """
        Produce an ExecutionGraph from a classified intent.

        Returns:
            ExecutionGraph — always returns, never raises.
            On complete failure returns a single error step.
        """
        # Build the system prompt with the live tool catalog injected
        system_prompt = ORCHESTRATOR_SYSTEM_PROMPT
        if self.tool_registry is not None:
            catalog = self.tool_registry.get_tool_catalog_string()
            system_prompt = system_prompt + f"\n\n## AVAILABLE TOOLS\n\n{catalog}"

        user_message = json.dumps(intent.model_dump(), indent=2)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ]

        response_text = ""
        last_error: Optional[Exception] = None

        # First attempt
        try:
            response_text = llm_client.complete(
                messages=messages,
                max_tokens=ORCHESTRATOR_MAX_TOKENS,
                temperature=0.0,
                verbose=self.verbose,
            )
            graph = self._parse_and_validate(response_text)
            if graph:
                return graph

        except Exception as e:
            last_error = e
            if self.verbose:
                print(f"  [Orchestrator] First attempt failed: {e}")
                print(f"  [Orchestrator] Raw response: {response_text!r}")

        # Error-correction retry
        try:
            correction_messages = messages + [
                {"role": "assistant", "content": response_text},
                {
                    "role": "user",
                    "content": ERROR_CORRECTION_PROMPT.format(
                        bad_output=response_text,
                        parse_error=str(last_error),
                    ),
                },
            ]
            response_text = llm_client.complete(
                messages=correction_messages,
                max_tokens=ORCHESTRATOR_MAX_TOKENS,
                temperature=0.0,
                verbose=self.verbose,
            )
            graph = self._parse_and_validate(response_text)
            if graph:
                return graph

        except Exception as retry_err:
            if self.verbose:
                print(f"  [Orchestrator] Retry also failed: {retry_err}")

        # Final fallback — single error step
        return ExecutionGraph(
            steps=[
                ExecutionStep(
                    step=1,
                    tool="error",
                    args={"message": "Planning failed — could not generate a valid execution graph."},
                    description="Planning error",
                    expected_output="error_message",
                )
            ]
        )

    def _parse_and_validate(self, response_text: str) -> Optional[ExecutionGraph]:
        """
        Parse the LLM response into an ExecutionGraph.
        Returns None (instead of raising) if validation fails.
        """
        # Strip markdown fences if present
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()

        # The response should be a JSON array
        data = json.loads(text)

        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array, got {type(data).__name__}")

        if len(data) == 0:
            raise ValueError("Execution graph cannot be empty")

        # Parse each step
        steps = []
        for i, raw_step in enumerate(data):
            step = ExecutionStep(**raw_step)
            steps.append(step)

        # Validate all tool names against registry (if available)
        if self.tool_registry is not None:
            invalid_tools = []
            for step in steps:
                if step.tool != "error" and not self.tool_registry.has_tool(step.tool):
                    invalid_tools.append(step.tool)

            if invalid_tools:
                raise ValueError(
                    f"Execution graph references unknown tools: {invalid_tools}. "
                    f"Only use tools from AVAILABLE TOOLS."
                )

        # Enforce max steps
        import os
        max_steps = int(os.getenv("OSSARTH_MAX_EXECUTION_STEPS", "10"))
        if len(steps) > max_steps:
            if self.verbose:
                print(f"  [Orchestrator] Truncating graph from {len(steps)} to {max_steps} steps")
            steps = steps[:max_steps]

        # Re-number steps to ensure sequential (model might get confused)
        for i, step in enumerate(steps):
            step.step = i + 1

        return ExecutionGraph(steps=steps)


# ─────────────────────────────────────────────────────────
# Standalone test entrypoint
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    verbose = "--verbose" in sys.argv or os.getenv("OSSARTH_VERBOSE", "false").lower() == "true"

    from mas_core.intent_agent import IntentAgent
    from mas_core.schemas import IntentSchema

    intent_agent = IntentAgent(verbose=verbose)
    orchestrator = OrchestratorAgent(tool_registry=None, verbose=verbose)

    print("OSSARTH Orchestrator Agent — Standalone Test")
    print("(No tool_registry loaded — tool validation skipped)")
    print("Type a command and press Enter. Ctrl+C to quit.\n")

    while True:
        try:
            user_input = input("orchestrate> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue

        print("\nStep 1: Classifying intent...")
        intent = intent_agent.classify(user_input)
        print(f"Intent: {intent.task_type}")
        print(json.dumps(intent.model_dump(), indent=2))

        print("\nStep 2: Planning execution graph...")
        graph = orchestrator.plan(intent)
        print(json.dumps([s.model_dump() for s in graph.steps], indent=2))
        print()
