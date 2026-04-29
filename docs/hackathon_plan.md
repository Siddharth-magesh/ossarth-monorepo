# OSSARTH — Hackathon Plan

## What We Are Building

**OSSARTH** is a User-Space AI Daemon that fundamentally reimagines the operating system. Instead of the traditional rigid pipeline (User → Shell → System Calls → Kernel), OSSARTH introduces an **AI Intent Layer** and an **AI Orchestrator**. The user types intent in plain English; a Multi-Agent System (MAS) classifies it, plans an execution graph, and dispatches Model Context Protocol (MCP) tools to carry it out — while a live System Monitor Dashboard shows the OS reacting in real time.

This is not an application on top of an OS. This is the OS interface itself.

### The Shift in Paradigm: Execution Engine + Decision Engine
Traditional OS: Hardcoded policies (CFS scheduling, LRU caching, static syscall sequences).
OSSARTH OS: Learned, adaptive policies. The kernel remains the Execution Engine, but AI becomes the Decision Engine.

---

## Scope Decision (Read This First)

We will **not** touch the Linux kernel. Kernel modules require weeks of low-level C development and specific hardware access. Instead:

- All kernel-level concepts (RAM allocation, GPU VRAM, CPU scheduler threads, process priority) are **simulated via a hardcoded in-memory resource model** written in Python.
- MCP tool calls mutate this simulated state.
- The System Monitor Dashboard reads and displays this state live.

To a judge watching the demo, the AI is visibly controlling system resources. The architecture — Intent Agent → Orchestrator → MCP → Resource Layer — is identical to what a production system with real kernel hooks would look like. We are proving the concept cleanly.

---

## Layered AI-Enhanced Architecture

```
User Input (natural language, GUI events, API calls)
        │
        ▼
   1. AI Intent Layer (Replaces Shell)    ← Translates natural language into a structured intent
        │
        ▼
   2. AI Orchestrator (New Layer)         ← Breaks task into subtasks, assigns agents, builds execution graph
        │
        ▼
   3. MCP Tool Layer (System Interface)   ← Converts AI plans into system calls, validates safety
        │
        ▼
   4. AI Optimization Layer (Theoretical) ← ML Scheduler, Vector/Semantic I/O, Predictive Memory
        │
        ▼
   5. Kernel & Simulation Layer           ← Simulates process tables, memory, scheduler execution
        │
        ▼
   Dashboard (Web UI)                     ← Live visualization of AI-driven OS decisions
```

---

## Phase 1 — Core Execution Pipeline (Implemented)

We have successfully built the base pipeline. The following components are operational:
- **Intent Agent**: Classifies natural language into a JSON intent (Ollama/Groq).
- **Orchestrator Agent**: Generates an ordered execution graph of system tools.
- **MCP Tool Registry**: Provides safe Python wrappers for filesystem and process management.
- **Simulated Kernel State**: Tracks memory, CPU, and processes.
- **Dashboard**: FastAPI/JS UI visualizing the state.

---

## Phase 2 — Advanced Theoretical Innovations (Next Steps)

To truly make OSSARTH an "AI Operating System", we must implement (or theoretically model and simulate) advanced decision-making layers that augment the kernel's responsibilities.

### 1. ML-Based Scheduler (Simulated)
**Current OS**: Uses static algorithms like Round Robin or CFS (Completely Fair Scheduler).
**OSSARTH Vision**: An AI-based scheduler that predicts workload patterns.
- **Implementation**: We will update `scheduler_sim.py` to analyze the process table. Instead of round-robin, it will use an ML heuristic to prioritize latency-sensitive tasks (e.g., UI processes) and deprioritize heavy background jobs.
- **Scenario**: If the Intent Agent dispatches an ML workload, the scheduler dynamically allocates "simulated GPU" resources and pauses background bash scripts.

### 2. Semantic File System & I/O (Vector Storage)
**Current OS**: Hierarchical path-based lookup (e.g., `open("/home/user/notes.txt")`).
**OSSARTH Vision**: Semantic file search using vector embeddings.
- **Implementation**: When files are created via the MCP filesystem tools, we will simulate generating vector embeddings for the content.
- **Scenario**: Instead of exact pathing, the user can say "Find my ML notes from last week." The AI Orchestrator uses a semantic search tool to bypass rigid directory structures, locating the file based on meaning rather than path.

### 3. Predictive Memory Management & Sycall Optimization
**Current OS**: Reactive paging (page faults) and static syscall sequences (open → read → write).
**OSSARTH Vision**: Predictive preloading and parallelization.
- **Implementation (Theoretical)**: The Orchestrator agent acts as a JIT optimizer. When a user asks to process a large file, the Orchestrator graph explicitly pre-fetches data and groups related context switches.
- **Scenario**: We simulate "Cache Hits" in our dashboard metrics rising when the AI correctly anticipates the next required resource for a task.

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

---

## Day 3 — Benchmarks, Proof, and Presentation

**Goal:** Quantified evidence and a polished presentation proving the AI OS model works and is efficient.

### Benchmarking Suite (To Be Executed)

1. **Latency Test (`benchmarks/latency_test.py`)**
   - Measure the overhead of the AI Intent + Orchestrator layers vs raw bash commands.
   - Frame the overhead as the acceptable cost of autonomy and intelligent routing.
2. **Accuracy Test (`benchmarks/accuracy_test.py`)**
   - Score the Orchestrator on generating exact-match execution graphs for complex prompts.
3. **Resource Overhead (`benchmarks/resource_overhead_test.py`)**
   - Track the daemon's CPU/RAM footprint.
4. **Scheduler Efficiency (NEW)**
   - Compare "Time to Completion" of simulated tasks using the standard Round-Robin vs the theoretical ML-Based Scheduler.

### The Pitch Deck Narrative
1. **The Problem**: Rigid syscalls, static scheduling, path-based filesystems.
2. **The Vision**: The OS as an Execution Engine + Decision Engine.
3. **The Solution (OSSARTH)**: Natural language intents, semantic file I/O, ML-driven resource allocation.
4. **Live Demo**: Show the split-screen REPL and Dashboard reacting.
5. **Benchmarks**: Prove that AI orchestration is viable.

---

## Demo Script (Presented to Judges)

Execute these commands in sequence during the live presentation.

```
BOOT
  Run: ./os_customization/launch.bat
  Expected: OSSARTH ASCII boot screen → daemon starts → dashboard opens

COMMAND 1 — System Query
  Input: "show me all running processes"
  Expected: process table returned, dashboard process list refreshes

COMMAND 2 — Intelligent File Creation
  Input: "create a file called hello.txt in ossarth_workspace with the content 'OSSARTH is live'"
  Expected: write_file called → file appears on disk → Semantic vector indexing simulated

COMMAND 3 — Multi-Step Create + Execute + Schedule
  Input: "write a python script that prints primes, save it to ossarth_workspace/primes.py, and run it"
  Expected:
    - Orchestrator generates: [write_file, start_process]
    - Dashboard: New process appears, ML-Scheduler dynamically boosts its priority, CPU spikes, then completes.

COMMAND 4 — Semantic Search (The Future of I/O)
  Input: "search ossarth_workspace for anything related to python scripts"
  Expected:
    - Orchestrator utilizes the search tools to retrieve the file not by exact name, but by content meaning.

CLOSE
  Point at the dashboard: "Every gauge you see moved because the AI issued a command.
  This is what it looks like when intelligence becomes the operating system."
```

---

## End-of-Hackathon Checklist

- [x] Full end-to-end loop works for core commands (Phase 1)
- [x] Dashboard displays gauges with live updates
- [ ] Implement theoretical simulation hooks for ML Scheduler and Semantic I/O
- [ ] Benchmark results files generated with real data
- [ ] Root `README.md` updated with the layered AI OS architecture
- [ ] Backup demo video recorded
