"""
Demo script — runs the assistant against a series of prompts using a
mock API client so no real API key is required.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from config import Config
from assistant import Assistant
from tools import call_tool, list_tools


# ── Mock API so demo runs without a real key ──────────────────────────────

def _make_mock_client(responses: list[str]):
    """Return a mock APIClient that cycles through canned responses."""
    client = MagicMock()
    idx = {"i": 0}

    def fake_chat(messages, tools=None, tool_choice="auto", stream=False):
        text = responses[min(idx["i"], len(responses) - 1)]
        idx["i"] += 1
        return {
            "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "model": "mock",
        }

    client.chat.side_effect = fake_chat
    return client


# ── Demo scenarios ────────────────────────────────────────────────────────

def demo_system_info():
    print("=" * 60)
    print("DEMO 1: System information")
    print("=" * 60)
    result = call_tool("system_info", {})
    print(json.dumps(result, indent=2))


def demo_file_ops(tmp_dir: str = "/tmp/assistant_demo"):
    import os
    os.makedirs(tmp_dir, exist_ok=True)
    print("\n" + "=" * 60)
    print("DEMO 2: File operations")
    print("=" * 60)

    # Write
    r = call_tool("write_file", {"path": f"{tmp_dir}/hello.txt", "content": "Hello, assistant!\n"})
    print("write_file:", r)

    # Read
    r = call_tool("read_file", {"path": f"{tmp_dir}/hello.txt"})
    print("read_file:", r)

    # Search
    r = call_tool("search_files", {"directory": tmp_dir, "pattern": "*.txt"})
    print("search_files:", r)

    # Disk usage
    r = call_tool("disk_usage", {"path": tmp_dir})
    print("disk_usage:", r)


def demo_network():
    print("\n" + "=" * 60)
    print("DEMO 3: Network checks")
    print("=" * 60)
    r = call_tool("check_connectivity", {})
    print("connectivity:", r)
    r = call_tool("dns_lookup", {"hostname": "example.com"})
    print("dns_lookup:", r)


def demo_security():
    print("\n" + "=" * 60)
    print("DEMO 4: Security tools")
    print("=" * 60)
    r = call_tool("generate_password", {"length": 24})
    print("generate_password:", r)
    r = call_tool("hash_text", {"text": "hello world"})
    print("hash_text:", r)


def demo_data():
    print("\n" + "=" * 60)
    print("DEMO 5: Data analysis")
    print("=" * 60)
    nums = [12.5, 8.3, 15.0, 9.7, 11.2, 14.8, 7.6, 13.1]
    r = call_tool("describe_data", {"numbers": nums})
    print("describe_data:", json.dumps(r, indent=2))


def demo_productivity():
    print("\n" + "=" * 60)
    print("DEMO 6: Productivity")
    print("=" * 60)
    r = call_tool("create_task", {
        "title": "Write unit tests",
        "priority": "high",
        "project": "assistant",
        "due": "2025-01-15",
    })
    print("create_task:", json.dumps(r, indent=2))

    r = call_tool("format_report", {
        "title": "Sprint Summary",
        "data": [
            {"task": "API client", "status": "done", "hours": 3},
            {"task": "Tools module", "status": "done", "hours": 8},
            {"task": "Tests", "status": "in progress", "hours": 2},
        ],
    })
    print("format_report:\n", r["result"])


def demo_memory():
    print("\n" + "=" * 60)
    print("DEMO 7: Memory / PKM")
    print("=" * 60)
    cfg = Config()
    cfg.memory_path = "/tmp/assistant_demo_memory.json"
    from memory import Memory
    mem = Memory(cfg)

    id1 = mem.store("Python 3.12 ships with tomllib in stdlib", entry_type="fact",
                    tags=["python", "stdlib"])
    id2 = mem.store("Project assistant: build a general-purpose AI assistant",
                    entry_type="project", project="assistant")
    mem.link_entries(id1, id2, "used_in")

    results = mem.search("python")
    print(f"Search 'python': {len(results)} results")
    for r in results:
        print(" ", mem.format_entry(r))

    print("Stats:", mem.stats())


def demo_text_tools():
    print("\n" + "=" * 60)
    print("DEMO 8: Text / research tools")
    print("=" * 60)
    text = (
        "Artificial intelligence has transformed many industries. "
        "Machine learning models can now generate text, images, and code. "
        "Large language models are trained on vast amounts of internet data. "
        "They are used for translation, summarisation, and question answering. "
        "The field continues to advance rapidly with new architectures."
    )
    r = call_tool("summarize_text", {"text": text, "max_sentences": 3})
    print("summarize_text:", r)
    r = call_tool("word_frequency", {"text": text, "top_n": 10})
    print("word_frequency:", r)


def demo_mock_chat():
    print("\n" + "=" * 60)
    print("DEMO 9: Mock chat session")
    print("=" * 60)

    cfg = Config()
    cfg.memory_path = "/tmp/assistant_demo_memory.json"
    assistant = Assistant(cfg)

    # Replace the real API client with a mock
    assistant.client = _make_mock_client([
        "I'll check your system information right away.",
        "Your system is running Linux with 8 CPU cores and 16 GB RAM. Uptime is 2 hours.",
    ])

    resp = assistant.chat("What's the current state of my system?")
    print(f"User: What's the current state of my system?")
    print(f"Assistant: {resp}\n")


def demo_list_tools():
    print("\n" + "=" * 60)
    print("DEMO 10: Available tools (first 15)")
    print("=" * 60)
    tools = list_tools()
    for t in tools[:15]:
        print(f"  {t['name']:<35} [{t['category']}]")
    print(f"  ... and {len(tools) - 15} more")


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_system_info()
    demo_file_ops()
    demo_network()
    demo_security()
    demo_data()
    demo_productivity()
    demo_memory()
    demo_text_tools()
    demo_mock_chat()
    demo_list_tools()
    print("\n✅  All demos completed successfully.")
