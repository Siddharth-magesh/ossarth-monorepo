# OSSARTH — Project Tracking

> Last updated: 2026-04-28
> Status: Day 1 complete · Day 2 (Dashboard) complete · Day 3 scripts complete · **58/58 tests passing**

---

## Legend
- ✅ Complete — code written, proper implementation
- 🔶 Partial — exists but needs work
- ❌ Missing — not yet created
- 📋 Planned — scheduled for a future day

---

## Phase 0 — Setup & Docs

| Item | File | Status | Notes |
|---|---|---|---|
| Project root structure | `/` | ✅ | All dirs created |
| Requirements | `requirements.txt` | ✅ | ollama, groq, fastapi, uvicorn, pydantic, psutil |
| Environment config | `.env.example` | ✅ | GROQ_API_KEY, Ollama model, all runtime vars |
| Gitignore | `.gitignore` | ✅ | Python standard + .env, venv, results/ |
| Hackathon plan (updated) | `docs/hackathon_plan.md` | ✅ | Claude API → Ollama/Groq references replaced |
| Architecture (update needed) | `docs/architecture.md` | 🔶 | Still has Claude API references in config table — minor |
| Project structure (update needed) | `docs/project_structure.md` | 🔶 | .env.example section still shows ANTHROPIC_API_KEY |

---

## Phase 1 — MAS Core (Day 1 Morning–Afternoon)

| Item | File | Status | Notes |
|---|---|---|---|
| Package init | `mas_core/__init__.py` | ✅ | |
| LLM client abstraction | `mas_core/llm_client.py` | ✅ | Ollama-first, Groq fallback, auto provider routing |
| Pydantic schemas | `mas_core/schemas.py` | ✅ | All schemas: Intent, Execution, Tool, Command log |
| Prompt constants | `mas_core/prompts.py` | ✅ | Intent, Orchestrator, Summarize, Error Correction |
| Intent Agent | `mas_core/intent_agent.py` | ✅ | classify(), error correction retry, verbose mode |
| Orchestrator Agent | `mas_core/orchestrator_agent.py` | ✅ | plan(), tool catalog injection, validation, retry |
| Context Manager | `mas_core/context_manager.py` | ✅ | Rolling 20-cmd history, reference word detection, persist |
| Agent Runner (REPL) | `mas_core/agent_runner.py` | ✅ | Full REPL loop, dispatch, CLI flags, boot sequence |

**Day 1 Morning Gate:** ✅ `python -m mas_core.intent_agent` — standalone REPL works

**Day 1 Afternoon Gate:** ✅ Full pipeline: input → intent JSON → execution graph → stub dispatch

---

## Phase 2 — MCP Tool Layer (Day 1 Evening)

| Item | File | Status | Notes |
|---|---|---|---|
| Package init | `mcp_tools/__init__.py` | ✅ | |
| Tool base decorator | `mcp_tools/tool_base.py` | ✅ | @mcp_tool: exception catch, timing, resource hook dispatch |
| Tool registry | `mcp_tools/tool_registry.py` | ✅ | ToolDefinition, register, call_tool, catalog string |
| Filesystem tools | `mcp_tools/filesystem_mcp.py` | ✅ | read, write, append, delete, search, list, get_info |
| Process tools | `mcp_tools/process_mcp.py` | ✅ | list, start (real Popen), kill, get_info |
| Network tools | `mcp_tools/network_mcp.py` | ✅ | interfaces, check_port, hostname, open_ports |
| System tools | `mcp_tools/system_mcp.py` | ✅ | resource_snapshot, uptime, command_history |

**Tool Count:** 18 tools registered across 4 modules

---

## Phase 3 — Kernel Simulation (Day 1 Evening)

| Item | File | Status | Notes |
|---|---|---|---|
| Package init | `kernel_sim/__init__.py` | ✅ | |
| Resource state singleton | `kernel_sim/resource_state.py` | ✅ | KernelResourceState + thread-safe ResourceState wrapper |
| Resource hooks | `kernel_sim/resource_hooks.py` | ✅ | on_write, on_read, on_search, on_start_process, on_kill, on_llm_call |
| Scheduler sim | `kernel_sim/scheduler_sim.py` | ✅ | Background daemon thread, round-robin, 1-sec ticks |

**Kernel Sim Features:**
- ✅ Thread-safe singleton with `threading.Lock`
- ✅ Temporary resource bumps with `threading.Timer` reversals
- ✅ Flush-to-file IPC for dashboard communication
- ✅ `reset_to_baseline()` for demo resets
- ✅ Realistic CPU jitter in scheduler ticks

---

## Phase 4 — Dashboard (Day 2)

| Item | File | Status | Notes |
|---|---|---|---|
| Package init | `dashboard/__init__.py` | ✅ | |
| FastAPI server | `dashboard/server.py` | ✅ | SSE /metrics, /history, /command, /history/commands, /health |
| Dashboard HTML | `dashboard/static/index.html` | ✅ | Full layout: gauges, cores, table, scheduler, log |
| Dashboard CSS | `dashboard/static/style.css` | ✅ | Dark theme, OSSARTH brand, responsive grid |
| Dashboard JS | `dashboard/static/dashboard.js` | ✅ | SSE, Chart.js donut+sparklines, process table diff, POST /command |

**Dashboard Features:**
- ✅ CPU donut chart (animated, color-coded by load)
- ✅ RAM bar with sparkline
- ✅ GPU VRAM bar with sparkline
- ✅ Thread counter with delta indicator and sparkline
- ✅ CPU per-core vertical bars (8 cores)
- ✅ Process table with new-row green flash / dead-row red fade
- ✅ Scheduler queue with active-process highlight
- ✅ Command input with POST /command and spinner
- ✅ Command log (newest-first, tool tags, color by success)
- ✅ SSE auto-reconnect (EventSource native)
- ✅ History ring buffer (300 snapshots, 5 min)
- ✅ Initial history load for sparklines on page load

---

## Phase 5 — OS Customization

| Item | File | Status | Notes |
|---|---|---|---|
| Boot message ASCII art | `os_customization/boot_message.txt` | ✅ | OSSARTH ASCII, tagline, hardware summary |
| Windows launch script | `os_customization/launch.bat` | ✅ | Activates venv, starts uvicorn, opens browser, runs REPL |
| Linux launch script | `os_customization/launch.sh` | ✅ | Equivalent for Linux/Mac |

---

## Phase 6 — Benchmarks (Day 3)

| Item | File | Status | Notes |
|---|---|---|---|
| Test command set | `benchmarks/test_commands.json` | ✅ | 10 commands, 4 tiers, Windows-safe paths |
| Latency test | `benchmarks/latency_test.py` | ✅ | 4-phase timing, cold/warm runs, JSON output |
| Accuracy test | `benchmarks/accuracy_test.py` | ✅ | 3-dimension scoring, by-tier breakdown |
| Overhead test | `benchmarks/resource_overhead_test.py` | ✅ | psutil CPU/RAM sampling, idle vs active |
| Consistency test | `benchmarks/consistency_test.py` | ✅ | B4 — 3 runs per command, pairwise comparison |
| Failure recovery test | `benchmarks/failure_recovery_test.py` | ✅ | B5 — 8 adversarial cases, scoring rubric |
| Report generator | `benchmarks/generate_report.py` | ✅ | Reads all results → summary.md |
| Results directory | `benchmarks/results/` | ✅ | .gitkeep in place, JSONs generated on Day 3 |

---

## Phase 7 — Tests

| Item | File | Status | Notes |
|---|---|---|---|
| Intent agent tests | `tests/test_intent_agent.py` | ✅ | LLM mocked, parsing, retries, schema, LLM exception handling |
| Orchestrator tests | `tests/test_orchestrator_agent.py` | ❌ | Not yet written |
| Filesystem MCP tests | `tests/test_filesystem_mcp.py` | ✅ | Full coverage of all 7 filesystem tools, Windows-safe paths |
| Process MCP tests | `tests/test_process_mcp.py` | ❌ | Not yet written |
| Resource state tests | `tests/test_resource_state.py` | ✅ | Singleton, mutations, process table, serialization |
| Tool registry tests | `tests/test_tool_registry.py` | ✅ | Registration, catalog, call_tool dispatch |

**Test result: 58/58 passing** (`pytest tests/ -v`, no warnings)

---

## Phase 8 — Root Files

| Item | File | Status | Notes |
|---|---|---|---|
| README for judges | `README.md` | ✅ | Architecture, 4-command setup, demo commands, scope note |
| This tracking file | `docs/tracking.md` | ✅ | |

---

## Remaining Work (Priority Order)

### 🔴 High Priority (needed for demo — Day 3)
1. 🔶 Run `benchmarks/latency_test.py` and save results
2. 🔶 Run `benchmarks/accuracy_test.py` and save results
3. 🔶 Run `benchmarks/consistency_test.py` and save results
4. 🔶 Run `benchmarks/failure_recovery_test.py` and save results
5. 🔶 Run `benchmarks/generate_report.py` to produce `summary.md`
6. 🔶 `docs/architecture.md` — minor: update config table (Claude → Groq/Ollama)
7. 🔶 `docs/project_structure.md` — minor: update .env.example section

### 🟡 Medium Priority (good to have)
8. ❌ `tests/test_orchestrator_agent.py` — LLM mocked tests for orchestrator
9. ❌ `tests/test_process_mcp.py` — subprocess tests for process tools

### 🟢 Low Priority (polish)
10. ❌ `planning/pitch_deck/slides_outline.md` — pitch deck outline

---

## Verification Checkpoints

### ✅ Can verify now
```bash
# Activate venv, then:
python -m mas_core.intent_agent          # standalone intent REPL
python -m mas_core.orchestrator_agent    # standalone orchestrator REPL
python -m mas_core.agent_runner          # full REPL
uvicorn dashboard.server:app --port 8000 # dashboard standalone
pytest tests/ -v                         # unit tests
```

### 📋 Day 3 verification
```bash
python benchmarks/latency_test.py
python benchmarks/accuracy_test.py
python benchmarks/resource_overhead_test.py
python benchmarks/generate_report.py    # after all benchmarks done
```

---

## Integration Test Commands (End-of-Day Gate)

```
OSSARTH > list all running processes
Expected: list_processes called → process table returned

OSSARTH > create a file called hello.txt in ossarth_workspace with the content 'OSSARTH is live'
Expected: write_file called → file on disk → RAM ticks up

OSSARTH > write a python script that prints the first 10 prime numbers, save it to ossarth_workspace/primes.py, and run it
Expected: write_file → start_process → output visible → CPU spikes → drops

OSSARTH > search ossarth_workspace for all .py files and tell me what each one does
Expected: search_directory → read_file × N → summary output
```

---

## File Count Summary

| Module | Files | Lines (approx) |
|---|---|---|
| `mas_core/` | 8 | ~1,200 |
| `mcp_tools/` | 7 | ~700 |
| `kernel_sim/` | 4 | ~550 |
| `dashboard/` | 4 | ~700 |
| `benchmarks/` | 4 (+results/) | ~450 |
| `tests/` | 4 | ~550 |
| `os_customization/` | 3 | ~150 |
| Root files | 5 | ~300 |
| **Total** | **39** | **~4,600** |
