"""
OSSARTH — tests/test_intent_agent.py

Unit tests for the Intent Agent.
LLM calls are mocked — tests verify parsing logic, schema validation,
error correction behaviour, and edge case handling.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from mas_core.intent_agent import IntentAgent
from mas_core.schemas import IntentSchema


# ── Helpers ──────────────────────────────────────────────────────────────────

GOOD_INTENT_JSON = json.dumps({
    "task_type": "query_system",
    "priority": "normal",
    "entities": [{"type": "process", "value": "all"}],
    "requires_clarification": False,
    "clarification_question": None,
    "raw_input": "list all running processes",
})

BAD_JSON = "This is not JSON at all"

FIXED_JSON = json.dumps({
    "task_type": "query_system",
    "priority": "normal",
    "entities": [],
    "requires_clarification": False,
    "clarification_question": None,
    "raw_input": "list all running processes",
})


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestIntentAgentParsing:

    def test_classify_returns_intent_schema(self):
        with patch("mas_core.llm_client.complete", return_value=GOOD_INTENT_JSON):
            agent = IntentAgent(verbose=False)
            result = agent.classify("list all running processes")
        assert isinstance(result, IntentSchema)
        assert result.task_type == "query_system"
        assert result.raw_input == "list all running processes"

    def test_classify_empty_input_returns_unknown(self):
        agent = IntentAgent(verbose=False)
        result = agent.classify("")
        assert result.task_type == "unknown"
        assert result.requires_clarification is True
        assert result.clarification_question is not None

    def test_classify_whitespace_only_returns_unknown(self):
        agent = IntentAgent(verbose=False)
        result = agent.classify("   \t  ")
        assert result.task_type == "unknown"

    def test_classify_strips_markdown_fences(self):
        fenced = "```json\n" + GOOD_INTENT_JSON + "\n```"
        with patch("mas_core.llm_client.complete", return_value=fenced):
            agent = IntentAgent(verbose=False)
            result = agent.classify("list all running processes")
        assert result.task_type == "query_system"

    def test_classify_error_correction_retry(self):
        """First call returns bad JSON (triggers parse error retry); second returns valid JSON."""
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return BAD_JSON if call_count == 1 else FIXED_JSON

        with patch("mas_core.llm_client.complete", side_effect=side_effect):
            agent = IntentAgent(verbose=False)
            result = agent.classify("list all running processes")

        # First call fails to parse → error correction → second call succeeds
        assert call_count == 2
        assert result.task_type in ("query_system", "unknown")

    def test_classify_all_retries_fail_returns_unknown(self):
        """Both calls return bad JSON — should gracefully return unknown."""
        with patch("mas_core.llm_client.complete", return_value=BAD_JSON):
            agent = IntentAgent(verbose=False)
            result = agent.classify("some valid command")
        assert result.task_type == "unknown"
        assert result.requires_clarification is True

    def test_classify_llm_exception_returns_unknown(self):
        """LLM call raises RuntimeError — should return unknown, never crash."""
        with patch("mas_core.llm_client.complete", side_effect=RuntimeError("LLM down")):
            agent = IntentAgent(verbose=False)
            result = agent.classify("list processes")
        assert result.task_type == "unknown"

    def test_classify_all_task_types(self):
        """Verify all 6 task_type literals are accepted by the schema."""
        valid_types = [
            "query_system", "file_operation", "create_and_execute",
            "search_and_summarize", "process_management", "unknown"
        ]
        for task_type in valid_types:
            payload = json.dumps({
                "task_type": task_type,
                "priority": "normal",
                "entities": [],
                "requires_clarification": task_type == "unknown",
                "clarification_question": "?" if task_type == "unknown" else None,
                "raw_input": "test",
            })
            with patch("mas_core.llm_client.complete", return_value=payload):
                agent = IntentAgent(verbose=False)
                result = agent.classify("test")
            assert result.task_type == task_type

    def test_context_prefix_injected_in_message(self):
        """Verify context prefix is prepended to the user message."""
        captured_messages = []

        def capture(*args, **kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return GOOD_INTENT_JSON

        with patch("mas_core.llm_client.complete", side_effect=capture):
            agent = IntentAgent(verbose=False)
            agent.classify("run it again", context_prefix="[RECENT CONTEXT]\nCommand 1: wrote hello.py")

        user_msg = next(m for m in captured_messages if m["role"] == "user")
        assert "[RECENT CONTEXT]" in user_msg["content"]
        assert "run it again" in user_msg["content"]


class TestIntentSchema:

    def test_schema_rejects_invalid_task_type(self):
        with pytest.raises(Exception):
            IntentSchema(
                task_type="invalid_type",
                raw_input="test",
            )

    def test_schema_extra_fields_ignored(self):
        """Extra fields in LLM response should not crash the schema."""
        result = IntentSchema(
            task_type="query_system",
            raw_input="test",
            some_extra_field="ignored",  # type: ignore
        )
        assert result.task_type == "query_system"

    def test_schema_defaults(self):
        result = IntentSchema(task_type="query_system", raw_input="test")
        assert result.priority == "normal"
        assert result.entities == []
        assert result.requires_clarification is False
        assert result.clarification_question is None
