"""Deterministic safety checks and operating guidance for the assistant."""

from __future__ import annotations

import re
from typing import Optional


class OperationalPolicy:
    """Handles requests that must not depend on a model's interpretation."""

    _PERFORMANCE_REQUEST = re.compile(r"\b(make|improve|speed up|optimi[sz]e).{0,40}\b(fast|faster|performance)\b|\bwhy is .{0,40} slow\b", re.I)
    _DELETION_REQUEST = re.compile(r"\b(delete|remove|wipe|clean)\s+(everything|all|it all)\b", re.I)
    _ROOT_DELETION = re.compile(r"(?:^|[;&|]\s*)rm\s+(?:-[a-z]*[rf][a-z]*\s+|--recursive\s+--force\s+)/?(?:\s|$)|\b(?:rm|rmdir)\s+-rf\s+/(?:\s|$)", re.I)
    _PRIVATE_KEY_EXFILTRATION = re.compile(
        r"(?:upload|post|send|expose|publish|share|curl|wget).{0,100}"
        r"(?:id_rsa|id_ed25519|\.ssh/|private[_ -]?key|ssh\s+key)",
        re.I,
    )

    @classmethod
    def response_for(cls, message: str) -> Optional[str]:
        """Return a required response for ambiguous or unsafe user requests."""
        if cls._PRIVATE_KEY_EXFILTRATION.search(message):
            return (
                "I can't expose or upload a private SSH key. I can help you rotate it, "
                "add only the public key to an authorized service, or store the private key securely."
            )
        if cls._ROOT_DELETION.search(message):
            return "I can't run a command that can delete the whole filesystem."
        if cls._DELETION_REQUEST.search(message):
            return (
                "I won't assume you mean the entire disk. Which do you mean: "
                "build artifacts, git-ignored files, or the current directory?"
            )
        if cls._PERFORMANCE_REQUEST.search(message):
            return (
                "Faster in what way: startup, compile, tests, runtime, Docker build, "
                "or website loading?"
            )
        return None

    @classmethod
    def tool_call_error(cls, tool_name: str, arguments: dict) -> Optional[str]:
        """Block destructive tool calls even if approval prompts are disabled."""
        command = str(arguments.get("command", ""))
        if tool_name == "run_command" and cls._ROOT_DELETION.search(command):
            return "Blocked a command that can delete the whole filesystem."
        if tool_name == "run_command" and cls._PRIVATE_KEY_EXFILTRATION.search(command):
            return "Blocked an attempt to expose a private SSH key."

        if tool_name == "delete_file":
            path = str(arguments.get("path", "")).strip()
            if path in {"/", "~", "$HOME"}:
                return "Blocked deletion of a filesystem root or home directory."
        return None


OPERATIONAL_PLAYBOOKS = """\
Operational behavior:
- Ask one concise clarifying question before editing for broad performance requests:
  startup, compile, tests, runtime, Docker build, or website loading.
- For vague deletion requests, never assume scope. Offer build artifacts, git-ignored
  files, and current directory. Never delete a filesystem root. Never expose, upload,
  or print private keys, credentials, or tokens.
- To explain a repository, inspect its structure and metadata first (git ls-files,
  README, package manifests, build manifests, entry points, and tests), then summarize
  architecture, dependencies, build system, entry points, and test structure. Do not
  dump files.
- For lost Git work, inspect git status, git reflog, git stash, and git fsck before
  proposing recovery. For a failed npm install, read package.json and the npm log, then
  inspect Node and npm versions. Do not guess from the error alone.
- Use native tools for simple facts. For example, count files with a filesystem command
  instead of reasoning. Search code with ripgrep or symbols before answering where a
  feature is implemented. Use semantic rename/refactoring support when available rather
  than blind text replacement.
- Start builds and tests before commenting on their result. Let long-running commands
  run and report live output when supported. On failure, identify the first actionable
  compiler or test error and categorize independent failures before fixing them.
- For Docker failures, inspect docker ps, docker info, service status, and relevant
  logs. For crashes, inspect logs and search for errors before diagnosing. For network
  failures, check connectivity, DNS, routes/gateway, and an HTTP request in that order.
- For database sizing, query database metadata/statistics rather than inspecting files
  manually. For permissions, inspect ownership, ACLs, mode, and umask before changing
  anything. Use current conversation context for service names and prior diagnostics.
- Before a Python-version upgrade or other breaking migration, present a plan, risks,
  compatibility checks, and migration order. Break massive refactors into incremental
  phases. For current versions or external documentation, fetch authoritative online
  sources. For unknown CLIs, run --help before using them.
- Profile performance with measurement tools before optimizing (for Rust, use perf,
  cargo flamegraph, or hyperfine when available). Reuse prior search results for
  repeated requests when still valid.
- When interrupted, stop the exact process cleanly and verify it has exited. Deployments
  require framework and deployment-doc discovery, secret checks, tests, builds,
  backup/rollback preparation, deployment, health checks, log checks, smoke tests, and
  a report containing elapsed time, changed files, commit, rollback command, and health.
"""
