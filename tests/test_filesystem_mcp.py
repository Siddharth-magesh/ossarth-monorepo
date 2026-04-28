"""
OSSARTH — tests/test_filesystem_mcp.py

Integration tests for filesystem MCP tools.
All tests operate only within a temporary directory — never touch real system paths.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Point workspace at temp so security check passes
os.environ.setdefault("OSSARTH_WORKSPACE", str(Path(tempfile.gettempdir()) / "ossarth_test"))
os.environ.setdefault("OSSARTH_STATE_FILE", str(Path(tempfile.gettempdir()) / "ossarth_test_state.json"))

from mcp_tools.filesystem_mcp import (
    append_file,
    delete_file,
    get_file_info,
    list_directory,
    read_file,
    search_directory,
    write_file,
)
from mas_core.schemas import ToolResult


@pytest.fixture
def tmp_workspace(tmp_path):
    """Provide a clean temp directory for each test."""
    os.environ["OSSARTH_WORKSPACE"] = str(tmp_path)
    yield tmp_path


class TestWriteFile:

    def test_write_creates_file(self, tmp_workspace):
        path = str(tmp_workspace / "hello.txt")
        result = write_file(path=path, content="Hello OSSARTH")
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert Path(path).read_text() == "Hello OSSARTH"

    def test_write_creates_parent_dirs(self, tmp_workspace):
        path = str(tmp_workspace / "deep" / "nested" / "file.txt")
        result = write_file(path=path, content="nested")
        assert result.success is True
        assert Path(path).exists()

    def test_write_blocked_path_fails(self, tmp_workspace):
        import sys
        # Use a platform-appropriate blocked path
        if sys.platform == "win32":
            blocked = r"C:\Windows\ossarth_test.txt"
        else:
            blocked = "/etc/ossarth_test.txt"
        result = write_file(path=blocked, content="blocked")
        assert result.success is False
        assert result.error is not None


class TestReadFile:

    def test_read_existing_file(self, tmp_workspace):
        p = tmp_workspace / "read_me.txt"
        p.write_text("content here")
        result = read_file(path=str(p))
        assert result.success is True
        assert result.output == "content here"

    def test_read_nonexistent_file_fails(self, tmp_workspace):
        result = read_file(path=str(tmp_workspace / "does_not_exist.txt"))
        assert result.success is False
        assert "not found" in result.error.lower()


class TestAppendFile:

    def test_append_to_new_file(self, tmp_workspace):
        path = str(tmp_workspace / "append.txt")
        result = append_file(path=path, content="line1\n")
        assert result.success is True
        assert "line1" in Path(path).read_text()

    def test_append_to_existing_file(self, tmp_workspace):
        path = str(tmp_workspace / "append2.txt")
        Path(path).write_text("initial\n")
        append_file(path=path, content="appended\n")
        content = Path(path).read_text()
        assert "initial" in content
        assert "appended" in content


class TestDeleteFile:

    def test_delete_existing_file(self, tmp_workspace):
        p = tmp_workspace / "delete_me.txt"
        p.write_text("bye")
        result = delete_file(path=str(p))
        assert result.success is True
        assert not p.exists()

    def test_delete_nonexistent_file_fails(self, tmp_workspace):
        result = delete_file(path=str(tmp_workspace / "ghost.txt"))
        assert result.success is False


class TestListDirectory:

    def test_list_returns_entries(self, tmp_workspace):
        (tmp_workspace / "a.txt").write_text("a")
        (tmp_workspace / "b.txt").write_text("b")
        result = list_directory(path=str(tmp_workspace))
        assert result.success is True
        names = [e["name"] for e in result.output]
        assert "a.txt" in names
        assert "b.txt" in names

    def test_list_nonexistent_dir_fails(self, tmp_workspace):
        result = list_directory(path=str(tmp_workspace / "no_such_dir"))
        assert result.success is False


class TestSearchDirectory:

    def test_search_by_filename(self, tmp_workspace):
        (tmp_workspace / "hello_world.py").write_text("print('hi')")
        result = search_directory(path=str(tmp_workspace), query="hello")
        assert result.success is True
        assert len(result.output) >= 1
        assert any("hello_world.py" in r["path"] for r in result.output)

    def test_search_by_content(self, tmp_workspace):
        (tmp_workspace / "script.py").write_text("print('OSSARTH benchmark')")
        result = search_directory(path=str(tmp_workspace), query="OSSARTH benchmark")
        assert result.success is True
        assert any(r["match_type"] == "content" for r in result.output)

    def test_search_with_extension_filter(self, tmp_workspace):
        (tmp_workspace / "code.py").write_text("pass")
        (tmp_workspace / "notes.txt").write_text("pass")
        result = search_directory(path=str(tmp_workspace), query="pass", file_extension=".py")
        assert result.success is True
        assert all(r["path"].endswith(".py") for r in result.output)


class TestGetFileInfo:

    def test_get_info_for_existing_file(self, tmp_workspace):
        p = tmp_workspace / "info_test.txt"
        p.write_text("content")
        result = get_file_info(path=str(p))
        assert result.success is True
        info = result.output
        assert "size_bytes" in info
        assert "modified" in info
        assert info["is_file"] is True

    def test_get_info_for_nonexistent_file_fails(self, tmp_workspace):
        result = get_file_info(path=str(tmp_workspace / "nope.txt"))
        assert result.success is False
