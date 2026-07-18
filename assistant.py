"""
Core assistant agent.

The agent follows a ReAct-style loop:
  1. Receive the user's goal.
  2. Call the LLM with the conversation history + available tools.
  3. If the LLM requests a tool call, execute it and feed the result back.
  4. Repeat until the LLM produces a final answer (no tool calls) or
     max_iterations is reached.

Memory integration:
  Conversation context is maintained across turns.  Significant facts and
  task outcomes can be stored in the persistent Memory store.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from api_client import APIClient, APIError
from config import Config
from memory import Memory
from operational_policy import OPERATIONAL_PLAYBOOKS, OperationalPolicy
from tools import call_tool, get_schemas, list_tools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a versatile AI assistant with access to tools that cover system
administration, file management, networking, security, programming,
databases, containers, web operations, productivity, documents, data
analysis, multimedia, finance, research, personal knowledge management,
monitoring, and automation.

Guidelines:
- Think step-by-step before using tools.
- Always confirm destructive actions (delete, reboot, format) before
  proceeding unless the user explicitly says to skip confirmation.
- When presenting data, format it clearly in Markdown.
- If a task is ambiguous, ask a clarifying question rather than guessing.
- Store important facts or learned preferences in memory when relevant.
- You can chain multiple tool calls to complete complex tasks.
""" + OPERATIONAL_PLAYBOOKS


class Assistant:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.load()
        self.client = APIClient(self.config)
        self.memory = Memory(self.config)
        self.history: list[dict] = []
        self._tool_schemas = get_schemas()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def chat(self, user_message: str) -> str:
        """Process a user message and return the assistant's response."""
        self.history.append({"role": "user", "content": user_message})
        response = OperationalPolicy.response_for(user_message) or self._run_agent_loop()
        self.history.append({"role": "assistant", "content": response})
        return response

    def reset(self) -> None:
        """Clear conversation history (memory is preserved)."""
        self.history = []

    # ------------------------------------------------------------------
    # Agent loop
    # ------------------------------------------------------------------

    def _run_agent_loop(self) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self.history)

        for iteration in range(self.config.max_iterations):
            logger.debug("Agent iteration %d/%d", iteration + 1, self.config.max_iterations)

            try:
                response = self.client.chat(
                    messages=messages,
                    tools=self._tool_schemas if self._tool_schemas else None,
                )
            except APIError as e:
                error_msg = f"API error: {e}"
                logger.error(error_msg)
                return error_msg

            message = response["choices"][0]["message"]
            finish_reason = response["choices"][0].get("finish_reason", "stop")

            # If the model wants to call tools
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                messages.append(message)
                for tc in tool_calls:
                    tool_result = self._execute_tool(tc)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(tool_result),
                    })
                continue

            # Final text response
            return message.get("content") or ""

        return "I reached the maximum number of iterations without completing the task. Please try rephrasing your request."

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def _execute_tool(self, tool_call: dict) -> Any:
        fn_name = tool_call["function"]["name"]
        try:
            args = json.loads(tool_call["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            return {"status": "error", "error": "Invalid JSON arguments from model"}

        logger.info("Calling tool: %s(%s)", fn_name, json.dumps(args)[:120])

        if policy_error := OperationalPolicy.tool_call_error(fn_name, args):
            logger.warning("Blocked unsafe tool call: %s", fn_name)
            return {"status": "blocked", "error": policy_error}

        # Check approval requirement
        if self.config.require_approval:
            from tools import _REGISTRY
            entry = _REGISTRY.get(fn_name, {})
            if entry.get("requires_approval") and not self._get_approval(fn_name, args):
                return {"status": "cancelled", "reason": "User denied approval"}

        try:
            result = call_tool(fn_name, args)
            logger.debug("Tool %s result: %s", fn_name, str(result)[:200])
            return result
        except Exception as e:
            logger.exception("Tool %s raised an exception", fn_name)
            return {"status": "error", "error": str(e)}

    def _get_approval(self, tool_name: str, args: dict) -> bool:
        """Interactive approval prompt (only in CLI mode with approval enabled)."""
        print(f"\n⚠️  Tool requires approval: {tool_name}")
        print(f"   Arguments: {json.dumps(args, indent=2)}")
        answer = input("   Approve? [y/N] ").strip().lower()
        return answer in ("y", "yes")

    # ------------------------------------------------------------------
    # Memory helpers
    # ------------------------------------------------------------------

    def remember(self, content: str, entry_type: str = "fact", **kwargs) -> str:
        return self.memory.store(content, entry_type=entry_type, **kwargs)

    def recall(self, query: str, limit: int = 10) -> list[dict]:
        return self.memory.search(query, limit=limit)

    def memory_stats(self) -> dict:
        return self.memory.stats()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def available_tools(self) -> list[dict]:
        return list_tools()
