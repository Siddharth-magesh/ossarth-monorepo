# OSSARTH — System Architecture

This document describes the complete technical architecture of OSSARTH. Every layer, every data flow, every boundary between components is defined here. When building, if something is ambiguous, this document is the authority.

---

## Guiding Principles

**1. Separation of concerns is absolute.**
The MAS core only thinks. The MCP tools only act. The kernel sim only tracks state. The dashboard only reads and displays. No layer reaches into another layer's domain. An MCP tool never calls a Claude API. An agent never writes a file directly.

**2. Every boundary is typed.**
Data crossing from one layer to another must conform to a Pydantic schema defined in `mas_core/schemas.py`. No raw dicts passed between major components. If you're passing a dict, wrap it in a schema first.

**3. The resource state is the ground truth.**
`kernel_sim/resource_state.py` holds a singleton. Every component that needs to know the current system state reads from it. No component maintains its own copy of resource values. There is one lock, one state, one version of reality.

**4. The daemon is stateless per command but stateful across commands.**
Each command runs independently through the full MAS pipeline. But `context_manager.py` maintains rolling history so the system can handle references to prior outputs. This is explicit context injection, not LLM memory.

**5. The demo must never crash.**
Every tool call is wrapped. Every LLM response is validated. Every subprocess has a timeout. Every SSE stream has auto-reconnect. The demo failing live is worse than a feature not working at all.

---

## Full System Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            USER INTERFACE                               │
│                                                                         │
│   Terminal REPL                         Dashboard (localhost:8000)      │
│   agent_runner.py                       dashboard/static/index.html     │
│   ┌──────────────┐                      ┌───────────────────────────┐  │
│   │ OSSARTH >    │                      │ CPU ████░  RAM ███░  GPU  │  │
│   │ type intent  │                      │ Process Table             │  │
│   │              │◄──── POST /command   │ Command Log               │  │
│   └──────┬───────┘                      └───────────┬───────────────┘  │
│          │ raw string                               │ EventSource       │
└──────────┼───────────────────────────────────────── │ ─────────────────┘
           │                                          │
           ▼                                          │ SSE stream (1/sec)
┌──────────────────────────────────┐                  │
│         MAS CORE                 │                  │
│                                  │         ┌────────┴──────────┐
│  ┌─────────────────────────┐     │         │  Dashboard Server  │
│  │     Intent Agent        │     │         │  dashboard/        │
│  │  Claude API call #1     │     │         │  server.py         │
│  │  raw string → JSON      │     │         │                    │
│  └────────────┬────────────┘     │         │  GET  /            │
│               │ IntentSchema     │         │  GET  /metrics     │
│               ▼                  │         │  GET  /history     │
│  ┌─────────────────────────┐     │         │  POST /command     │
│  │   Orchestrator Agent    │     │         └────────┬──────────┘
│  │  Claude API call #2     │     │                  │
│  │  intent → graph         │     │                  │ reads
│  └────────────┬────────────┘     │                  │
│               │ ExecutionGraph   │                  ▼
│               ▼                  │    ┌─────────────────────────────┐
│  ┌─────────────────────────┐     │    │    KERNEL SIM               │
│  │    Agent Runner         ├─────┼───►│                             │
│  │  steps → tool dispatch  │     │    │  resource_state.py          │
│  └────────────┬────────────┘     │    │  KernelResourceState        │
│               │                  │    │  (singleton, thread-safe)   │
└───────────────┼──────────────────┘    │                             │
                │                       │  scheduler_sim.py           │
                │ tool_name + args       │  (background thread)        │
                ▼                       │                             │
┌──────────────────────────────────┐    │  resource_hooks.py          │
│         MCP TOOL LAYER           │    │  (called after every tool)  │
│                                  │    └─────────────────────────────┘
│  tool_registry.py                │                  ▲
│  ┌───────────────────────────┐   │                  │ mutate state
│  │ filesystem_mcp.py         ├───┼──────────────────┘
│  │  read_file                │   │
│  │  write_file               │   │
│  │  search_directory         │   │
│  │  list_directory           │   │
│  │  delete_file              │   │
│  └───────────────────────────┘   │
│  ┌───────────────────────────┐   │
│  │ process_mcp.py            │   │ ← real subprocess.Popen calls
│  │  list_processes           │   │
│  │  start_process            │   │
│  │  kill_process             │   │
│  └───────────────────────────┘   │
│  ┌───────────────────────────┐   │
│  │ network_mcp.py            │   │
│  │  get_interfaces           │   │
│  │  check_port               │   │
│  └───────────────────────────┘   │
└──────────────────────────────────┘
                │
                │ real I/O
                ▼
┌──────────────────────────────────┐
│          HOST FILESYSTEM         │
│          HOST PROCESSES          │
│          (Linux, real)           │
└──────────────────────────────────┘
```

---

## Layer 1 — User Interface

### Terminal REPL (`mas_core/agent_runner.py`)

The terminal is the primary interface. It is a blocking stdin loop — the daemon reads one line at a time, processes it completely, prints results, then reads the next line.

**Concurrency model:** The REPL runs in the main thread. The dashboard server runs in a background subprocess (not a thread) started by `launch.sh`. The scheduler sim runs in a daemon thread. Resource state reads/writes use a `threading.Lock`. No asyncio in the MAS core — it's synchronous Python with Claude API blocking calls. FastAPI handles async separately in its own process.

**Why subprocess for the dashboard, not a thread?**
FastAPI with uvicorn uses its own event loop. Running uvicorn inside a thread in the same process as synchronous blocking code is fragile. Starting it as a separate process via `launch.sh` is cleaner and isolates crashes.

**Input preprocessing:**
Before passing raw input to the Intent Agent, `agent_runner.py` applies these transformations:
- Strip leading/trailing whitespace
- Normalize multiple spaces to single space
- If input starts with `!`, treat as a raw bash passthrough (bypass MAS entirely, run directly in subprocess)
- If input is empty, re-prompt without calling the API
- If input is `exit` or `quit`, print goodbye and clean up

### Dashboard (`dashboard/`)

Runs in a separate process. Communicates with the MAS exclusively through the shared `resource_state` singleton (same Python process in production; in the separate process model, `resource_state` is read by `server.py` which imports it directly).

**Important:** In the hackathon build, `dashboard/server.py` and `mas_core/agent_runner.py` are started by `launch.sh` as separate processes. This means they do not share memory. The solution: `server.py` imports `kernel_sim.resource_state` and reads the singleton, while `agent_runner.py` also imports and mutates it. Since they're separate processes, they don't share the same singleton.

**Resolution for the hackathon build:** Use a lightweight file-based IPC. `resource_state.py` provides a `flush_to_file()` method that writes the current state to `/tmp/ossarth_state.json` after every mutation. `server.py` reads this file every second for its SSE stream. Simple, no sockets, no message queue, works reliably.

For the post-hackathon version: replace with a proper shared memory bus (Redis, or Python's `multiprocessing.Manager`).

---

## Layer 2 — MAS Core

### Data Flow: Intent Agent

```
raw_input: str
    │
    ▼
build prompt:
    system = INTENT_SYSTEM_PROMPT (from prompts.py)
    user   = raw_input
    │
    ▼
llm_client.complete(messages, max_tokens=256, temperature=0.0)
    │
    ├── provider: Ollama (local) — tried first
    │       model: OSSARTH_OLLAMA_MODEL (default: llama3.1:8b)
    │
    └── fallback: Groq API — used if Ollama unavailable/errors
            model: OSSARTH_GROQ_MODEL (default: llama-3.1-8b-instant)
    │
    ▼
response text  (expected: raw JSON string)
    │
    ├── try: json.loads() → pydantic IntentSchema(**data)
    │       │
    │       └── success → return IntentSchema
    │
    └── except (JSONDecodeError | ValidationError):
            │
            ▼
        error correction round:
            user = ERROR_CORRECTION_PROMPT.format(bad_output=response_text)
            llm_client.complete() — call #2
            │
            ├── success → return IntentSchema
            └── failure → return IntentSchema(task_type="unknown", ...)
```

**Temperature is always 0.0 for classification tasks.** We want the same input to always produce the same classification. Creativity is not wanted here.

**Token budget:** Intent Agent responses are always small JSON objects. 256 max tokens is generous. If the model exceeds this, the prompt is leaking and needs fixing.

**Note on local models:** Open-source models at temperature 0.0 are not as deterministic as commercial APIs — minor variation is acceptable. If a model repeatedly fails JSON output, switch to a larger model via `.env` config.

---

### Data Flow: Orchestrator Agent

```
intent: IntentSchema
    │
    ▼
build prompt:
    system = ORCHESTRATOR_SYSTEM_PROMPT
             + "\n\nAVAILABLE TOOLS:\n"
             + tool_registry.get_tool_catalog_string()
    user   = json.dumps(intent.model_dump())
    │
    ▼
llm_client.complete(messages, max_tokens=1000, temperature=0.0)
    │
    ├── provider: Ollama (local, preferred)
    └── fallback: Groq API
    │
    ▼
response.content[0].text  (expected: JSON array)
    │
    ├── parse → list[ExecutionStep]
    ├── validate: all tool names exist in tool_registry
    ├── validate: step numbers are sequential starting from 1
    ├── validate: step count ≤ OSSARTH_MAX_EXECUTION_STEPS
    │
    ├── valid → return ExecutionGraph
    │
    └── invalid → error correction → retry once → on failure return
                  ExecutionGraph with single step:
                  { tool: "error", args: { message: "Planning failed" } }
```

**Why inject the tool catalog at runtime?**
If tools are added or removed, the prompt stays current automatically. The Orchestrator can never hallucinate a tool name because the only tool names it sees are the ones that actually exist in the registry.

---

### Context Injection

Before every Intent Agent call, `agent_runner.py` checks `context_manager.get_recent_context()`. If the recent context is non-empty and the new input contains reference words ("that file", "it", "the same", "again", "the result"), the context is prepended to the user message:

```
[RECENT CONTEXT]
Command 1: "write hello.py" → wrote /tmp/hello.py
Command 2: "run it" → executed python /tmp/hello.py

[CURRENT INPUT]
run it again
```

This gives the Intent Agent enough information to resolve "it" to `/tmp/hello.py` and produce a correct `start_process` intent.

---

### Execution: Agent Runner Dispatch Loop

```
for step in execution_graph:
    # 1. resolve references
    args = resolve_references(step.args, previous_results)

    # 2. look up tool
    tool_fn = tool_registry.get(step.tool)
    if tool_fn is None:
        result = ToolResult(success=False, error=f"Tool '{step.tool}' not found")
        continue

    # 3. call tool (wrapped by @mcp_tool decorator)
    result = tool_fn(**args)

    # 4. store result
    previous_results[step.step] = result

    # 5. display to user
    print_step_result(step, result)

# 6. log completed command
context_manager.add(CommandLogEntry(...))

# 7. flush state for dashboard
resource_state.flush_to_file()
```

**Reference resolution** (`resolve_references`):
Scans all arg values for the pattern `$step_N_output`. Replaces with `previous_results[N].output`. If the referenced step failed, substitutes an empty string and logs a warning.

---

## Layer 3 — MCP Tool Layer

### Tool Execution Contract

Every tool function must satisfy this contract:

1. **Input:** keyword arguments only, all typed, all matching the schema in `tool_registry`
2. **Output:** any JSON-serializable value (string, dict, list, number)
3. **Errors:** never raise. Catch all exceptions internally and return a value that the `@mcp_tool` decorator wraps into a `ToolResult(success=False, error=...)`
4. **Side effects:** real filesystem and subprocess side effects are allowed and expected. Resource state mutation is handled by the decorator, not the function itself.
5. **Timeout:** any tool that might block (subprocess, network) must have an explicit timeout parameter with a sensible default

### Tool Catalog (Canonical List)

This is the exact list of tools the Orchestrator knows about. Any tool not on this list does not exist from the Orchestrator's perspective.

```
FILESYSTEM TOOLS
  read_file(path: str) → str
  write_file(path: str, content: str) → str
  append_file(path: str, content: str) → str
  delete_file(path: str) → bool
  search_directory(path: str, query: str, file_extension?: str) → list[dict]
  list_directory(path: str) → list[dict]
  get_file_info(path: str) → dict

PROCESS TOOLS
  list_processes() → list[dict]
  start_process(cmd: str, name?: str, timeout_seconds?: int) → dict
  kill_process(pid: int) → bool
  get_process_info(pid: int) → dict

NETWORK TOOLS
  get_network_interfaces() → list[dict]
  check_port(host: str, port: int) → dict
  get_hostname() → str

SYSTEM TOOLS
  get_resource_snapshot() → dict   ← returns resource_state.to_dict()
  get_uptime() → float
  get_command_history(n?: int) → list[dict]
```

`get_resource_snapshot`, `get_uptime`, and `get_command_history` are lightweight read-only tools that let the Orchestrator answer questions like "how much RAM is being used?" or "what did I run earlier?" without needing special-case logic.

---

## Layer 4 — Kernel Simulation

### State Lifecycle

```
Startup
  └── resource_state singleton created with baseline values
  └── scheduler_sim thread starts
  └── uptime timer starts

Per tool call
  └── tool executes (real I/O)
  └── @mcp_tool decorator calls resource_hooks.on_tool_call(...)
  └── hook acquires lock, mutates state
  └── hook schedules reversal timer if the mutation is temporary
  └── lock released
  └── agent_runner calls resource_state.flush_to_file()

Per second (scheduler thread)
  └── reads process_table
  └── recalculates scheduler_queue and context_switches_per_sec
  └── updates cpu_per_core distribution
  └── increments uptime_seconds
  └── flushes to file

Dashboard read (per second, from server.py)
  └── reads /tmp/ossarth_state.json
  └── sends as SSE data event
```

### Resource Value Ranges (for realistic simulation)

| Metric | Baseline (idle) | Under light load | Under heavy load |
|---|---|---|---|
| `cpu_usage_percent` | 6–12% | 25–45% | 60–80% |
| `used_ram_mb` | 1100–1300 | 1800–2500 | 3500–5000 |
| `used_gpu_vram_mb` | 0 | 0 | 0 (GPU unused in demo) |
| `active_threads` | 10–14 | 20–35 | 40–55 |
| `context_switches_per_sec` | 800–1200 | 3000–6000 | 8000–15000 |

These ranges make the dashboard look realistic. Hooks should add values sampled from the appropriate range, not fixed deltas.

### Temporary Mutation Pattern

Temporary bumps (e.g., RAM spikes during file reads) use Python's `threading.Timer`:

```python
def on_read_file(path, result):
    bump = estimate_file_size_mb(path)
    with state_lock:
        resource_state.used_ram_mb += bump
    resource_state.flush_to_file()

    def release():
        with state_lock:
            resource_state.used_ram_mb -= bump
        resource_state.flush_to_file()

    threading.Timer(5.0, release).start()
```

This pattern must be used for all temporary resource effects. Never leave a bump without a scheduled reversal.

---

## Layer 5 — Dashboard Server

### SSE Protocol

The `/metrics` endpoint implements Server-Sent Events:

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

data: {"cpu_usage_percent": 23.4, "used_ram_mb": 1842, ...}\n\n
data: {"cpu_usage_percent": 24.1, "used_ram_mb": 1856, ...}\n\n
...
```

Each event is a complete JSON snapshot of `KernelResourceState`. The client does not need to merge partial updates — it replaces the entire state with each event.

**Keepalive:** Send a comment line `": keepalive\n\n"` every 15 seconds on connections with no state change, to prevent proxy timeout.

**Client reconnect:** The browser's native `EventSource` API reconnects automatically after network interruption. The server does not need to implement any reconnection logic.

### History Ring Buffer

`server.py` maintains a `collections.deque(maxlen=300)` of snapshots. Every second when a new snapshot is generated for SSE, it is also appended here. The `/history` endpoint serializes this deque to JSON. 300 entries × 1 second each = 5 minutes of history for sparklines.

---

## Data Schemas (Complete Reference)

All schemas live in `mas_core/schemas.py`. Pydantic v2.

```python
class EntityItem(BaseModel):
    type: Literal["file", "directory", "command", "language", "query",
                  "process", "port", "action", "unknown"]
    value: str

class IntentSchema(BaseModel):
    task_type: Literal["query_system", "file_operation", "create_and_execute",
                       "search_and_summarize", "process_management", "unknown"]
    priority: Literal["low", "normal", "high"] = "normal"
    entities: list[EntityItem] = []
    requires_clarification: bool = False
    clarification_question: Optional[str] = None
    raw_input: str

class ExecutionStep(BaseModel):
    step: int
    tool: str
    args: dict[str, Any]
    description: str
    expected_output: str

    @validator("step")
    def step_must_be_positive(cls, v):
        assert v >= 1
        return v

class ExecutionGraph(BaseModel):
    steps: list[ExecutionStep]

    @validator("steps")
    def steps_must_be_sequential(cls, v):
        for i, step in enumerate(v):
            assert step.step == i + 1, f"Step {i+1} has number {step.step}"
        return v

class ToolResult(BaseModel):
    step: int
    tool: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float

class CommandLogEntry(BaseModel):
    timestamp: datetime
    raw_input: str
    intent: IntentSchema
    graph: ExecutionGraph
    results: list[ToolResult]
    total_duration_ms: float
    success: bool   # True if all steps succeeded
```

---

## Error Handling Strategy

Every layer has a defined failure mode that does not crash the daemon.

| Layer | Failure | Response |
|---|---|---|
| Intent Agent | Claude API error | Return `IntentSchema(task_type="unknown")`, display "Could not understand intent, try rephrasing" |
| Intent Agent | JSON parse error | Error correction prompt, one retry, then unknown |
| Orchestrator | Claude API error | Return single-step error graph, display "Planning failed" |
| Orchestrator | Invalid tool in graph | Retry once with corrective prompt; if still invalid, skip that step and warn |
| Tool execution | Exception inside tool | `@mcp_tool` catches it, returns `ToolResult(success=False, error=str(e))` |
| Tool execution | Subprocess timeout | Kill child process, return timeout error |
| Resource hooks | Any exception | Silently log, do not crash the tool that triggered it |
| Scheduler thread | Any exception | Log, sleep 1 second, continue loop — never exit |
| Dashboard SSE | File read error | Send last known good state; log the error |
| Dashboard client | Connection drop | EventSource auto-reconnects; no user action needed |

---

## Security Constraints

Since OSSARTH executes arbitrary commands via `start_process`, these rules apply:

**Allowed paths for file operations:**
- `/tmp/ossarth/` — dedicated working directory, created on startup
- `~/ossarth_workspace/` — user's home workspace directory
- Any path explicitly confirmed by the user in the REPL

**Blocked operations (enforced in `filesystem_mcp.py` and `process_mcp.py`):**
- Write to `/etc`, `/sys`, `/proc`, `/boot`, or any path starting with `/sys`
- Execute any command containing `rm -rf /`, `mkfs`, `dd if=`, `:(){:|:&};:`
- Read files outside allowed paths without explicit user confirmation prompt

**Subprocess sandboxing:**
- All `start_process` commands run with the current user's permissions (not root)
- Commands are not passed to a shell (`shell=False` in subprocess calls) to prevent injection
- The command string from the LLM is split using `shlex.split()` before passing to Popen

---

## Configuration Reference

All runtime configuration is loaded from `.env` via `python-dotenv` at startup. No hardcoded values anywhere except the default values in `KernelResourceState`.

| Variable | Default | Effect |
|---|---|---|
| `GROQ_API_KEY` | required for Groq fallback | Authenticates Groq API calls |
| `OSSARTH_LLM_PROVIDER` | `auto` | `auto` \| `ollama` \| `groq` — `auto` tries Ollama first |
| `OSSARTH_OLLAMA_MODEL` | `llama3.1:8b` | Ollama model to use for all LLM calls |
| `OSSARTH_GROQ_MODEL` | `llama-3.1-8b-instant` | Groq model used as fallback |
| `OSSARTH_MAX_TOKENS` | `1000` | Max tokens for Orchestrator responses |
| `OSSARTH_VERBOSE` | `false` | Print full intent JSON and graph in REPL |
| `OSSARTH_DASHBOARD_PORT` | `8000` | FastAPI server port |
| `OSSARTH_MAX_EXECUTION_STEPS` | `10` | Max steps per execution graph |
| `OSSARTH_PROCESS_TIMEOUT` | `10` | Seconds before a subprocess is killed |
| `OSSARTH_STATE_FILE` | `ossarth_state.json` | IPC file for dashboard ↔ daemon (relative to workspace) |
| `OSSARTH_WORKSPACE` | `./ossarth_workspace` | Default working directory for file ops |
| `OSSARTH_HISTORY_FILE` | `~/.ossarth_history` | Persistent command history |

---

## Startup Sequence (Canonical Order)

When `launch.sh` runs `python mas_core/agent_runner.py`:

```
1. load_dotenv()                          # load .env
2. validate_config()                      # check API key present, create workspace dir
3. resource_state = KernelResourceState() # init singleton
4. resource_state.flush_to_file()         # write initial state for dashboard
5. scheduler = SchedulerSim(resource_state)
   scheduler.start()                      # start background thread
6. tool_registry.initialize()             # import and register all MCP tools
7. context_manager.load_history()         # read ~/.ossarth_history
8. print(boot_message)                    # print ASCII boot screen
9. log("Dashboard at http://localhost:{PORT}")
10. REPL loop begins
```

If step 1–6 raises any exception, the daemon prints the error and exits with code 1. After step 7, all errors are caught per-command and never crash the daemon.
