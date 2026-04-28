"""
OSSARTH — mas_core/schemas.py

Pydantic v2 schemas for all data crossing layer boundaries.
Every data structure passed between agents and tools is defined here.
No raw dicts between major components — always a typed schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, field_validator, model_validator


# ─────────────────────────────────────────────────────────
# Intent Layer
# ─────────────────────────────────────────────────────────

class EntityItem(BaseModel):
    """A single entity extracted from the user's natural language input."""
    type: Literal[
        "file", "directory", "command", "language",
        "query", "process", "port", "action", "content", "unknown"
    ]
    value: str


class IntentSchema(BaseModel):
    """
    Structured representation of what the user wants to do.
    Produced by the Intent Agent from raw natural language input.
    """
    task_type: Literal[
        "query_system",
        "file_operation",
        "create_and_execute",
        "search_and_summarize",
        "process_management",
        "unknown",
    ]
    priority: Literal["low", "normal", "high"] = "normal"
    entities: list[EntityItem] = []
    requires_clarification: bool = False
    clarification_question: Optional[str] = None
    raw_input: str

    model_config = {"extra": "ignore"}


# ─────────────────────────────────────────────────────────
# Execution Layer
# ─────────────────────────────────────────────────────────

class ExecutionStep(BaseModel):
    """
    A single step in the execution graph produced by the Orchestrator.
    Specifies exactly one tool call.
    """
    step: int
    tool: str
    args: dict[str, Any]
    description: str = ""
    expected_output: str = ""

    @field_validator("step")
    @classmethod
    def step_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"Step number must be >= 1, got {v}")
        return v

    model_config = {"extra": "ignore"}


class ExecutionGraph(BaseModel):
    """
    Ordered list of tool calls to execute.
    Produced by the Orchestrator Agent from a classified intent.
    """
    steps: list[ExecutionStep]

    @field_validator("steps")
    @classmethod
    def steps_must_be_sequential(cls, v: list[ExecutionStep]) -> list[ExecutionStep]:
        for i, step in enumerate(v):
            if step.step != i + 1:
                raise ValueError(
                    f"Steps must be sequential starting at 1. "
                    f"Expected step {i + 1}, got step {step.step}."
                )
        return v

    @model_validator(mode="after")
    def steps_must_not_be_empty(self) -> "ExecutionGraph":
        if not self.steps:
            raise ValueError("ExecutionGraph must have at least one step.")
        return self


# ─────────────────────────────────────────────────────────
# Tool Result Layer
# ─────────────────────────────────────────────────────────

class ToolResult(BaseModel):
    """
    Result of executing one tool step.
    Always returned by @mcp_tool — never raises exceptions.
    """
    step: int
    tool: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0

    model_config = {"extra": "ignore"}


# ─────────────────────────────────────────────────────────
# Command Log Layer
# ─────────────────────────────────────────────────────────

class CommandLogEntry(BaseModel):
    """
    Full record of one user command processed by the daemon.
    Stored in context_manager and streamed to the dashboard.
    """
    timestamp: datetime
    raw_input: str
    intent: IntentSchema
    graph: ExecutionGraph
    results: list[ToolResult]
    total_duration_ms: float
    success: bool  # True if ALL steps succeeded
