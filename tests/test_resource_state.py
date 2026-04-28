"""
OSSARTH — tests/test_resource_state.py

Unit tests for the Kernel Resource State singleton.
Tests thread-safe mutation, process table management, and serialisation.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("OSSARTH_STATE_FILE", str(Path(tempfile.gettempdir()) / "ossarth_test_state.json"))

# Reset singleton between tests
from kernel_sim import resource_state as rs_module


@pytest.fixture(autouse=True)
def fresh_state():
    """Reset the singleton before each test."""
    rs_module.ResourceState._instance = None
    yield
    rs_module.ResourceState._instance = None


def get_state():
    return rs_module.get_resource_state()


class TestSingleton:

    def test_singleton_returns_same_instance(self):
        a = get_state()
        b = get_state()
        assert a is b

    def test_singleton_across_threads(self):
        instances = []
        def grab():
            instances.append(get_state())
        threads = [threading.Thread(target=grab) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert all(i is instances[0] for i in instances)


class TestMutations:

    def test_bump_cpu(self):
        state = get_state()
        initial = state.get("cpu_usage_percent")
        state.bump_cpu(10.0)
        assert state.get("cpu_usage_percent") == pytest.approx(initial + 10.0, abs=0.1)

    def test_bump_cpu_clamps_to_95(self):
        state = get_state()
        state.bump_cpu(999.0)
        assert state.get("cpu_usage_percent") <= 95.0

    def test_bump_ram(self):
        state = get_state()
        initial = state.get("used_ram_mb")
        state.bump_ram(512)
        assert state.get("used_ram_mb") == initial + 512

    def test_bump_ram_clamps_to_total(self):
        state = get_state()
        total = state.get("total_ram_mb")
        state.bump_ram(999999)
        assert state.get("used_ram_mb") <= total

    def test_bump_threads(self):
        state = get_state()
        initial = state.get("active_threads")
        state.bump_threads(5)
        assert state.get("active_threads") == initial + 5

    def test_bump_ram_negative(self):
        state = get_state()
        state.bump_ram(100)
        mid = state.get("used_ram_mb")
        state.bump_ram(-100)
        assert state.get("used_ram_mb") == mid - 100

    def test_mutate_function(self):
        state = get_state()
        state.mutate(lambda s: setattr(s, "command_count", 42))
        assert state.get("command_count") == 42


class TestProcessTable:

    def test_add_process_returns_pid(self):
        state = get_state()
        pid = state.add_process({"name": "test_proc", "cmd": "python test.py"})
        assert isinstance(pid, int)
        assert pid >= 1001

    def test_add_process_assigns_unique_pids(self):
        state = get_state()
        pids = [state.add_process({"name": f"proc_{i}"}) for i in range(5)]
        assert len(set(pids)) == 5

    def test_remove_process_returns_true_when_found(self):
        state = get_state()
        pid = state.add_process({"name": "kill_me"})
        removed = state.remove_process(pid)
        assert removed is True

    def test_remove_process_returns_false_when_not_found(self):
        state = get_state()
        removed = state.remove_process(99999)
        assert removed is False

    def test_get_process_returns_entry(self):
        state = get_state()
        pid = state.add_process({"name": "findme", "cmd": "sleep 10"})
        entry = state.get_process(pid)
        assert entry is not None
        assert entry["name"] == "findme"
        assert entry["pid"] == pid

    def test_get_process_returns_none_for_unknown_pid(self):
        state = get_state()
        assert state.get_process(99999) is None


class TestFileTracking:

    def test_track_file(self):
        state = get_state()
        state.track_file("/tmp/test.txt", 1024)
        tracked = state.get("tracked_files")
        assert any(f["path"] == "/tmp/test.txt" for f in tracked)

    def test_untrack_file(self):
        state = get_state()
        state.track_file("/tmp/remove_me.txt", 512)
        state.untrack_file("/tmp/remove_me.txt")
        tracked = state.get("tracked_files")
        assert not any(f["path"] == "/tmp/remove_me.txt" for f in tracked)


class TestSerialisation:

    def test_to_dict_contains_required_keys(self):
        state = get_state()
        d = state.to_dict()
        required = [
            "cpu_usage_percent", "used_ram_mb", "total_ram_mb",
            "active_threads", "process_table", "scheduler_queue",
            "uptime_seconds", "command_count",
        ]
        for key in required:
            assert key in d, f"Missing key: {key}"

    def test_flush_to_file_creates_file(self, tmp_path):
        state = get_state()
        state._state_file = tmp_path / "test_state.json"
        state.flush_to_file()
        assert state._state_file.exists()
        with open(state._state_file) as f:
            data = json.load(f)
        assert "cpu_usage_percent" in data


class TestReset:

    def test_reset_to_baseline(self):
        state = get_state()
        state.bump_cpu(50.0)
        state.bump_ram(2000)
        state.add_process({"name": "test"})
        state.reset_to_baseline()
        assert state.get("cpu_usage_percent") == pytest.approx(8.0, abs=1.0)
        assert state.get("used_ram_mb") == 1200
        assert state.get("process_table") == []
