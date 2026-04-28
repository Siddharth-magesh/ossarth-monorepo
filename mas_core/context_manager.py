"""
OSSARTH — mas_core/context_manager.py

Rolling history of the last N commands for multi-turn context.
Allows the daemon to understand references like:
  "run that again"
  "delete the file you just created"

Data flow:
  agent_runner → context_manager.add(CommandLogEntry)
  agent_runner → context_manager.get_recent_context() → prepended to intent call
"""

from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from mas_core.schemas import CommandLogEntry

# Max entries to keep in memory
MAX_HISTORY_SIZE = 20

# Reference words that signal the user is referring to a prior output
REFERENCE_WORDS = {
    "it", "that", "the same", "again", "the result",
    "that file", "the file", "that script", "the script",
    "the output", "the process", "that process",
}


class ContextManager:
    """
    Maintains a rolling history of processed commands.
    Provides context injection and fuzzy reference resolution.
    """

    def __init__(self, history_file: Optional[str] = None) -> None:
        self._history: deque[CommandLogEntry] = deque(maxlen=MAX_HISTORY_SIZE)
        self._history_file = Path(
            history_file
            or os.path.expanduser(os.getenv("OSSARTH_HISTORY_FILE", "~/.ossarth_history"))
        )

    # ─────────────────────────────────────────────────────
    # Write
    # ─────────────────────────────────────────────────────

    def add(self, entry: CommandLogEntry) -> None:
        """Append a completed command to the history."""
        self._history.append(entry)
        self._persist(entry)

    def _persist(self, entry: CommandLogEntry) -> None:
        """Append a single entry to the history file (newline-delimited JSON)."""
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._history_file, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
        except Exception:
            pass  # History persistence is best-effort — never crash the daemon

    # ─────────────────────────────────────────────────────
    # Read
    # ─────────────────────────────────────────────────────

    def get_recent_context(self, n: int = 5) -> str:
        """
        Return a compact string of the last N commands for LLM context injection.
        Format is intentionally terse to minimise token usage.
        """
        recent = list(self._history)[-n:]
        if not recent:
            return ""

        lines = ["[RECENT CONTEXT]"]
        for i, entry in enumerate(recent, 1):
            # Summarise: input → tools used → key outputs
            tools_used = [r.tool for r in entry.results if r.tool != "error"]
            outputs = []
            for r in entry.results:
                if r.success and r.output:
                    output_str = str(r.output)[:80]  # truncate long outputs
                    outputs.append(output_str)

            summary = f"Command {i}: \"{entry.raw_input}\""
            if tools_used:
                summary += f" → tools: {', '.join(tools_used)}"
            if outputs:
                summary += f" → output: {outputs[-1]}"  # last output only

            lines.append(summary)

        return "\n".join(lines)

    def has_reference_words(self, user_input: str) -> bool:
        """
        Return True if the input likely refers to a previous command's output.
        Used by agent_runner to decide whether to inject context.
        """
        lower = user_input.lower()
        return any(ref in lower for ref in REFERENCE_WORDS)

    def get_last_output(self, hint: str = "") -> Optional[str]:
        """
        Return the most recent successful tool output (as a string).
        Used to resolve "that file", "the result", etc.
        hint: optional keyword to narrow the search (e.g., "file", "process")
        """
        for entry in reversed(self._history):
            for result in reversed(entry.results):
                if result.success and result.output is not None:
                    output_str = str(result.output)
                    if not hint or hint.lower() in output_str.lower():
                        return output_str
        return None

    def get_last_entry(self) -> Optional[CommandLogEntry]:
        """Return the most recent command log entry."""
        if self._history:
            return self._history[-1]
        return None

    # ─────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────

    def load_history(self) -> None:
        """
        Load command history from disk on startup.
        Silently ignores missing or corrupt files.
        """
        if not self._history_file.exists():
            return

        loaded = 0
        try:
            with open(self._history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entry = CommandLogEntry(**data)
                        self._history.append(entry)
                        loaded += 1
                    except Exception:
                        continue  # Skip corrupt lines
        except Exception:
            pass

        # Keep only last MAX_HISTORY_SIZE entries
        while len(self._history) > MAX_HISTORY_SIZE:
            self._history.popleft()

    def clear(self) -> None:
        """Clear in-memory history (does not delete the file)."""
        self._history.clear()

    def command_count(self) -> int:
        """Return number of commands in the current session history."""
        return len(self._history)
