"""
OSSARTH — mas_core/llm_client.py

Unified LLM client abstraction.
- Primary: Ollama (local, free, offline-capable)
- Fallback: Groq API (free tier, fast cloud inference)

The rest of the codebase calls llm_client.complete() and never
interacts with either SDK directly. Switching models or providers
only requires changing .env variables.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────

LLM_PROVIDER: str = os.getenv("OSSARTH_LLM_PROVIDER", "auto").lower()
OLLAMA_MODEL: str = os.getenv("OSSARTH_OLLAMA_MODEL", "llama3.1:8b")
GROQ_MODEL: str = os.getenv("OSSARTH_GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Track which provider is currently active (set on first successful call)
_active_provider: Optional[str] = None


# ─────────────────────────────────────────────────────────
# Provider implementations
# ─────────────────────────────────────────────────────────

def _ollama_complete(messages: list[dict], max_tokens: int, temperature: float) -> str:
    """
    Call Ollama local inference.
    messages: list of {"role": "system"|"user"|"assistant", "content": str}
    Returns the model's text response.
    """
    try:
        import ollama  # type: ignore
    except ImportError:
        raise RuntimeError(
            "ollama Python package not installed. Run: pip install ollama"
        )

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=messages,
        options={
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    )
    # ollama.chat returns an object with message.content
    return response["message"]["content"].strip()


def _groq_complete(messages: list[dict], max_tokens: int, temperature: float) -> str:
    """
    Call Groq cloud inference (free tier).
    messages: list of {"role": "system"|"user"|"assistant", "content": str}
    Returns the model's text response.
    """
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY not set in .env. Either set the key or ensure Ollama is running."
        )

    try:
        from groq import Groq  # type: ignore
    except ImportError:
        raise RuntimeError(
            "groq Python package not installed. Run: pip install groq"
        )

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,  # type: ignore
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


# ─────────────────────────────────────────────────────────
# Provider availability check
# ─────────────────────────────────────────────────────────

def _is_ollama_available() -> bool:
    """Ping Ollama to check if it's running."""
    try:
        import ollama  # type: ignore
        # List models — if this succeeds, Ollama is up
        ollama.list()
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────
# Public interface
# ─────────────────────────────────────────────────────────

def complete(
    messages: list[dict],
    max_tokens: int = 512,
    temperature: float = 0.0,
    verbose: bool = False,
) -> str:
    """
    Send messages to the active LLM provider and return the text response.

    Args:
        messages:    Chat history in OpenAI format:
                     [{"role": "system"|"user"|"assistant", "content": str}]
        max_tokens:  Maximum tokens to generate.
        temperature: Sampling temperature (0.0 = deterministic).
        verbose:     If True, print which provider is being used.

    Returns:
        The model's response text.

    Raises:
        RuntimeError: If all providers fail.
    """
    global _active_provider

    t0 = time.perf_counter()

    # Determine provider order based on config
    if LLM_PROVIDER == "ollama":
        providers = ["ollama"]
    elif LLM_PROVIDER == "groq":
        providers = ["groq"]
    else:
        # auto: Ollama first, Groq fallback
        providers = ["ollama", "groq"]

    last_error: Optional[Exception] = None

    for provider in providers:
        try:
            if provider == "ollama":
                if verbose:
                    print(f"  [LLM] Using Ollama ({OLLAMA_MODEL})")
                result = _ollama_complete(messages, max_tokens, temperature)
            else:
                if verbose:
                    print(f"  [LLM] Using Groq ({GROQ_MODEL})")
                result = _groq_complete(messages, max_tokens, temperature)

            _active_provider = provider
            elapsed_ms = (time.perf_counter() - t0) * 1000

            if verbose:
                print(f"  [LLM] Response in {elapsed_ms:.0f}ms ({len(result)} chars)")

            return result

        except Exception as e:
            last_error = e
            if verbose:
                print(f"  [LLM] {provider} failed: {e}")
            if LLM_PROVIDER == "auto" and provider == "ollama":
                print(f"  [LLM] Ollama unavailable, falling back to Groq...")
            continue

    raise RuntimeError(
        f"All LLM providers failed. Last error: {last_error}\n"
        f"- Ensure Ollama is running: `ollama serve`\n"
        f"- Or set GROQ_API_KEY in .env for cloud fallback."
    )


def get_active_provider() -> Optional[str]:
    """Return which provider was used in the last successful call."""
    return _active_provider


def get_model_name() -> str:
    """Return the model name for the current provider config."""
    if LLM_PROVIDER == "groq":
        return GROQ_MODEL
    if LLM_PROVIDER == "ollama":
        return OLLAMA_MODEL
    # auto: prefer ollama
    return OLLAMA_MODEL


def check_providers() -> dict:
    """
    Check availability of all configured providers.
    Returns a dict of provider -> status for startup diagnostics.
    """
    status = {}

    # Check Ollama
    status["ollama"] = {
        "available": _is_ollama_available(),
        "model": OLLAMA_MODEL,
        "host": OLLAMA_HOST,
    }

    # Check Groq
    status["groq"] = {
        "available": bool(GROQ_API_KEY),
        "model": GROQ_MODEL,
        "key_set": bool(GROQ_API_KEY),
    }

    return status
