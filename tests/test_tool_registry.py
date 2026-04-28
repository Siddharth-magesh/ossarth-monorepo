"""
OSSARTH — tests/test_tool_registry.py

Unit tests for the ToolRegistry — registration, lookup, catalog string,
and call_tool dispatch.
"""

from __future__ import annotations

import sys
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("OSSARTH_STATE_FILE", str(Path(tempfile.gettempdir()) / "ossarth_test_state.json"))
os.environ.setdefault("OSSARTH_WORKSPACE", str(Path(tempfile.gettempdir()) / "ossarth_test"))

from mcp_tools.tool_registry import ToolRegistry
from mas_core.schemas import ToolResult


class TestToolRegistryRegistration:

    def test_initialize_registers_all_tools(self):
        registry = ToolRegistry()
        registry.initialize()
        tool_names = registry.list_tool_names()

        expected = [
            "read_file", "write_file", "append_file", "delete_file",
            "search_directory", "list_directory", "get_file_info",
            "list_processes", "start_process", "kill_process", "get_process_info",
            "get_network_interfaces", "check_port", "get_hostname",
            "get_resource_snapshot", "get_uptime", "get_command_history",
        ]
        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"

    def test_has_tool_returns_true_for_registered(self):
        registry = ToolRegistry()
        registry.register("test_tool", lambda: None, "A test tool", {})
        assert registry.has_tool("test_tool") is True

    def test_has_tool_returns_false_for_unknown(self):
        registry = ToolRegistry()
        assert registry.has_tool("nonexistent_tool") is False

    def test_register_and_retrieve(self):
        registry = ToolRegistry()
        fn = MagicMock(return_value="done")
        registry.register("my_tool", fn, "Does something", {"x": {"type": "string", "required": True}})
        defn = registry.get("my_tool")
        assert defn is not None
        assert defn.description == "Does something"
        assert defn.fn is fn


class TestToolRegistryCatalog:

    def test_catalog_string_contains_tool_names(self):
        registry = ToolRegistry()
        registry.initialize()
        catalog = registry.get_tool_catalog_string()
        assert "read_file" in catalog
        assert "write_file" in catalog
        assert "list_processes" in catalog

    def test_catalog_string_is_sorted(self):
        registry = ToolRegistry()
        registry.initialize()
        catalog = registry.get_tool_catalog_string()
        # The first tool name alphabetically should appear before later ones
        append_pos = catalog.find("append_file")
        write_pos   = catalog.find("write_file")
        assert append_pos < write_pos


class TestCallTool:

    def test_call_registered_tool(self):
        registry = ToolRegistry()
        mock_fn = MagicMock(return_value="result_value")
        registry.register("echo_tool", mock_fn, "Echo", {})

        result = registry.call_tool("echo_tool", {}, step=1)
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.step == 1

    def test_call_unregistered_tool_returns_failure(self):
        registry = ToolRegistry()
        result = registry.call_tool("ghost_tool", {}, step=3)
        assert result.success is False
        assert result.step == 3
        assert "not found" in result.error.lower()

    def test_call_tool_that_raises_returns_failure(self):
        registry = ToolRegistry()
        def boom(**kwargs):
            raise ValueError("boom!")
        registry.register("boom_tool", boom, "Explodes", {})

        result = registry.call_tool("boom_tool", {}, step=2)
        assert result.success is False
        assert "boom" in result.error

    def test_call_tool_passes_step_to_result(self):
        registry = ToolRegistry()
        registry.register("step_tool", lambda: "ok", "Step test", {})
        result = registry.call_tool("step_tool", {}, step=7)
        assert result.step == 7
