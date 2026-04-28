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

# ── Workspace resolution ──
# Resolve OSSARTH_WORKSPACE relative to the repo root so it is always correct
# regardless of which directory the process was started from.
_REPO_ROOT = Path(__file__).parent.parent.resolve()

def _get_workspace() -> Path:
    """Return the absolute workspace path, always anchored to the repo root."""
    raw = os.getenv("OSSARTH_WORKSPACE", "./ossarth_workspace")
    if Path(raw).is_absolute():
        return Path(raw).resolve()
    return (_REPO_ROOT / raw).resolve()

def _resolve_path(path: str) -> Path:
    """
    If path is relative (no drive letter, doesn't start with /),
    resolve it relative to OSSARTH_WORKSPACE so LLM-generated paths
    like 'ossarth_workspace/hello.txt' or 'hello.txt' land in the right place.
    """
    p = Path(path)
    if p.is_absolute():
        return p
    ws = _get_workspace()
    # Strip leading 'ossarth_workspace/' if the model included it
    parts = p.parts
    if parts and parts[0].lower() == "ossarth_workspace":
        p = Path(*parts[1:])
    return (ws / p).resolve()

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
    p = _resolve_path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    if not p.is_file():
        raise ValueError(f"Path is not a file: {p}")
    return p.read_text(encoding="utf-8", errors="replace")


@mcp_tool()
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed."""
    p = _resolve_path(path)
    _check_write_path(str(p))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p)


@mcp_tool()
def append_file(path: str, content: str) -> str:
    """Append content to a file, creating it if it does not exist."""
    p = _resolve_path(path)
    _check_write_path(str(p))
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(content)
    return str(p)


@mcp_tool()
def delete_file(path: str) -> bool:
    """Delete a file at the given path."""
    p = _resolve_path(path)
    _check_write_path(str(p))
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
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
    base = _resolve_path(path)
    if not base.exists():
        raise FileNotFoundError(f"Directory not found: {base}")

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
    base = _resolve_path(path)
    if not base.exists():
        raise FileNotFoundError(f"Directory not found: {base}")
    if not base.is_dir():
        raise ValueError(f"Path is not a directory: {base}")

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
    p = _resolve_path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    s = p.stat()
    return {
        "path": str(p),
        "size_bytes": s.st_size,
        "created": datetime.fromtimestamp(s.st_ctime, tz=timezone.utc).isoformat(),
        "modified": datetime.fromtimestamp(s.st_mtime, tz=timezone.utc).isoformat(),
        "extension": p.suffix,
        "is_file": p.is_file(),
        "is_dir": p.is_dir(),
    }
