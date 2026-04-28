"""
OSSARTH — mas_core/intent_agent.py

First stage of the MAS pipeline.
Takes raw natural language input → returns a typed IntentSchema.

Pipeline:
  raw_input → build messages → llm_client.complete() → json.loads()
            → IntentSchema validation → (retry on failure) → return
"""

from __future__ import annotations

import json
import sys
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from mas_core import llm_client
from mas_core.prompts import ERROR_CORRECTION_PROMPT, INTENT_SYSTEM_PROMPT
from mas_core.schemas import IntentSchema

# Max tokens for intent responses (small JSON objects — 256 is generous)
INTENT_MAX_TOKENS = 256


# ─────────────────────────────────────────────────────────
# Intent Agent class
# ─────────────────────────────────────────────────────────

class IntentAgent:
    """
    Classifies raw user input into a structured IntentSchema.

    Usage:
        agent = IntentAgent()
        intent = agent.classify("list all running processes")
        print(intent.task_type)  # "query_system"
    """

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def classify(
        self,
        raw_input: str,
        context_prefix: str = "",
    ) -> IntentSchema:
        """
        Classify the user's input into an IntentSchema.

        Args:
            raw_input:      The raw user input string.
            context_prefix: Optional recent-context block prepended to the
                            user message (injected by agent_runner for
                            multi-turn reference resolution).

        Returns:
            IntentSchema — always returns, never raises.
            On complete failure returns unknown intent.
        """
        # Sanitize input
        raw_input = raw_input.strip()
        if not raw_input:
            return IntentSchema(
                task_type="unknown",
                requires_clarification=True,
                clarification_question="Please describe what you'd like to do.",
                raw_input="",
            )

        # Build user message (with optional context prefix)
        user_content = raw_input
        if context_prefix:
            user_content = f"{context_prefix}\n\n[CURRENT INPUT]\n{raw_input}"

        messages = [
            {"role": "system", "content": INTENT_SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]

        # First attempt
        response_text = ""
        last_error: Exception = ValueError("no response")
        try:
            response_text = llm_client.complete(
                messages=messages,
                max_tokens=INTENT_MAX_TOKENS,
                temperature=0.0,
                verbose=self.verbose,
            )
            return self._parse_response(response_text, raw_input)

        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            if self.verbose:
                print(f"  [IntentAgent] Parse failed on first attempt: {e}")
                print(f"  [IntentAgent] Raw response: {response_text!r}")

        except Exception as e:
            # LLM call itself failed (network, timeout, etc.) — skip retry
            last_error = e
            if self.verbose:
                print(f"  [IntentAgent] LLM call failed: {e}")
            return IntentSchema(
                task_type="unknown",
                requires_clarification=True,
                clarification_question="An error occurred processing your request. Please try again.",
                raw_input=raw_input,
            )

        # Error-correction retry (only reached on parse failures)
        try:
            correction_messages = [
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
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
                max_tokens=INTENT_MAX_TOKENS,
                temperature=0.0,
                verbose=self.verbose,
            )
            return self._parse_response(response_text, raw_input)

        except Exception as retry_err:
            if self.verbose:
                print(f"  [IntentAgent] Retry also failed: {retry_err}")

        # Final fallback
        return IntentSchema(
            task_type="unknown",
            requires_clarification=True,
            clarification_question=(
                "I couldn't understand that request. "
                "Could you rephrase it more specifically?"
            ),
            raw_input=raw_input,
        )

    def _parse_response(self, response_text: str, raw_input: str) -> IntentSchema:
        """
        Parse and validate a JSON response string into an IntentSchema.
        Raises json.JSONDecodeError or ValueError on failure.
        """
        # Strip any accidental markdown fences
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()

        data = json.loads(text)

        # Ensure raw_input is set (model might omit it)
        if "raw_input" not in data or not data["raw_input"]:
            data["raw_input"] = raw_input

        return IntentSchema(**data)


# ─────────────────────────────────────────────────────────
# Standalone test entrypoint
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    verbose = "--verbose" in sys.argv or os.getenv("OSSARTH_VERBOSE", "false").lower() == "true"

    agent = IntentAgent(verbose=verbose)

    print("OSSARTH Intent Agent — Standalone Test")
    print("Type a command and press Enter. Ctrl+C to quit.\n")

    while True:
        try:
            user_input = input("intent> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue

        result = agent.classify(user_input)
        print(json.dumps(result.model_dump(), indent=2))
        print()
