"""
OSSARTH — mcp_tools/tool_registry.py

Central registry mapping tool name strings to callable functions.
Used by:
  - agent_runner.py — dispatches execution graph steps
  - orchestrator_agent.py — injects tool catalog into the planning prompt
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from mas_core.schemas import ToolResult


@dataclass
class ToolDefinition:
    """Metadata + callable for one MCP tool."""
    fn: Callable
    description: str
    args_schema: dict = field(default_factory=dict)
    # args_schema format: { "arg_name": {"type": str, "description": str, "required": bool} }


class ToolRegistry:
    """
    Maps tool name strings → ToolDefinition.
    Thread-safe for reads (dict is read after initialization, never mutated at runtime).
    """

    def __init__(self) -> None:
        self._registry: dict[str, ToolDefinition] = {}

    # ─────────────────────────────────────────────────────
    # Registration
    # ─────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        fn: Callable,
        description: str,
        args_schema: Optional[dict] = None,
    ) -> None:
        """Register a tool with the given name."""
        self._registry[name] = ToolDefinition(
            fn=fn,
            description=description,
            args_schema=args_schema or {},
        )

    def initialize(self) -> None:
        """
        Import all MCP tool modules and register their functions.
        Called once during daemon startup.
        """
        # ── Filesystem tools ──
        from mcp_tools import filesystem_mcp
        self.register(
            "read_file", filesystem_mcp.read_file,
            "Read the full text content of a file at the given path.",
            {"path": {"type": "string", "description": "Absolute or relative path to the file", "required": True}},
        )
        self.register(
            "write_file", filesystem_mcp.write_file,
            "Write content to a file, creating parent directories if needed.",
            {
                "path": {"type": "string", "description": "Path to write to", "required": True},
                "content": {"type": "string", "description": "Text content to write", "required": True},
            },
        )
        self.register(
            "append_file", filesystem_mcp.append_file,
            "Append content to a file, creating it if it does not exist.",
            {
                "path": {"type": "string", "description": "Path to append to", "required": True},
                "content": {"type": "string", "description": "Content to append", "required": True},
            },
        )
        self.register(
            "delete_file", filesystem_mcp.delete_file,
            "Delete a file at the given path.",
            {"path": {"type": "string", "description": "Path of the file to delete", "required": True}},
        )
        self.register(
            "search_directory", filesystem_mcp.search_directory,
            "Recursively search a directory for files matching a name or content query.",
            {
                "path": {"type": "string", "description": "Directory to search", "required": True},
                "query": {"type": "string", "description": "Search term (matched against filenames and content)", "required": True},
                "file_extension": {"type": "string", "description": "Filter by extension, e.g. '.py'", "required": False},
            },
        )
        self.register(
            "list_directory", filesystem_mcp.list_directory,
            "List the contents of a directory (one level deep).",
            {"path": {"type": "string", "description": "Directory path to list", "required": True}},
        )
        self.register(
            "get_file_info", filesystem_mcp.get_file_info,
            "Get metadata for a single file: size, created, modified, permissions.",
            {"path": {"type": "string", "description": "Path to the file", "required": True}},
        )

        # ── Process tools ──
        from mcp_tools import process_mcp
        self.register(
            "list_processes", process_mcp.list_processes,
            "Return the current simulated process table.",
            {},
        )
        self.register(
            "start_process", process_mcp.start_process,
            "Run a shell command via subprocess. Returns stdout, stderr, and returncode.",
            {
                "cmd": {"type": "string", "description": "Command to run (will be split safely)", "required": True},
                "name": {"type": "string", "description": "Human-readable label for the process table", "required": False},
                "timeout_seconds": {"type": "integer", "description": "Kill the process after this many seconds", "required": False},
            },
        )
        self.register(
            "kill_process", process_mcp.kill_process,
            "Kill a process by its PID. Sends SIGTERM then SIGKILL if needed.",
            {"pid": {"type": "integer", "description": "PID of the process to kill", "required": True}},
        )
        self.register(
            "get_process_info", process_mcp.get_process_info,
            "Return the process table entry for a given PID.",
            {"pid": {"type": "integer", "description": "PID to look up", "required": True}},
        )

        # ── Network tools ──
        from mcp_tools import network_mcp
        self.register(
            "get_network_interfaces", network_mcp.get_network_interfaces,
            "Return a list of network interfaces with IP, MAC, and status.",
            {},
        )
        self.register(
            "check_port", network_mcp.check_port,
            "Check if a TCP port on a host is reachable.",
            {
                "host": {"type": "string", "description": "Hostname or IP address", "required": True},
                "port": {"type": "integer", "description": "Port number to check", "required": True},
            },
        )
        self.register(
            "get_hostname", network_mcp.get_hostname,
            "Return the current machine's hostname.",
            {},
        )

        # ── System tools ──
        from mcp_tools import system_mcp
        self.register(
            "get_resource_snapshot", system_mcp.get_resource_snapshot,
            "Return a full snapshot of current simulated system resources (CPU, RAM, threads, etc.).",
            {},
        )
        self.register(
            "get_uptime", system_mcp.get_uptime,
            "Return the daemon uptime in seconds.",
            {},
        )
        self.register(
            "get_command_history", system_mcp.get_command_history,
            "Return the last N commands processed by the daemon.",
            {"n": {"type": "integer", "description": "Number of history entries to return (default 10)", "required": False}},
        )

    # ─────────────────────────────────────────────────────
    # Lookup
    # ─────────────────────────────────────────────────────

    def has_tool(self, name: str) -> bool:
        return name in self._registry

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._registry.get(name)

    def get_callable(self, name: str) -> Optional[Callable]:
        defn = self._registry.get(name)
        return defn.fn if defn else None

    def call_tool(self, tool_name: str, args: dict, step: int = 0) -> ToolResult:
        """Look up a tool and call it. Returns ToolResult(success=False) if not found."""
        defn = self._registry.get(tool_name)
        if defn is None:
            return ToolResult(
                step=step,
                tool=tool_name,
                success=False,
                output=None,
                error=f"Tool '{tool_name}' not found in registry.",
                duration_ms=0.0,
            )
        try:
            result = defn.fn(**args)
            # If the tool function returns a ToolResult, use it directly
            if isinstance(result, ToolResult):
                result.step = step
                return result
            # Otherwise wrap the raw output
            return ToolResult(step=step, tool=tool_name, success=True, output=result)
        except Exception as e:
            return ToolResult(
                step=step,
                tool=tool_name,
                success=False,
                error=f"{type(e).__name__}: {e}",
                duration_ms=0.0,
            )

    # ─────────────────────────────────────────────────────
    # Prompt injection
    # ─────────────────────────────────────────────────────

    def get_tool_catalog_string(self) -> str:
        """
        Format the entire registry as a readable string for injection
        into the Orchestrator's system prompt.
        Tools are sorted alphabetically for consistent LLM output.
        """
        lines = []
        for name in sorted(self._registry.keys()):
            defn = self._registry[name]
            # Build argument list string
            if defn.args_schema:
                arg_parts = []
                for arg_name, meta in defn.args_schema.items():
                    required = meta.get("required", True)
                    arg_type = meta.get("type", "string")
                    suffix = "" if required else "?"
                    arg_parts.append(f"{arg_name}{suffix}: {arg_type}")
                args_str = ", ".join(arg_parts)
            else:
                args_str = ""
            lines.append(f"  {name}({args_str})")
            lines.append(f"    → {defn.description}")
            # Show arg descriptions
            for arg_name, meta in (defn.args_schema or {}).items():
                desc = meta.get("description", "")
                required = "(required)" if meta.get("required", True) else "(optional)"
                lines.append(f"      {arg_name}: {desc} {required}")
            lines.append("")
        return "\n".join(lines)

    def list_tool_names(self) -> list[str]:
        """Return sorted list of all registered tool names."""
        return sorted(self._registry.keys())


# Module-level singleton
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
