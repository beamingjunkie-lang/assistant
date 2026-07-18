"""Interactive CLI for the assistant."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from config import Config, DEFAULT_CONFIG_PATH
from assistant import Assistant, __version__

logger = logging.getLogger(__name__)

WELCOME = """
╔══════════════════════════════════════════╗
║          AI Assistant  v1.0              ║
║  Type  /help  for commands               ║
╚══════════════════════════════════════════╝
"""

HELP_TEXT = """
Commands
--------
/help            Show this help
/tools           List available tools
/tools <cat>     List tools in a category
/memory          Show memory statistics
/recall <query>  Search memory
/remember <text> Store a fact in memory
/clear           Clear conversation history
/config          Show current configuration
/exit  /quit     Exit
"""


def run_cli(config: Config | None = None) -> None:
    cfg = config or Config.load()
    cfg.setup_logging()

    assistant = Assistant(cfg)

    print(WELCOME)

    if not cfg.api_key:
        print("⚠️  Warning: No API key configured.")
        print("   Set OPENAI_API_KEY or ASSISTANT_API_KEY environment variable,")
        print("   or add 'api_key' to ~/.assistant/config.json\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Built-in commands
        if user_input.startswith("/"):
            _handle_command(user_input, assistant, cfg)
            continue

        print("Assistant: ", end="", flush=True)
        try:
            response = assistant.chat(user_input)
            print(response)
        except Exception as e:
            logger.exception("Error during chat")
            print(f"[Error] {e}")
        print()


def _handle_command(cmd: str, assistant: Assistant, cfg: Config) -> None:
    parts = cmd.split(None, 1)
    verb = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if verb in ("/exit", "/quit"):
        print("Goodbye!")
        sys.exit(0)

    elif verb == "/help":
        print(HELP_TEXT)

    elif verb == "/tools":
        tools = assistant.available_tools()
        if arg:
            tools = [t for t in tools if arg.lower() in t["category"].lower()]
        for t in tools:
            approval = " [approval required]" if t["requires_approval"] else ""
            print(f"  {t['name']:<35} [{t['category']}]{approval}")
            print(f"    {t['description'][:80]}")
        print(f"\n  Total: {len(tools)} tools")

    elif verb == "/memory":
        stats = assistant.memory_stats()
        print(json.dumps(stats, indent=2))

    elif verb == "/recall":
        if not arg:
            print("Usage: /recall <query>")
            return
        results = assistant.recall(arg)
        if not results:
            print("No matching memories found.")
        for entry in results:
            print(assistant.memory.format_entry(entry))

    elif verb == "/remember":
        if not arg:
            print("Usage: /remember <text>")
            return
        entry_id = assistant.remember(arg)
        print(f"Stored memory: {entry_id}")

    elif verb == "/clear":
        assistant.reset()
        print("Conversation history cleared.")

    elif verb == "/config":
        from dataclasses import asdict
        data = asdict(cfg)
        if data.get("api_key"):
            data["api_key"] = "***"
        print(json.dumps(data, indent=2))

    else:
        print(f"Unknown command: {verb}. Type /help for help.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assistant",
        description="AI Assistant CLI",
    )
    parser.add_argument(
        "--config", "-c",
        metavar="PATH",
        help="Path to config file",
    )
    parser.add_argument(
        "--model", "-m",
        metavar="MODEL",
        help="Override LLM model",
    )
    parser.add_argument(
        "--message", "-M",
        metavar="TEXT",
        help="Send a single message non-interactively and exit",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List available tools and exit",
    )
    parser.add_argument(
        "--no-approval",
        action="store_true",
        help="Disable approval prompts for destructive tools",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Create a default configuration file and exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else Path(
        os.environ.get("ASSISTANT_CONFIG", DEFAULT_CONFIG_PATH)
    )
    if args.init_config:
        if config_path.exists():
            parser.error(f"Configuration already exists: {config_path}")
        Config().save(config_path)
        print(f"Created configuration: {config_path}")
        return

    cfg = Config.load(config_path)
    cfg.setup_logging()

    if args.model:
        cfg.model = args.model
    if args.no_approval:
        cfg.require_approval = False

    assistant = Assistant(cfg)

    if args.list_tools:
        for t in assistant.available_tools():
            print(f"{t['name']:<35} [{t['category']}]")
        sys.exit(0)

    if args.message:
        response = assistant.chat(args.message)
        print(response)
        sys.exit(0)

    run_cli(cfg)


if __name__ == "__main__":
    main()
