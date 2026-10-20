"""NEXUS Conversational AI Interactive Operator CLI.

Provides a terminal-based conversational interface for operators to query
NEXUS telemetry, trends, statistics, and operational incidents.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repository root is on sys.path for direct script execution
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from ground_station.ai.agent import NexusConversationalAgent  # noqa: E402
from ground_station.ai.tools import NexusAITools  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NEXUS Conversational AI Assistant (Read-only Operator Interface)"
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Optional initial query. If omitted, starts an interactive chat session.",
    )
    parser.add_argument(
        "--model",
        default="mistral:7b",
        help="Target Ollama model name (default: mistral:7b)",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama server endpoint (default: http://localhost:11434)",
    )

    args = parser.parse_args()

    tools = NexusAITools()
    agent = NexusConversationalAgent(
        tools=tools,
        model=args.model,
        ollama_url=args.ollama_url,
    )

    ollama_ok = agent.is_ollama_available()
    backend_mode = f"Ollama ({args.model})" if ollama_ok else "Deterministic Rule Router (Ollama offline)"

    # If single query provided via command-line args
    if args.query:
        user_query = " ".join(args.query)
        print(f"\n[Mode: {backend_mode}] Query: {user_query}")
        resp = agent.ask(user_query)
        print(f"\nResponse ({resp.latency_ms:.0f}ms):\n{resp.content}\n")
        return

    # Interactive session
    print("=" * 70)
    print(" NEXUS Ground Station — Read-Only Conversational AI Assistant")
    print(f" Active Backend: {backend_mode}")
    print(" Commands: 'exit', 'quit', or 'help'")
    print("=" * 70)

    history = []
    while True:
        try:
            prompt = input("\nNEXUS > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting NEXUS assistant.")
            break

        if not prompt:
            continue
        if prompt.lower() in ("exit", "quit"):
            print("Session closed.")
            break
        if prompt.lower() == "help":
            print("\nExample queries:")
            print("- What are the latest valid temperature and humidity readings?")
            print("- Has telemetry from esp32_01 become stale?")
            print("- Are there any active incidents right now?")
            print("- Show me the recent LDR light trend.")
            print("- Were there executive task failures in the latest reporting interval?")
            print("- What is the overall system and database status?")
            continue

        resp = agent.ask(prompt, history=history)
        print(f"\nAssistant ({resp.latency_ms:.0f}ms):\n{resp.content}")

        if resp.tool_calls:
            print(f"\n[Tools consulted: {', '.join(tc['name'] for tc in resp.tool_calls)}]")

        # Maintain last 6 turns for conversational context
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": resp.content})
        if len(history) > 12:
            history = history[-12:]


if __name__ == "__main__":
    main()
