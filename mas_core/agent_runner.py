"""
OSSARTH — mas_core/agent_runner.py

Main entry point and REPL loop.
Orchestrates the full pipeline: user input → intent → graph → tools → output.

Startup sequence:
  1. load_dotenv()
  2. validate_config()
  3. Init resource_state singleton
  4. flush initial state for dashboard
  5. Start scheduler sim background thread
  6. Init tool registry
  7. Load context history
  8. Print boot message
  9. REPL loop begins

CLI flags:
  --verbose    Print full intent JSON and execution graph
  --dry-run    Plan but do not execute tools
  --no-dashboard   Skip dashboard startup message
"""

from __future__ import annotations

import json
import os
import sys

# Force UTF-8 encoding for Windows console (fixes cp1252 errors for ✓ and ✗ characters)
for stream in (sys.stdout, sys.stderr):
    if stream.encoding.lower() != "utf-8" and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────
# Module-level singleton (accessed by system_mcp.get_command_history)
# ─────────────────────────────────────────────────────────
_context_manager = None


# ─────────────────────────────────────────────────────────
# ANSI colour helpers
# ─────────────────────────────────────────────────────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    CYAN    = "\033[36m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    MAGENTA = "\033[35m"
    BLUE    = "\033[34m"

    @staticmethod
    def supports_color() -> bool:
        return sys.stdout.isatty() and os.name != "nt" or os.getenv("FORCE_COLOR")


def _c(text: str, color: str) -> str:
    if C.supports_color():
        return f"{color}{text}{C.RESET}"
    return text


# ─────────────────────────────────────────────────────────
# Config validation
# ─────────────────────────────────────────────────────────

def validate_config() -> None:
    """Check that required config is present. Exits with code 1 on failure."""
    provider = os.getenv("OSSARTH_LLM_PROVIDER", "auto").lower()
    groq_key = os.getenv("GROQ_API_KEY", "")

    if provider == "groq" and not groq_key:
        print(_c("ERROR: OSSARTH_LLM_PROVIDER=groq but GROQ_API_KEY is not set.", C.RED))
        print("Set GROQ_API_KEY in your .env file or use OSSARTH_LLM_PROVIDER=ollama")
        sys.exit(1)

    # Resolve workspace relative to the repo root (where agent_runner.py lives, two dirs up)
    _repo_root = Path(__file__).parent.parent.resolve()
    _raw_ws = os.getenv("OSSARTH_WORKSPACE", "./ossarth_workspace")
    if Path(_raw_ws).is_absolute():
        workspace_path = str(Path(_raw_ws).resolve())
    else:
        workspace_path = str((_repo_root / _raw_ws).resolve())
    os.environ["OSSARTH_WORKSPACE"] = workspace_path
    Path(workspace_path).mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────
# Boot message
# ─────────────────────────────────────────────────────────

def print_boot_message() -> None:
    """Print the ASCII boot screen from boot_message.txt."""
    boot_file = Path(__file__).parent.parent / "os_customization" / "boot_message.txt"
    if boot_file.exists():
        print(boot_file.read_text(encoding="utf-8"))
    else:
        print("\n" + "="*60)
        print("  OSSARTH — Intelligence as the Operating System")
        print("="*60 + "\n")


# ─────────────────────────────────────────────────────────
# Reference resolution
# ─────────────────────────────────────────────────────────

def resolve_references(args: dict, previous_results: dict) -> dict:
    """
    Replace $step_N_output placeholders with actual results from step N.
    e.g., {"path": "$step_1_output"} → {"path": "/tmp/hello.py"}
    """
    resolved = {}
    for key, value in args.items():
        if isinstance(value, str) and value.startswith("$step_"):
            parts = value.split("_")
            try:
                step_num = int(parts[1])
                result = previous_results.get(step_num)
                out = result.output if result else ""
                
                # Smart extraction for search/list tools that return list of dicts
                if isinstance(out, list) and out and isinstance(out[0], dict):
                    if "path" in out[0]:
                        out = out[0]["path"]
                    elif "name" in out[0]:
                        out = out[0]["name"]
                
                resolved[key] = str(out) if out else ""
            except (IndexError, ValueError):
                resolved[key] = value
        else:
            resolved[key] = value
    return resolved


# ─────────────────────────────────────────────────────────
# Step result display
# ─────────────────────────────────────────────────────────

def print_step_result(step, result, verbose: bool = False) -> None:
    """Display a tool execution result in the REPL."""
    # Detect whether the terminal supports Unicode; fall back to ASCII symbols
    _utf8 = getattr(sys.stdout, "encoding", "utf-8").lower() == "utf-8"
    ok_str   = "\u2713" if _utf8 else "[OK]"
    fail_str = "\u2717" if _utf8 else "[FAIL]"
    icon = _c(ok_str, C.GREEN) if result.success else _c(fail_str, C.RED)
    tool_name = _c(result.tool, C.CYAN)
    ms = _c(f"{result.duration_ms:.0f}ms", C.DIM)

    print(f"\n  {icon} {tool_name}  {ms}")

    if result.success and result.output is not None:
        output_str = result.output
        if isinstance(output_str, (dict, list)):
            output_str = json.dumps(output_str, indent=4, ensure_ascii=False)
        else:
            output_str = str(output_str)
        # Truncate very long outputs
        if len(output_str) > 2000:
            output_str = output_str[:2000] + "\n  ... (truncated)"
        # Indent output lines
        for line in output_str.splitlines():
            print(f"    {line}")

    if not result.success and result.error:
        print(f"    {_c('Error:', C.RED)} {result.error}")


# ─────────────────────────────────────────────────────────
# Main dispatch function (also called by dashboard POST /command)
# ─────────────────────────────────────────────────────────

def dispatch_execution_graph(graph, registry, verbose: bool = False, silent: bool = False) -> list:
    """
    Execute all steps in an ExecutionGraph.
    silent=True suppresses all print output (used by dashboard to avoid cp1252 crashes).
    """
    previous_results = {}
    results = []

    for step in graph.steps:
        # Handle error step (planning failure)
        if step.tool == "error":
            from mas_core.schemas import ToolResult
            err_result = ToolResult(
                step=step.step,
                tool="error",
                success=False,
                error=step.args.get("message", "Unknown planning error"),
                duration_ms=0.0,
            )
            results.append(err_result)
            if not silent:
                print_step_result(step, err_result, verbose)
            continue

        # Resolve $step_N_output references
        resolved_args = resolve_references(step.args, previous_results)

        # Dispatch tool
        tool_result = registry.call_tool(step.tool, resolved_args, step=step.step)
        previous_results[step.step] = tool_result
        results.append(tool_result)

        # Only print in REPL, never when called from dashboard
        if not silent:
            print_step_result(step, tool_result, verbose)

    return results


# ─────────────────────────────────────────────────────────
# REPL loop
# ─────────────────────────────────────────────────────────

def run_repl(
    intent_agent,
    orchestrator,
    registry,
    context_manager,
    verbose: bool = False,
    dry_run: bool = False,
) -> None:
    """Main blocking REPL loop."""
    from mas_core.schemas import CommandLogEntry

    prompt = _c("OSSARTH", C.CYAN) + _c(" > ", C.DIM)

    while True:
        # Read input
        try:
            raw_input = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{_c('Goodbye. OSSARTH daemon stopped.', C.DIM)}")
            break

        # ── Special inputs ──
        if not raw_input:
            continue

        if raw_input.lower() in ("exit", "quit", "q"):
            print(_c("Shutting down OSSARTH. Goodbye.", C.DIM))
            break

        if raw_input.startswith("!"):
            # Raw bash passthrough — bypass MAS entirely
            cmd = raw_input[1:].strip()
            print(_c(f"  [passthrough] Running: {cmd}", C.DIM))
            os.system(cmd)
            continue

        if raw_input.lower() == "status":
            from mas_core import llm_client
            state_dict = registry.call_tool("get_resource_snapshot", {}).output or {}
            print(f"  Provider:  {_c(llm_client.get_active_provider() or 'none yet', C.CYAN)}")
            print(f"  CPU:       {state_dict.get('cpu_usage_percent', '?')}%")
            print(f"  RAM:       {state_dict.get('used_ram_mb', '?')} / {state_dict.get('total_ram_mb', '?')} MB")
            print(f"  Commands:  {context_manager.command_count()} this session")
            continue

        if raw_input.lower() == "reset":
            from kernel_sim.resource_state import get_resource_state
            get_resource_state().reset_to_baseline()
            print(_c("  Resource state reset to baseline.", C.GREEN))
            continue

        # ── Main pipeline ──
        t_start = time.perf_counter()

        # Step 1: Classify intent
        print(_c("  Classifying intent...", C.DIM), end="\r")

        # Inject context if input contains reference words
        context_prefix = ""
        if context_manager.has_reference_words(raw_input):
            context_prefix = context_manager.get_recent_context(n=3)

        intent = intent_agent.classify(raw_input, context_prefix=context_prefix)

        if verbose:
            print(f"\n{_c('  Intent:', C.YELLOW)}")
            print(json.dumps(intent.model_dump(), indent=4))

        # Handle clarification
        if intent.requires_clarification:
            question = intent.clarification_question or "Could you clarify your request?"
            print(f"\n  {_c('?', C.YELLOW)} {question}")
            continue

        # Step 2: Plan execution graph
        print(_c("  Planning execution graph...          ", C.DIM), end="\r")
        graph = orchestrator.plan(intent)

        if verbose:
            print(f"\n{_c('  Execution Graph:', C.YELLOW)}")
            for step in graph.steps:
                print(f"    Step {step.step}: {_c(step.tool, C.CYAN)} {step.args}")

        # Show what we're about to do
        if not verbose:
            tool_names = [s.tool for s in graph.steps]
            print(f"\n  {_c('Plan:', C.YELLOW)} {' → '.join(tool_names)}")

        # Step 3: Execute (unless dry-run)
        if dry_run:
            print(_c("  [dry-run] Execution skipped.", C.DIM))
            continue

        results = dispatch_execution_graph(graph, registry, verbose=verbose)

        # Step 4: Record in context manager
        t_end = time.perf_counter()
        total_ms = (t_end - t_start) * 1000

        entry = CommandLogEntry(
            timestamp=datetime.now(timezone.utc),
            raw_input=raw_input,
            intent=intent,
            graph=graph,
            results=results,
            total_duration_ms=round(total_ms, 2),
            success=all(r.success for r in results),
        )
        context_manager.add(entry)

        # Update resource state metadata
        from kernel_sim.resource_state import get_resource_state
        state = get_resource_state()

        def update_meta(s):
            s.last_command_latency_ms = total_ms
            s.command_count += 1

        state.mutate(update_meta)
        state.flush_to_file()

        # Show latency
        success_count = sum(1 for r in results if r.success)
        total_steps = len(results)
        status_color = C.GREEN if entry.success else C.YELLOW
        print(
            f"\n  {_c(f'{success_count}/{total_steps} steps OK', status_color)}"
            f"  {_c(f'{total_ms:.0f}ms', C.DIM)}\n"
        )


# ─────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────

def main() -> None:
    global _context_manager

    # Parse CLI flags
    verbose = "--verbose" in sys.argv or os.getenv("OSSARTH_VERBOSE", "false").lower() == "true"
    dry_run = "--dry-run" in sys.argv
    no_dashboard = "--no-dashboard" in sys.argv

    # 1. Load and validate config
    validate_config()

    # 2. Init resource state singleton
    from kernel_sim.resource_state import get_resource_state
    resource_state = get_resource_state()

    # 3. Write initial state for dashboard
    resource_state.flush_to_file()

    # 4. Start scheduler sim background thread
    from kernel_sim.scheduler_sim import SchedulerSim
    scheduler = SchedulerSim(resource_state)
    scheduler.start()

    # 5. Init tool registry
    from mcp_tools.tool_registry import ToolRegistry
    registry = ToolRegistry()
    registry.initialize()

    # 5a. Seed process table immediately with real OS processes
    try:
        from mcp_tools.process_mcp import list_processes
        list_processes()   # this calls psutil and writes into resource_state
        resource_state.flush_to_file()
    except Exception:
        pass

    # 6. Init context manager
    from mas_core.context_manager import ContextManager
    context_manager = ContextManager()
    context_manager.load_history()
    _context_manager = context_manager  # module-level reference for system_mcp

    # 7. Init agents
    from mas_core.intent_agent import IntentAgent
    from mas_core.orchestrator_agent import OrchestratorAgent
    intent_agent = IntentAgent(verbose=verbose)
    orchestrator = OrchestratorAgent(tool_registry=registry, verbose=verbose)

    # 8. Print boot message
    print_boot_message()

    # 9. Check LLM providers
    from mas_core import llm_client
    provider_status = llm_client.check_providers()
    _utf8 = getattr(sys.stdout, "encoding", "utf-8").lower() == "utf-8"
    _ok  = "\u2713" if _utf8 else "[OK]"
    _no  = "o" if not _utf8 else "\u25cb"
    if provider_status["ollama"]["available"]:
        print(_c(f"  {_ok} Ollama ready ({provider_status['ollama']['model']})", C.GREEN))
    else:
        print(_c(f"  {_no} Ollama not available -- using Groq fallback", C.YELLOW))

    if provider_status["groq"]["key_set"]:
        print(_c(f"  {_ok} Groq ready ({provider_status['groq']['model']})", C.GREEN))
    else:
        print(_c(f"  {_no} Groq key not set", C.DIM))

    dashboard_port = os.getenv("OSSARTH_DASHBOARD_PORT", "8000")
    if not no_dashboard:
        print(_c(f"\n  Dashboard → http://localhost:{dashboard_port}", C.CYAN))

    print(_c("\n  Type a command in natural language. '!cmd' for raw shell. 'exit' to quit.\n", C.DIM))

    # 10. Start REPL
    run_repl(
        intent_agent=intent_agent,
        orchestrator=orchestrator,
        registry=registry,
        context_manager=context_manager,
        verbose=verbose,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    main()
