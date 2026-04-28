# OSSARTH — Project Structure

Every folder and file in this project is described below. When building, treat this document as the source of truth for what belongs where and what each file must contain. No file is a placeholder — every file listed here has a specific, non-trivial job.

---

## Root Layout

```
ossarth/
├── mas_core/
├── mcp_tools/
├── kernel_sim/
├── dashboard/
├── os_customization/
├── benchmarks/
├── planning/
├── tests/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## `/mas_core` — Multi-Agent System Brain

This is the intelligence layer of OSSARTH. It contains every module responsible for understanding user intent and planning what to do about it. Nothing in this folder touches the filesystem or executes processes — it only thinks.

```
mas_core/
├── intent_agent.py
├── orchestrator_agent.py
├── agent_runner.py
├── prompts.py
├── schemas.py
└── context_manager.py
```

### `mas_core/intent_agent.py`

**Purpose:** First stage of the pipeline. Takes a raw natural language string from the user and returns a structured JSON object classifying what the user wants.

**How it works:**
- Makes a single LLM call via `llm_client.py` (Ollama local first, Groq fallback) using the system prompt from `prompts.INTENT_SYSTEM_PROMPT`
- Instructs the model to return only JSON — no preamble, no markdown fences
- Parses and validates the response against the `IntentSchema` from `schemas.py`
- If parsing fails, retries once with an error-correcting prompt; on second failure, returns `{ task_type: "unknown" }`

**What it must return — `IntentSchema`:**
```json
{
  "task_type": "create_and_execute",
  "priority": "normal",
  "entities": [
    { "type": "file", "value": "/tmp/test.py" },
    { "type": "language", "value": "python" },
    { "type": "action", "value": "run" }
  ],
  "requires_clarification": false,
  "clarification_question": null,
  "raw_input": "write a python script that prints hello and run it"
}
```

**Supported `task_type` values:**
- `query_system` — user wants information about the system state
- `file_operation` — create, read, edit, delete, move files
- `create_and_execute` — write code/script and then run it
- `search_and_summarize` — find files/content and explain them
- `process_management` — start, stop, inspect running processes
- `unknown` — cannot be classified; daemon should ask for clarification

**Edge cases to handle:**
- Empty input → return `unknown` with clarification question "Please describe what you'd like to do."
- Input that is already a valid bash command → still classify it, do not pass it directly to subprocess
- Multi-part requests ("do X then Y") → `entities` list captures both parts; Orchestrator handles sequencing

---

### `mas_core/orchestrator_agent.py`

**Purpose:** Second stage of the pipeline. Takes the intent JSON and produces an ordered execution graph — a list of concrete tool calls the daemon will execute step by step.

**How it works:**
- Makes a single LLM call via `llm_client.py` using `prompts.ORCHESTRATOR_SYSTEM_PROMPT`
- The system prompt includes the complete tool catalog (all tool names, descriptions, argument schemas) so the model can only generate calls to tools that actually exist
- Returns a list of step objects; each step specifies exactly one tool call
- Validates every step's `tool` field against the live tool registry before returning — any step referencing a non-existent tool causes a retry

**What it must return — `ExecutionGraph`:**
```json
[
  {
    "step": 1,
    "tool": "write_file",
    "args": {
      "path": "/tmp/test.py",
      "content": "print('hello')"
    },
    "description": "Save the Python script to disk",
    "expected_output": "file_path"
  },
  {
    "step": 2,
    "tool": "start_process",
    "args": {
      "cmd": "python /tmp/test.py"
    },
    "description": "Execute the script",
    "expected_output": "stdout"
  }
]
```

**Key constraints the Orchestrator must respect:**
- Steps must be ordered (step 1 before step 2); if a later step depends on output from an earlier step, the args can reference `"$step_1_output"` as a placeholder, which `agent_runner.py` resolves at runtime
- Maximum 10 steps per execution graph; if a task genuinely requires more, the Orchestrator should decompose it into a high-level plan and ask the user to confirm before proceeding
- Never generate a step that calls a tool not in the registry

---

### `mas_core/agent_runner.py`

**Purpose:** The main entry point and REPL loop. Orchestrates the full pipeline from user input to tool execution to output display.

**Startup sequence:**
1. Load environment variables from `.env`
2. Initialize the tool registry (import all MCP tools, register them)
3. Initialize `KernelResourceState` singleton
4. Start the scheduler sim background thread
5. Print the boot message from `os_customization/boot_message.txt`
6. Start the dashboard server as a background subprocess
7. Enter the REPL loop

**REPL loop (per iteration):**
1. Print `OSSARTH > ` prompt, wait for user input
2. Pass raw input to `IntentAgent.classify()` → get intent JSON
3. If `requires_clarification` is true, print the clarification question, collect user answer, append it to the original input, re-run step 2
4. Pass intent JSON to `OrchestratorAgent.plan()` → get execution graph
5. Print the execution plan to the user in human-readable form before executing (optional `--verbose` flag controls detail level)
6. For each step in the execution graph:
   a. Resolve any `$step_N_output` references using previous step results
   b. Look up the tool in `tool_registry`
   c. Call the tool with the resolved args
   d. Store the result keyed by step number
   e. Print step result
7. Log the full command (input → intent → graph → results) to `context_manager.py`
8. Loop

**CLI flags:**
- `--verbose` — print full intent JSON and execution graph before executing
- `--dry-run` — print the execution graph but do not call any tools
- `--no-dashboard` — start daemon without the web dashboard

---

### `mas_core/prompts.py`

**Purpose:** Single source of truth for every LLM prompt in the project. No prompt strings live anywhere else.

**Contents:**

`INTENT_SYSTEM_PROMPT` — Detailed instruction for the Intent Agent. Must specify:
- Respond in JSON only. No text before or after. No markdown.
- Exact output schema with field descriptions
- List of valid `task_type` values with one-sentence descriptions each
- Examples: 3–5 input/output pairs covering edge cases

`ORCHESTRATOR_SYSTEM_PROMPT` — Detailed instruction for the Orchestrator. Must include:
- You are a planning agent. You receive an intent and produce a step-by-step tool execution plan.
- Respond in JSON only. An array of step objects.
- The full tool catalog: for each tool, its name, what it does, and its argument schema. This section is injected dynamically from `tool_registry.py` at runtime so it stays in sync.
- Rules: max 10 steps, all tools must exist in the catalog, args must match the schema exactly
- Examples: 2–3 intent → execution graph pairs

`SUMMARIZE_PROMPT` — Used by `search_and_summarize` tasks when the Orchestrator adds a final "explain what these files do" step. Takes file contents as context.

`ERROR_CORRECTION_PROMPT` — Used when JSON parsing fails. Feeds the malformed output back to the model with instruction to fix and return valid JSON only.

---

### `mas_core/schemas.py`

**Purpose:** Pydantic models for every data structure passed between agents and tools. Type safety and validation at every boundary.

**Models defined here:**
- `EntityItem` — `{ type: str, value: str }`
- `IntentSchema` — the full intent object (fields above)
- `ExecutionStep` — one step in the execution graph
- `ExecutionGraph` — list of `ExecutionStep`, validated to have sequential step numbers and no duplicate step numbers
- `ToolResult` — `{ step: int, tool: str, success: bool, output: Any, error: Optional[str], duration_ms: float }`
- `CommandLogEntry` — full record of one user command: raw input, intent, graph, all results, total duration

All models use strict validation. A malformed response from the LLM that fails Pydantic validation triggers the error correction flow in the agent.

---

### `mas_core/context_manager.py`

**Purpose:** Maintains a rolling history of the last N commands for multi-turn context. Allows the daemon to understand references like "run that again" or "delete the file you just created."

**Responsibilities:**
- Stores the last 20 `CommandLogEntry` objects in memory
- Provides `get_recent_context(n=5)` → returns last N entries serialized to a compact string for injection into the next LLM prompt
- Provides `get_last_output(step_description)` → fuzzy-matches a description against recent tool outputs and returns the most likely match (used to resolve "that file you created" references)
- Writes command history to `~/.ossarth_history` as newline-delimited JSON for persistence across sessions (reads it on startup)

---

## `/mcp_tools` — Model Context Protocol Tool Layer

This folder contains every tool the Orchestrator can call. Each tool is a Python function with a defined signature. Tools interact with the real filesystem and real processes — they are the only layer that has side effects. Every tool also calls into `kernel_sim/resource_hooks.py` after executing to update the simulated resource state.

```
mcp_tools/
├── filesystem_mcp.py
├── process_mcp.py
├── network_mcp.py
├── tool_registry.py
└── tool_base.py
```

### `mcp_tools/tool_base.py`

**Purpose:** Base class and decorator that every MCP tool function uses. Provides consistent error handling, timing, and result formatting.

**`@mcp_tool` decorator responsibilities:**
- Wraps the function in a try/except; catches all exceptions and returns a `ToolResult` with `success=False` and the error message rather than crashing the daemon
- Records start and end time, attaches `duration_ms` to the result
- Calls `resource_hooks.on_tool_call(tool_name, args, result)` after the function returns (regardless of success/failure)
- Logs the call to stdout in verbose mode

Every tool function must be decorated with `@mcp_tool` and must return data that can be serialized into a `ToolResult`.

---

### `mcp_tools/filesystem_mcp.py`

**Purpose:** All file and directory operations. Every function here is a real operation on the real filesystem using `pathlib` and standard Python I/O.

**Functions:**

`read_file(path: str) -> str`
- Reads and returns the full text content of the file at `path`
- Raises a clean error if the file does not exist or is not readable
- Resource hook: increment `used_ram_mb` by `ceil(file_size_bytes / 1024)` while the content is "in memory" (reset 2 seconds later via a timer)

`write_file(path: str, content: str) -> str`
- Creates parent directories if they don't exist
- Writes `content` to `path` (overwrites if exists)
- Returns the absolute path of the written file
- Resource hook: add the file to `resource_state.tracked_files` with its size

`append_file(path: str, content: str) -> str`
- Appends `content` to the file at `path`
- Creates the file if it does not exist

`delete_file(path: str) -> bool`
- Deletes the file at `path`
- Returns True on success
- Resource hook: remove from `tracked_files`

`search_directory(path: str, query: str, file_extension: Optional[str] = None) -> list[dict]`
- Recursively searches `path` for files whose names or contents match `query`
- `query` is matched against filenames with glob and against file contents with a case-insensitive string search (not regex)
- `file_extension` filters by extension (e.g., `".py"`)
- Returns: `[{ "path": str, "match_type": "name"|"content", "preview": str (first 100 chars of matching line) }]`
- Limits results to 50 matches to prevent runaway output

`list_directory(path: str) -> list[dict]`
- Returns structured listing of `path` (one level deep, not recursive)
- Each entry: `{ "name": str, "type": "file"|"directory", "size_bytes": int, "modified": ISO timestamp }`

`get_file_info(path: str) -> dict`
- Returns metadata for one file: path, size, created, modified, permissions, extension

---

### `mcp_tools/process_mcp.py`

**Purpose:** Process lifecycle management. Uses `subprocess` to actually launch and kill real processes, but maintains a **simulated** process table in `resource_state` rather than reading from `ps`.

**Functions:**

`list_processes() -> list[dict]`
- Returns the simulated process table from `resource_state.process_table`
- Each entry: `{ "pid": int, "name": str, "cmd": str, "cpu_percent": float, "memory_mb": float, "status": str, "started": ISO timestamp }`
- Does NOT call `ps` or read `/proc` — the table is maintained by `start_process` and `kill_process`

`start_process(cmd: str, name: Optional[str] = None, timeout_seconds: int = 10) -> dict`
- Launches `cmd` via `subprocess.Popen` with `stdout=PIPE`, `stderr=PIPE`
- Waits up to `timeout_seconds` for completion; if it times out, kills the process and returns an error result
- On success: adds an entry to `resource_state.process_table`, increments `active_threads`, bumps `cpu_usage_percent` by a calculated delta
- Returns: `{ "pid": int, "stdout": str, "stderr": str, "returncode": int, "duration_ms": float }`
- `name` is a human-readable label for the process table; defaults to the first word of `cmd`

`kill_process(pid: int) -> bool`
- Sends SIGTERM to the process with the given PID
- If the process doesn't respond within 3 seconds, sends SIGKILL
- Removes the entry from `resource_state.process_table`
- Decrements `active_threads` and `cpu_usage_percent` appropriately
- Returns True if the process was found and killed, False if PID not found in the table

`get_process_info(pid: int) -> dict`
- Returns the entry for `pid` from `resource_state.process_table`
- Returns an error dict if not found

---

### `mcp_tools/network_mcp.py`

**Purpose:** Lightweight network information tools. No actual network calls that could be slow or require authentication — only local network state queries and simple HTTP checks.

**Functions:**

`get_network_interfaces() -> list[dict]`
- Returns list of network interfaces with: name, IP address, MAC, is_up status
- Uses Python's `socket` and `fcntl` (or `psutil` if available) to get this information

`check_port(host: str, port: int, timeout_seconds: float = 2.0) -> dict`
- Attempts a TCP connection to `host:port`, returns `{ "reachable": bool, "latency_ms": float }`

`get_hostname() -> str`
- Returns the machine's hostname

`get_open_ports() -> list[int]`
- Returns a hardcoded list from `resource_state` of "open" simulated ports (e.g., [8000, 22, 80])
- This is part of the simulated kernel layer — we don't do a real port scan

---

### `mcp_tools/tool_registry.py`

**Purpose:** Central registry that maps tool name strings to callable functions. This is what the `agent_runner.py` uses to dispatch steps from the execution graph, and what `orchestrator_agent.py` reads to build the tool catalog injected into the system prompt.

**Structure:**

```python
TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "read_file": ToolDefinition(
        fn=filesystem_mcp.read_file,
        description="Read the full text content of a file at the given path.",
        args_schema={
            "path": { "type": "string", "description": "Absolute or relative path to the file", "required": True }
        }
    ),
    "write_file": ToolDefinition(...),
    ...
}
```

**`ToolDefinition` dataclass fields:**
- `fn` — the actual callable
- `description` — one-sentence description used in the Orchestrator's system prompt
- `args_schema` — dict of argument names to their type, description, and whether required

**`get_tool_catalog_string() -> str`** — returns the entire registry formatted as a readable string for injection into `ORCHESTRATOR_SYSTEM_PROMPT`.

**`call_tool(tool_name: str, args: dict) -> ToolResult`** — looks up the tool, validates args against the schema, calls the function, returns result.

---

## `/kernel_sim` — Simulated Kernel Resource Model

This folder contains the fake "kernel" that the dashboard visualizes and the MCP tools mutate. Nothing here touches the real Linux kernel. It is a Python in-memory model of what an AI-controlled kernel would track and expose.

```
kernel_sim/
├── resource_state.py
├── resource_hooks.py
└── scheduler_sim.py
```

### `kernel_sim/resource_state.py`

**Purpose:** Single source of truth for all simulated hardware and OS resource values. One global singleton. All reads and writes go through this module.

**The `KernelResourceState` dataclass:**

```python
@dataclass
class KernelResourceState:
    # --- Hardcoded Hardware Caps (never change at runtime) ---
    total_ram_mb: int = 8192
    total_gpu_vram_mb: int = 4096
    total_cpu_cores: int = 8
    max_scheduler_threads: int = 64
    cpu_clock_ghz: float = 3.6
    storage_total_gb: int = 256

    # --- Live CPU State ---
    cpu_usage_percent: float = 8.0         # baseline idle usage
    cpu_per_core: list[float]              # usage per core, list of 8 floats
    active_threads: int = 12              # baseline system threads

    # --- Live Memory State ---
    used_ram_mb: int = 1200               # baseline OS footprint
    used_gpu_vram_mb: int = 0
    tracked_files: list[dict]             # files written this session

    # --- Live Process State ---
    process_table: list[dict]             # managed by process_mcp
    next_pid: int = 1001                  # auto-increments for new processes

    # --- Live Storage State ---
    storage_used_gb: float = 42.3

    # --- Scheduler State ---
    scheduler_queue: list[str]            # task names currently queued
    scheduler_algorithm: str = "round_robin"
    context_switches_per_sec: float = 0.0

    # --- Session Metadata ---
    uptime_seconds: float = 0.0           # incremented by a background timer
    last_command_latency_ms: float = 0.0
    command_count: int = 0
```

**Thread safety:** All mutation methods use a `threading.Lock`. The dashboard SSE stream reads this object from a different thread, so every write must acquire the lock.

**Methods:**
- `to_dict() -> dict` — serializes all fields to a JSON-safe dict for the SSE stream
- `reset_to_baseline()` — resets live values to their startup defaults (used between demo runs)
- `add_process(entry: dict) -> int` — adds to `process_table`, returns the assigned PID
- `remove_process(pid: int) -> bool`

---

### `kernel_sim/resource_hooks.py`

**Purpose:** Functions called by `tool_base.py` after every tool execution. Each hook knows how a given tool type affects the resource state and mutates it accordingly.

**Hook functions:**

`on_write_file(path: str, content: str, result: ToolResult)`
- Adds file entry to `tracked_files`
- Adds `ceil(len(content.encode()) / 1024)` MB to `used_ram_mb` for 3 seconds (write buffer simulation), then releases

`on_read_file(path: str, result: ToolResult)`
- Adds `ceil(file_size / 1024)` MB to `used_ram_mb` for 5 seconds, then releases

`on_search_directory(path: str, query: str, result: ToolResult)`
- Small RAM bump proportional to number of files scanned
- Small CPU bump (5–10%) for 2 seconds, then releases

`on_start_process(cmd: str, result: ToolResult)`
- Adds 1 to `active_threads`
- Bumps `cpu_usage_percent` by 15–25% (randomized within range) for the duration of the process
- Bumps `used_ram_mb` by 30–80 MB (randomized)
- When the process exits, reverses these changes

`on_kill_process(pid: int, result: ToolResult)`
- Removes thread, CPU, and RAM contributions of the killed process
- Updates `cpu_per_core` to redistribute load evenly

`on_llm_call(agent_name: str, tokens_used: int)`
- Not called by a tool — called by the agents directly
- Bumps `used_ram_mb` by a small amount representing the model context
- Used to show that "thinking" also has a resource cost

All hooks use `threading.Timer` to schedule the reversal of temporary bumps so resource values drop naturally rather than snapping back.

---

### `kernel_sim/scheduler_sim.py`

**Purpose:** Runs as a background daemon thread. Simulates an OS round-robin task scheduler by cycling through the active process table and updating `context_switches_per_sec`. Gives the dashboard's scheduler queue panel something live to display.

**How it works:**
- Every 1 second, reads `resource_state.process_table`
- Builds a round-robin queue from process names
- Writes the current queue order back to `resource_state.scheduler_queue`
- Calculates `context_switches_per_sec` = number of processes × switches_per_process_per_sec (a formula based on active thread count)
- Updates `resource_state.cpu_per_core` to simulate load distribution: processes are round-robined across cores, each core's usage is recomputed

This runs in a `threading.Thread` with `daemon=True` so it exits cleanly when the main process exits.

---

## `/dashboard` — System Monitor Web UI

The visual face of OSSARTH. A browser-based dashboard that shows all simulated kernel metrics in real time, powered by FastAPI and Server-Sent Events.

```
dashboard/
├── server.py
├── static/
│   ├── index.html
│   ├── style.css
│   └── dashboard.js
└── README.md
```

### `dashboard/server.py`

**Purpose:** FastAPI backend that serves the static dashboard and streams live metrics.

**Endpoints:**

`GET /`
- Serves `static/index.html`

`GET /metrics`
- Server-Sent Events endpoint
- Streams `resource_state.to_dict()` as JSON every second
- Format: `data: <json>\n\n`
- Client reconnects automatically if connection drops (EventSource handles this)

`GET /history?seconds=60`
- Returns a list of the last N seconds of resource snapshots as a JSON array
- Used by the dashboard to draw sparkline graphs on initial load
- Snapshots are stored in a rolling in-memory deque of max length 300

`POST /command`
- Body: `{ "input": "natural language command" }`
- Passes input through the full MAS pipeline (Intent → Orchestrator → tool execution)
- Returns: `{ "intent": {...}, "graph": [...], "results": [...], "duration_ms": float }`
- Allows the dashboard's own input box to send commands without using the terminal

`GET /history/commands`
- Returns the last 20 command log entries from `context_manager`
- Used to populate the Command Log panel on page load

---

### `dashboard/static/index.html`

**Purpose:** The single-page dashboard UI. All layout is here. No framework — pure semantic HTML with CSS classes.

**Layout (dark theme, grid-based):**

```
┌─────────────────────────────────────────────┐
│  OSSARTH SYSTEM MONITOR          uptime      │
├──────────┬──────────┬──────────┬────────────┤
│ CPU      │ RAM      │ GPU VRAM │ Threads    │
│ (donut)  │ (bar)    │ (bar)    │ (counter)  │
├──────────┴──────────┴──────────┴────────────┤
│ CPU per core (8 mini bars)                  │
├─────────────────────┬───────────────────────┤
│ Process Table       │ Scheduler Queue       │
│ PID Name CPU% Mem   │ round-robin list      │
│ ...                 │ context switches/sec  │
├─────────────────────┴───────────────────────┤
│ Command Input                               │
│ [___________________________] [RUN]         │
├─────────────────────────────────────────────┤
│ Command Log                                 │
│ [timestamp] intent → tools called → result  │
│ ...                                         │
└─────────────────────────────────────────────┘
```

All panels update live. No page refresh needed.

---

### `dashboard/static/dashboard.js`

**Purpose:** All client-side logic. Connects to the SSE endpoint, receives metric updates, and renders them to the DOM.

**Responsibilities:**

SSE connection:
- Creates an `EventSource('/metrics')` on page load
- Parses each event's JSON data
- Calls the appropriate update function for each panel

Update functions:
- `updateCpuGauge(percent)` — animates the donut chart to the new CPU%
- `updateRamBar(used, total)` — updates the bar width and the `X MB / Y MB` label
- `updateGpuBar(used, total)` — same as RAM
- `updateThreadCounter(count)` — updates the big number; shows green/red delta indicator if it changed
- `updateCoreGrid(per_core_list)` — updates all 8 mini bars
- `updateProcessTable(process_table)` — diffs the new table against the DOM to add/remove rows without flickering; new rows flash green briefly; removed rows flash red before disappearing
- `updateSchedulerQueue(queue, switches_per_sec)` — updates the scrolling list and the counter
- `appendCommandLog(entry)` — adds a new row to the command log panel; does not re-render existing rows

Command input:
- Sends `POST /command` with the input value on button click or Enter key
- While waiting, shows a spinner in the input field
- On response, appends to the command log

Sparklines:
- On page load, fetches `/history?seconds=60`
- Renders a tiny Chart.js line chart inside each gauge panel showing the last 60 seconds
- Updates the sparkline data on each SSE event

---

### `dashboard/README.md`

**Purpose:** Standalone instructions for the dashboard component, written so that someone can run just the dashboard independently of the full daemon (for UI development purposes).

**Must cover:**
- How to start the FastAPI server alone: `uvicorn dashboard.server:app --reload`
- How to fake live data for UI development: `python dashboard/fake_metrics.py` which pushes random-walk values to `resource_state` every second without running the MAS
- The full list of SSE data fields and their types
- How to add a new panel to the dashboard

---

## `/os_customization` — Boot Experience

Everything needed to make OSSARTH feel like a real OS interface rather than a script you ran.

```
os_customization/
├── boot_message.txt
├── launch.sh
└── systemd/
    └── ossarth.service
```

### `os_customization/boot_message.txt`

**Purpose:** ASCII art boot screen printed to the terminal when the daemon starts. Sets the tone for the demo.

Must contain:
- Large ASCII art of "OSSARTH"
- Version string
- A short tagline ("Intelligence as the Operating System")
- A brief hardware summary line (reads from `resource_state` to print: "8-core CPU | 8192 MB RAM | 4096 MB VRAM")
- "Daemon active. Dashboard at http://localhost:8000"
- "Awaiting intent..."

---

### `os_customization/launch.sh`

**Purpose:** Single script to start everything. Should work from the repo root with no arguments.

**What it does in order:**
1. Activates the Python virtual environment (`source venv/bin/activate`)
2. Checks that `.env` exists; if not, prints an error and exits
3. Starts `uvicorn dashboard.server:app --host 0.0.0.0 --port 8000` as a background process, redirects its stdout/stderr to `logs/dashboard.log`
4. Waits 2 seconds for the server to be ready
5. Opens the browser to `http://localhost:8000` if a display is available (uses `xdg-open` on Linux)
6. Runs `python mas_core/agent_runner.py` in the foreground (this is the REPL the user interacts with)
7. On exit (Ctrl+C), kills the background uvicorn process

---

### `os_customization/systemd/ossarth.service`

**Purpose:** Optional systemd unit file so OSSARTH can be configured to start on boot in a real VM.

**What it defines:**
- `ExecStart` points to `launch.sh`
- `WorkingDirectory` points to the repo root
- `Restart=on-failure`
- `User=ossarth` (a dedicated non-root user)
- `After=network.target`

Not required for the hackathon demo but included to show production intent.

---

## `/benchmarks` — Performance Measurement

```
benchmarks/
├── latency_test.py
├── accuracy_test.py
├── resource_overhead_test.py
├── test_commands.json
└── results/
    ├── latency_results.json
    ├── accuracy_results.json
    └── overhead_results.json
```

### `benchmarks/test_commands.json`

**Purpose:** The canonical set of 10 test commands used across all benchmark scripts. Defined once, used consistently.

**Structure:**
```json
[
  {
    "id": 1,
    "input": "list all running processes",
    "expected_task_type": "query_system",
    "expected_tools": ["list_processes"],
    "complexity": "simple"
  },
  {
    "id": 2,
    "input": "create a python file at /tmp/hello.py that prints Hello OSSARTH and run it",
    "expected_task_type": "create_and_execute",
    "expected_tools": ["write_file", "start_process"],
    "complexity": "medium"
  },
  ...
]
```

Commands span: simple queries, single file ops, multi-step create+execute, search+summarize, process kill, ambiguous inputs.

---

### `benchmarks/latency_test.py`

**Purpose:** Measures end-to-end latency from user input to execution start for each of the 10 test commands.

**Measurements per command:**
- `intent_classification_ms` — time for the Intent Agent Claude API call to return
- `orchestration_ms` — time for the Orchestrator Claude API call to return
- `first_tool_execution_ms` — time from execution graph receipt to the first tool call completing
- `total_ms` — wall time from input string to all tools completing
- Baseline comparison: estimated time to type and execute the equivalent raw bash command (hardcoded estimate, clearly labeled as such)

---

### `benchmarks/accuracy_test.py`

**Purpose:** Measures how accurately the MAS generates the correct execution graph for known inputs.

**Scoring per command:**
- 1 point if `task_type` matches `expected_task_type`
- 1 point if the set of tools used matches `expected_tools` exactly
- 1 point if the tools are in the correct order
- Maximum 3 points per command, 30 total

Outputs a score and a per-command breakdown of where it failed.

---

### `benchmarks/resource_overhead_test.py`

**Purpose:** Measures how much CPU and RAM the OSSARTH daemon itself consumes, independent of the work it's doing.

**Measurements:**
- Baseline: CPU% and RAM of the Python process while the daemon is running but idle (no commands for 30 seconds)
- Under load: CPU% and RAM during a burst of 5 commands in 60 seconds
- Uses `psutil` to read the daemon's own process stats

---

## `/tests` — Unit and Integration Tests

```
tests/
├── test_intent_agent.py
├── test_orchestrator_agent.py
├── test_filesystem_mcp.py
├── test_process_mcp.py
├── test_resource_state.py
└── test_tool_registry.py
```

Each test file uses `pytest`. Mock the Claude API calls in agent tests using `unittest.mock.patch`. Test the real filesystem tools against `/tmp` only. Test resource state mutations directly.

---

## Root-Level Files

### `.env.example`

```
# LLM Configuration — no paid APIs required
GROQ_API_KEY=your_groq_key_here          # Free at console.groq.com
OSSARTH_LLM_PROVIDER=auto               # auto | ollama | groq
OSSARTH_OLLAMA_MODEL=llama3.1:8b        # Any model from: ollama list
OSSARTH_GROQ_MODEL=llama-3.1-8b-instant # Groq free-tier model

# Runtime Config
OSSARTH_MAX_TOKENS=1000
OSSARTH_VERBOSE=false
OSSARTH_DASHBOARD_PORT=8000
OSSARTH_MAX_EXECUTION_STEPS=10
OSSARTH_PROCESS_TIMEOUT_SECONDS=10
```

### `requirements.txt`

```
# LLM providers (no paid APIs — local + free tier only)
ollama>=0.2.0
groq>=0.9.0

# Web server
fastapi>=0.111.0
uvicorn[standard]>=0.29.0

# Core
python-dotenv>=1.0.0
pydantic>=2.7.0
psutil>=5.9.0
```

### `README.md` (Root — For Judges)

Must cover in under 2 minutes of reading:
1. What OSSARTH is (one paragraph)
2. The architecture diagram (ASCII)
3. Setup: 4 commands to get running
4. Demo commands to try
5. What the dashboard shows
6. Benchmark results summary (filled in on Day 3)
7. Honest note on scope: what is simulated and why, and what the production path looks like
