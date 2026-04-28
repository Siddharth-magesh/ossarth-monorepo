# OSSARTH — Hackathon Plan

## What We Are Building

**OSSARTH** is a User-Space AI Daemon that replaces the traditional OS shell with a natural language interface. The user types intent in plain English; a Multi-Agent System (MAS) classifies it, plans an execution graph, and dispatches Model Context Protocol (MCP) tools to carry it out — while a live System Monitor Dashboard shows the OS reacting in real time.

This is not an application on top of an OS. This is the OS interface itself.

---

## Scope Decision (Read This First)

We will **not** touch the Linux kernel. Kernel modules require weeks of low-level C development and specific hardware access. Instead:

- All kernel-level concepts (RAM allocation, GPU VRAM, CPU scheduler threads, process priority) are **simulated via a hardcoded in-memory resource model** written in Python.
- MCP tool calls mutate this simulated state.
- The System Monitor Dashboard reads and displays this state live.

To a judge watching the demo, the AI is visibly controlling system resources. The architecture — Intent Agent → Orchestrator → MCP → Resource Layer — is identical to what a production system with real kernel hooks would look like. We are proving the concept cleanly.

---

## High-Level Architecture

```
User Input (natural language)
        │
        ▼
   Intent Agent          ← LLM call: classifies input into structured intent JSON
        │
        ▼
  Orchestrator Agent     ← LLM call: breaks intent into ordered execution graph
        │
        ▼
   MCP Tool Layer        ← Python functions: filesystem, process, network ops
        │
        ▼
 Kernel Resource Sim     ← In-memory state: RAM, GPU, threads, process table
        │
        ▼
  Dashboard (Web UI)     ← FastAPI SSE → live gauges, process table, scheduler view
```

---

## Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| LLM (primary) | Ollama local models (`llama3.1:8b`, `mistral:7b`, etc.) | Free, private, no API cost, runs offline |
| LLM (fallback) | Groq inference API (`llama-3.1-8b-instant`) | Free tier, ultra-fast, kicks in if Ollama unavailable |
| LLM Client | `mas_core/llm_client.py` abstraction | Unified interface — rest of code never touches provider SDK directly |
| MAS Core | Python 3.11+ | Fastest to build and iterate |
| MCP Tool Layer | Python (`os`, `subprocess`, `pathlib`) | Direct system access, no overhead |
| Kernel Simulation | Python dataclass, in-memory | Simple, zero dependencies, demo-safe |
| Dashboard Backend | FastAPI + Server-Sent Events | Lightweight real-time streaming |
| Dashboard Frontend | Vanilla JS + Chart.js | No build step, runs anywhere |
| Boot Experience | Bash/Bat launch script | One command starts everything |

---

## Day 0 — Pre-Hackathon Setup (Hour 1)

These must be done before writing a single line of feature code.

- [ ] Create GitHub repo: `ossarth`
- [ ] Set up folder structure exactly as defined in `project_structure.md`
- [ ] Create `.env` with `GROQ_API_KEY` and Ollama model config
- [ ] Create `requirements.txt` with: `ollama`, `groq`, `fastapi`, `uvicorn`, `python-dotenv`, `pydantic`, `psutil`
- [ ] Set up Python virtual environment, install deps
- [ ] Verify Ollama is running: `ollama list` → confirm model available
- [ ] Verify Groq fallback: set `OSSARTH_LLM_PROVIDER=groq` and confirm API key works
- [ ] Write `os_customization/boot_message.txt` — the ASCII art boot screen shown on launch
- [ ] Write `os_customization/launch.sh` — single script that starts daemon + dashboard

**Gate:** Running `./os_customization/launch.sh` prints the boot screen and starts both processes without errors.

---

## Day 1 — The Brain (MAS Core)

**Goal:** A working REPL where natural language input produces a structured execution graph.

### Morning — Intent Agent

Build `mas_core/intent_agent.py`.

The Intent Agent takes a raw user string and makes a single LLM call (Ollama local or Groq fallback) via `llm_client.py` with a carefully crafted system prompt. It must return a clean JSON object classifying the intent. No extra text, no markdown — pure JSON only.

Output schema:
```json
{
  "task_type": "create_and_execute",
  "priority": "normal",
  "entities": [
    { "type": "file", "value": "test.py" },
    { "type": "command", "value": "python test.py" }
  ],
  "raw_input": "write a script that prints hello and run it"
}
```

Supported `task_type` values: `query_system`, `file_operation`, `create_and_execute`, `search_and_summarize`, `process_management`, `unknown`.

Also build `mas_core/prompts.py` containing all system prompts as constants. No prompt strings should be scattered across files.

**Checkpoint:** `python mas_core/intent_agent.py` runs as a standalone script, takes input from stdin, prints the JSON.

### Late Morning — Orchestrator Agent

Build `mas_core/orchestrator_agent.py`.

The Orchestrator takes the intent JSON and makes a second LLM call via `llm_client.py`. It must return an ordered list of tool calls — the execution graph.

Output schema:
```json
[
  { "step": 1, "tool": "write_file", "args": { "path": "/tmp/test.py", "content": "print('hello')" } },
  { "step": 2, "tool": "start_process", "args": { "cmd": "python /tmp/test.py" } }
]
```

The Orchestrator's system prompt must include the full list of available MCP tools and their argument schemas so it only generates calls to tools that exist.

**Checkpoint:** Feed the Intent Agent's output into the Orchestrator, get back a valid execution graph JSON.

### Afternoon — Agent Runner + Tool Registry Stubs

Build `mas_core/agent_runner.py` — the main REPL loop:
1. Print boot message
2. Read user input from stdin
3. Call Intent Agent → get intent JSON
4. Call Orchestrator → get execution graph
5. For each step in the graph, call the registered tool
6. Print result of each step
7. Loop back to step 2

Build `mcp_tools/tool_registry.py` — maps tool name strings to callable Python functions. At this stage, register **stub** versions of every tool that just print what they would do and return a fake success response.

**Checkpoint:** Type *"list all running processes"* → see intent JSON printed → see execution graph printed → see stub tool called for each step.

### Evening — Kernel Simulation

Build `kernel_sim/resource_state.py` — the single source of truth for all simulated resources. One global singleton instance.

Build `kernel_sim/resource_hooks.py` — functions called by each MCP tool to mutate the resource state. Each hook takes the tool name and args, updates the relevant fields (CPU%, RAM used, thread count, process table).

Wire the hooks into the stub tools in `tool_registry.py` so that every stub call also triggers the appropriate resource mutation.

Build `kernel_sim/scheduler_sim.py` — a simple round-robin scheduler that maintains a queue of fake "tasks" drawn from the active process table. Cycles through them on a 1-second tick, simulating context switching. This runs in a background thread.

**End-of-Day Gate:** Type any command → execution graph is generated → stubs are called → `resource_state` values change → print the state after each command and verify the numbers moved correctly.

---

## Day 2 — The Hands + The Eyes (MCP Tools + Dashboard)

**Goal:** Real tool execution and a live dashboard. Full end-to-end working prototype by midnight.

### Morning — Real MCP Tools

Replace the stubs in `mcp_tools/` with real implementations.

`mcp_tools/filesystem_mcp.py`:
- `read_file(path)` → reads and returns file content, bumps RAM in resource state
- `write_file(path, content)` → writes to disk, adds to resource state file tracking
- `search_directory(path, query)` → glob + optional grep, returns list of matches
- `list_directory(path)` → returns structured directory listing
- `delete_file(path)` → deletes file, removes from tracking

`mcp_tools/process_mcp.py`:
- `list_processes()` → returns the simulated process table (NOT real `ps`)
- `start_process(cmd)` → runs via `subprocess.Popen`, adds entry to simulated process table, bumps CPU and thread count
- `kill_process(pid)` → kills real subprocess if running, removes from table, decrements CPU and threads
- `get_process_info(pid)` → returns details for one process from the table

Each real tool must call the appropriate resource hook after executing.

**Checkpoint:** `write_file`, `read_file`, `start_process`, `kill_process` all work correctly when called directly. Resource state mutates as expected after each call.

### Afternoon — Dashboard

Build `dashboard/server.py`:
- FastAPI app
- `GET /` → serves `static/index.html`
- `GET /metrics` → SSE endpoint that streams `resource_state` as JSON every second
- `GET /history` → returns last 60 seconds of resource snapshots for sparklines
- `POST /command` → accepts a command string, runs it through the MAS, returns result (so the dashboard can have its own input box)

Build `dashboard/static/index.html` + `dashboard/static/dashboard.js` + `dashboard/static/style.css`:

The dashboard must show:
- **CPU Gauge** — donut chart, 0–100%, updates every second
- **RAM Bar** — used MB / total MB, with percentage label
- **GPU VRAM Bar** — used MB / total MB
- **Active Threads Counter** — large number display with delta indicator
- **Process Table** — live table with columns: PID, Name, CPU%, Memory, Status, Started
- **Scheduler Queue** — scrolling list of the round-robin queue from `scheduler_sim`
- **Command Log** — chronological list of every intent → execution graph → result the daemon has processed
- **Latency Display** — shows time-to-execute for the last command in ms

Dark theme. Monospace font for process table and logs. Should feel like a real sysadmin tool.

**Checkpoint:** Dashboard loads at `http://localhost:8000`. All gauges display. Gauges update when resource state changes (manually mutate state and verify).

### Evening — Full Integration

- Replace stub tools in `tool_registry.py` with the real implementations
- Run full end-to-end test:

**Integration Test Command:**
> *"Create a Python script that prints the Fibonacci sequence up to 100, save it to /tmp/fib.py, and run it."*

Expected flow:
1. Intent Agent → `{ task_type: "create_and_execute", entities: [file: /tmp/fib.py, ...] }`
2. Orchestrator → `[write_file(/tmp/fib.py, <fibonacci code>), start_process(python /tmp/fib.py)]`
3. `write_file` executes → file appears on disk → RAM bumps
4. `start_process` executes → output prints → process appears in dashboard table → CPU spikes
5. Process completes → CPU drops → process removed from table

**End-of-Day Gate:** The above works completely without manual intervention. Dashboard shows the resource changes in real time.

---

## Day 3 — The Proof + The Pitch

**Goal:** Quantified evidence and a polished presentation.

### Morning — Benchmarks

Run `benchmarks/latency_test.py`:
- 10 commands of varying complexity (simple query, file op, multi-step create+run)
- Record: time from keypress to first tool execution, time to full completion
- Compare against equivalent raw bash commands typed manually
- Output: `benchmarks/results/latency_results.json`

Run `benchmarks/accuracy_test.py`:
- 10 pre-written prompts with known correct execution graphs
- Compare generated graph against expected graph
- Score: exact match on tool names and order
- Output: `benchmarks/results/accuracy_results.json`

Run `benchmarks/resource_overhead_test.py`:
- Measure CPU and RAM consumed by the daemon itself (the Python process + Claude API wait time) while idle and under load
- Output: `benchmarks/results/overhead_results.json`

### Afternoon — Pitch Deck

Create `planning/pitch_deck/slides_outline.md` with the following structure:

1. **The Problem** — Cloud AI sends your data to someone else's server. Standard shells are rigid, command-syntax-dependent, and require expertise.
2. **The Vision** — AI Sovereignty. Your compute. Your data. Your intent.
3. **OSSARTH** — Architecture diagram. What each layer does in one sentence.
4. **Live Demo** — Play the recording from the integration test.
5. **Benchmark Data** — Latency cost of AI routing. Accuracy on complex tasks. Frame overhead as the cost of autonomy, not a flaw.
6. **Roadmap** — Real kernel hooks, local LLM (Llama/Phi), decentralized compute layer.

---

## Demo Script (Presented to Judges)

Execute these commands in sequence during the live presentation.

```
BOOT
  Run: ./os_customization/launch.sh
  Expected: OSSARTH ASCII boot screen → daemon starts → dashboard opens at localhost:8000

COMMAND 1 — Simple Query
  Input: "show me all running processes"
  Expected: process table returned, dashboard process list refreshes

COMMAND 2 — File Creation
  Input: "create a file called hello.txt in /tmp with the content 'OSSARTH is live'"
  Expected: write_file called → file appears on disk → RAM ticks up slightly

COMMAND 3 — Multi-Step Create + Execute
  Input: "write a python script that prints the first 10 prime numbers, save it to /tmp/primes.py, and run it"
  Expected:
    - Orchestrator generates: [write_file, start_process]
    - File is written to disk (verify: cat /tmp/primes.py)
    - Script runs, output visible in command log
    - Dashboard: new process appears, CPU spikes, then process completes and CPU drops

COMMAND 4 — Search + Summarize
  Input: "search /tmp for all .py files and tell me what each one does"
  Expected:
    - Orchestrator generates: [search_directory, read_file x N, summarize]
    - Each file is read
    - Claude returns a plain-English summary of each script
    - RAM climbs during reads, drops after

CLOSE
  Point at the dashboard: "Every gauge you see moved because the AI issued a command.
  This is what it looks like when intelligence becomes the operating system."
```

---

## Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Ollama model not responding | Low | Auto-fallback to Groq via `llm_client.py`; daemon logs which provider is active |
| Groq API rate limit during demo | Low | Cache responses for known demo commands; Ollama is primary anyway |
| Local model produces bad JSON | Medium | Error-correction retry prompt; `unknown` intent fallback on second failure |
| `start_process` hangs on bad LLM-generated code | Medium | Wrap all subprocess calls with a 10-second timeout |
| Dashboard SSE drops connection | Low | Auto-reconnect logic in `dashboard.js` |
| Orchestrator generates invalid tool name | Medium | Validate every graph step against `tool_registry` before execution; return error to user gracefully |
| Wi-Fi down during demo | Low | Pre-record a video of the full demo as backup; Ollama runs fully offline |

---

## End-of-Hackathon Checklist

- [ ] Full end-to-end loop works for all 4 demo commands
- [ ] Dashboard displays all gauges with live updates
- [ ] Benchmark results files exist and have real data
- [ ] `./os_customization/launch.sh` starts everything in one command
- [ ] Root `README.md` is written and readable by a judge in under 2 minutes
- [ ] Backup demo video recorded
