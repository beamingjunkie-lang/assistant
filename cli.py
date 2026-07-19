"""Interactive and non-interactive command-line interface for the assistant."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from assistant import Assistant, __version__
from config import Config, DEFAULT_CONFIG_PATH
from operational_policy import OperationalPolicy
from tools import list_tools

logger = logging.getLogger(__name__)

WELCOME = f"""
╔══════════════════════════════════════════╗
║          AI Assistant  v{__version__:<5}        ║
║  Type /help for commands                 ║
╚══════════════════════════════════════════╝
"""

HELP_TEXT = """
Commands
--------
/help                   Show this help
/tools [category]       List tools or tools in one category
/status                 Show session and configuration status
/memory                 Show memory statistics
/recall <query>         Search memory
/remember <text>        Store a fact in memory
/clear                  Clear conversation history
/config                 Show current configuration with secrets redacted
/approval [on|off]      Show or change approval prompts for this session
/exit  /quit            Exit
"""


def _print_tools(category: Optional[str] = None) -> bool:
    """Print tools, returning False when a requested category is unknown."""
    tools = list_tools()
    categories = sorted({tool["category"] for tool in tools})
    if category:
        normalized = category.lower()
        if normalized not in categories:
            print(
                f"Unknown tool category: {category}. "
                f"Available categories: {', '.join(categories)}"
            )
            return False
        tools = [tool for tool in tools if tool["category"] == normalized]

    for tool in tools:
        approval = " [approval required]" if tool["requires_approval"] else ""
        print(f"  {tool['name']:<35} [{tool['category']}]{approval}")
        print(f"    {tool['description']}")
    print(f"\n  Total: {len(tools)} tools")
    return True


def _print_config(config: Config) -> None:
    data = asdict(config)
    if data.get("api_key"):
        data["api_key"] = "***"
    print(json.dumps(data, indent=2))


def _print_status(assistant: Assistant, config: Config) -> None:
    stats = assistant.memory_stats()
    print(
        "Session status\n"
        "--------------\n"
        f"Model: {config.model}\n"
        f"API key: {'configured' if config.api_key else 'not configured'}\n"
        f"Approval prompts: {'enabled' if config.require_approval else 'disabled'}\n"
        f"Conversation messages: {len(assistant.history)}\n"
        f"Stored memory entries: {stats['total']}"
    )


def _handle_command(cmd: str, assistant: Assistant, config: Config) -> bool:
    """Handle one slash command and return True when the CLI should exit."""
    parts = cmd.split(None, 1)
    verb = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if verb in ("/exit", "/quit"):
        return True
    if verb == "/help":
        print(HELP_TEXT)
    elif verb == "/tools":
        _print_tools(arg or None)
    elif verb == "/status":
        _print_status(assistant, config)
    elif verb == "/memory":
        print(json.dumps(assistant.memory_stats(), indent=2))
    elif verb == "/recall":
        if not arg:
            print("Usage: /recall <query>")
            return False
        results = assistant.recall(arg)
        if not results:
            print("No matching memories found.")
        for entry in results:
            print(assistant.memory.format_entry(entry))
    elif verb == "/remember":
        if not arg:
            print("Usage: /remember <text>")
            return False
        entry_id = assistant.remember(arg)
        print(f"Stored memory: {entry_id}")
    elif verb == "/clear":
        assistant.reset()
        print("Conversation history cleared.")
    elif verb == "/config":
        _print_config(config)
    elif verb == "/approval":
        if arg not in {"", "on", "off"}:
            print("Usage: /approval [on|off]")
            return False
        if arg:
            config.require_approval = arg == "on"
        print(f"Approval prompts are {'enabled' if config.require_approval else 'disabled'} for this session.")
    else:
        print(f"Unknown command: {verb}. Type /help for help.")
    return False


def run_cli(config: Config | None = None) -> int:
    """Run the interactive session and return a process exit code."""
    cfg = config or Config.load()
    if config is None:
        cfg.setup_logging()
    assistant = Assistant(cfg)

    print(WELCOME)
    if not cfg.api_key:
        print("Warning: No API key configured.")
        print("Set OPENAI_API_KEY or ASSISTANT_API_KEY before sending an AI prompt.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return 0

        if not user_input:
            continue
        if user_input.startswith("/"):
            if _handle_command(user_input, assistant, cfg):
                print("Goodbye!")
                return 0
            continue

        print("Assistant: ", end="", flush=True)
        try:
            print(assistant.chat(user_input))
        except KeyboardInterrupt:
            print("\nRequest cancelled.")
        except Exception as error:
            logger.error("Error during chat: %s", error)
            print(f"[Error] {error}")
        print()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assistant",
        description="AI Assistant CLI",
    )
    parser.add_argument("--config", "-c", metavar="PATH", help="Path to config file")
    parser.add_argument("--model", "-m", metavar="MODEL", help="Override LLM model")
    parser.add_argument("--message", "-M", metavar="TEXT", help="Send one message and exit")
    parser.add_argument(
        "--list-tools",
        nargs="?",
        const="",
        metavar="CATEGORY",
        help="List all tools or tools in one category and exit",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Show effective configuration with secrets redacted and exit",
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


def _config_path(args: argparse.Namespace) -> Path:
    return Path(args.config) if args.config else Path(
        os.environ.get("ASSISTANT_CONFIG", DEFAULT_CONFIG_PATH)
    )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    modes = sum((
        args.init_config,
        args.list_tools is not None,
        args.show_config,
        args.message is not None,
    ))
    if modes > 1:
        parser.error("Choose only one of --init-config, --list-tools, --show-config, or --message")

    config_path = _config_path(args)
    if args.init_config:
        if config_path.exists():
            parser.error(f"Configuration already exists: {config_path}")
        Config().save(config_path)
        print(f"Created configuration: {config_path}")
        return 0

    cfg = Config.load(config_path)
    cfg.setup_logging()
    if args.model:
        cfg.model = args.model
    if args.no_approval:
        cfg.require_approval = False

    if args.list_tools is not None:
        return 0 if _print_tools(args.list_tools or None) else 2
    if args.show_config:
        _print_config(cfg)
        return 0
    if args.message is not None:
        if not cfg.api_key and OperationalPolicy.response_for(args.message) is None:
            print(
                "Error: No API key configured. Set OPENAI_API_KEY or use --config PATH.",
                file=sys.stderr,
            )
            return 2
        try:
            response = Assistant(cfg).chat(args.message)
        except Exception as error:
            logger.error("Non-interactive chat failed: %s", error)
            print(f"Error: {error}", file=sys.stderr)
            return 1
        if response.startswith("API error:"):
            print(response, file=sys.stderr)
            return 1
        print(response)
        return 0

    return run_cli(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
