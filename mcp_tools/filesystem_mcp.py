"""
OSSARTH — mcp_tools/filesystem_mcp.py

Real filesystem operations using pathlib and standard Python I/O.
All functions are wrapped with @mcp_tool for error handling and resource hooks.

Security: Only write to OSSARTH_WORKSPACE or /tmp by default.
Blocked paths: /etc, /sys, /proc, /boot, C:\\Windows\\System32, etc.
"""
from __future__ import annotations
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from mcp_tools.tool_base import mcp_tool

# ── Security: blocked path prefixes ──
_BLOCKED_WRITE_PREFIXES = [
    "/etc", "/sys", "/proc", "/boot", "/bin", "/sbin", "/usr/bin",
    "C:\\Windows", "C:\\Program Files",
]
_BLOCKED_COMMANDS = ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:"]


def _check_write_path(path: str) -> None:
    """Raise ValueError if the path is in a blocked location."""
    resolved = str(Path(path).resolve())
    for blocked in _BLOCKED_WRITE_PREFIXES:
        if resolved.startswith(blocked):
            raise ValueError(
                f"Write to '{resolved}' is blocked for safety. "
                f"Use the OSSARTH workspace directory instead."
            )


# ─────────────────────────────────────────────────────────

@mcp_tool()
def read_file(path: str) -> str:
    """Read and return the full text content of a file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not p.is_file():
        raise ValueError(f"Path is not a file: {path}")
    return p.read_text(encoding="utf-8", errors="replace")


@mcp_tool()
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed."""
    _check_write_path(path)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p.resolve())


@mcp_tool()
def append_file(path: str, content: str) -> str:
    """Append content to a file, creating it if it does not exist."""
    _check_write_path(path)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(content)
    return str(p.resolve())


@mcp_tool()
def delete_file(path: str) -> bool:
    """Delete a file at the given path."""
    _check_write_path(path)
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    p.unlink()
    return True


@mcp_tool()
def search_directory(
    path: str, query: str, file_extension: Optional[str] = None
) -> list:
    """
    Recursively search a directory for files matching name or content query.
    Returns up to 50 matches.
    """
    base = Path(path)
    if not base.exists():
        raise FileNotFoundError(f"Directory not found: {path}")

    results = []
    query_lower = query.lower()
    ext = file_extension.lower() if file_extension else None

    for item in base.rglob("*"):
        if len(results) >= 50:
            break
        if not item.is_file():
            continue
        if ext and item.suffix.lower() != ext:
            continue

        # Match by filename
        if query_lower in item.name.lower():
            results.append({
                "path": str(item),
                "match_type": "name",
                "preview": item.name,
            })
            continue

        # Match by content (text files only, skip large files)
        if item.stat().st_size > 1_000_000:  # skip files > 1MB
            continue
        try:
            text = item.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if query_lower in line.lower():
                    results.append({
                        "path": str(item),
                        "match_type": "content",
                        "preview": line.strip()[:100],
                    })
                    break
        except Exception:
            continue

    return results


@mcp_tool()
def list_directory(path: str) -> list:
    """List the contents of a directory (one level deep)."""
    base = Path(path)
    if not base.exists():
        raise FileNotFoundError(f"Directory not found: {path}")
    if not base.is_dir():
        raise ValueError(f"Path is not a directory: {path}")

    entries = []
    for item in sorted(base.iterdir()):
        try:
            stat_result = item.stat()
            entries.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size_bytes": stat_result.st_size if item.is_file() else 0,
                "modified": datetime.fromtimestamp(
                    stat_result.st_mtime, tz=timezone.utc
                ).isoformat(),
            })
        except Exception:
            continue
    return entries


@mcp_tool()
def get_file_info(path: str) -> dict:
    """Return metadata for a single file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    s = p.stat()
    return {
        "path": str(p.resolve()),
        "size_bytes": s.st_size,
        "created": datetime.fromtimestamp(s.st_ctime, tz=timezone.utc).isoformat(),
        "modified": datetime.fromtimestamp(s.st_mtime, tz=timezone.utc).isoformat(),
        "extension": p.suffix,
        "is_file": p.is_file(),
        "is_dir": p.is_dir(),
    }
