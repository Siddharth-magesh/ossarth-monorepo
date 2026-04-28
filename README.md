# OSSARTH

**Intelligence as the Operating System**

OSSARTH is a User-Space AI Daemon that replaces the traditional OS shell with a natural language interface. You type intent in plain English; a Multi-Agent System classifies it, plans an execution graph, and dispatches tools to carry it out — while a live System Monitor Dashboard shows the OS reacting in real time.

---

## Architecture

```
User Input (natural language)
        │
        ▼
   Intent Agent          ← LLM call: classifies input → structured JSON
        │
        ▼
  Orchestrator Agent     ← LLM call: breaks intent into ordered tool calls
        │
        ▼
   MCP Tool Layer        ← Python functions: filesystem, process, network ops
        │
        ▼
 Kernel Resource Sim     ← In-memory state: RAM, GPU, threads, process table
        │
        ▼
  Dashboard (Web UI)     ← FastAPI SSE → live gauges, process table, log
```

**LLM:** Ollama (local, free, offline) → Groq (free tier fallback). No paid APIs.

---

## Setup (4 Commands)

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Edit .env: add GROQ_API_KEY, set OSSARTH_OLLAMA_MODEL to your model

# 4. Launch everything
os_customization\launch.bat  # Windows
# ./os_customization/launch.sh  # Linux/Mac
```

**Prerequisites:**
- Python 3.11+
- [Ollama](https://ollama.ai) running locally with at least one model (`ollama pull llama3.1:8b`)
- OR a free [Groq API key](https://console.groq.com) set as `GROQ_API_KEY` in `.env`

---

## Demo Commands to Try

```
OSSARTH > list all running processes
OSSARTH > create a file called hello.txt in ossarth_workspace with the content 'OSSARTH is live'
OSSARTH > write a python script that prints the first 10 prime numbers, save it to ossarth_workspace/primes.py, and run it
OSSARTH > search ossarth_workspace for all .py files and tell me what each one does
OSSARTH > status
OSSARTH > !dir ossarth_workspace     ← raw shell passthrough
```

---

## What the Dashboard Shows

Open **http://localhost:8000** after launch:

| Panel | What it shows |
|---|---|
| CPU Gauge | Donut chart, 0–100%, updates every second |
| RAM Bar | Used MB / Total MB with sparkline |
| GPU VRAM Bar | Used MB / Total MB |
| Threads Counter | Active thread count with delta indicator |
| CPU Per Core | 8 mini vertical bars |
| Process Table | Live table: PID, name, CPU%, memory, status |
| Scheduler Queue | Round-robin process queue + context switches/sec |
| Command Input | Type natural language commands directly in the browser |
| Command Log | Every command → intent → tools → result |

---

## Project Structure

```
ossarth-monorepo/
├── mas_core/          # MAS brain: intent agent, orchestrator, REPL
│   ├── llm_client.py  # Ollama-first, Groq-fallback unified LLM interface
│   ├── intent_agent.py
│   ├── orchestrator_agent.py
│   ├── agent_runner.py  ← main entry point
│   ├── prompts.py
│   ├── schemas.py
│   └── context_manager.py
├── mcp_tools/         # MCP tool layer: real filesystem + process ops
│   ├── tool_registry.py
│   ├── filesystem_mcp.py
│   ├── process_mcp.py
│   ├── network_mcp.py
│   └── system_mcp.py
├── kernel_sim/        # Simulated kernel resource model
│   ├── resource_state.py
│   ├── resource_hooks.py
│   └── scheduler_sim.py
├── dashboard/         # FastAPI + SSE + Vanilla JS web UI
│   ├── server.py
│   └── static/
│       ├── index.html
│       ├── style.css
│       └── dashboard.js
├── benchmarks/        # Performance measurement scripts
├── tests/             # pytest unit + integration tests
└── os_customization/  # Boot message + launch scripts
```

---

## Scope Note (Honest)

**What is simulated:**
- Kernel resource values (RAM, CPU, threads) — Python in-memory model, not real kernel hooks
- Process table — tracked by our tools, not `/proc` or `ps`
- GPU VRAM — always 0 in the demo; no GPU workloads

**What is real:**
- Filesystem operations — real files written to disk via pathlib
- Process execution — real `subprocess.Popen` calls
- Network queries — real socket calls

**Why simulation?** Real kernel modules require weeks of low-level C development. The architecture (Intent → Orchestrator → MCP → Resource Layer) is identical to what a production system with real kernel hooks would look like. We are proving the concept cleanly.

**Production path:** Replace `kernel_sim/` with real kernel hooks via eBPF or `/proc` reads. Replace Ollama model with a fine-tuned local model. Add decentralized compute layer.

---

## Running Tests

```bash
pytest tests/ -v
```

---

*Built at a hackathon. LLM-powered. No paid APIs.*
