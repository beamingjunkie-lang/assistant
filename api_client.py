"""LLM API client (OpenAI-compatible)."""

import json
import logging
import time
from typing import Any, Generator, Optional

import requests

from config import Config

logger = logging.getLogger(__name__)


class APIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class APIClient:
    def __init__(self, config: Config):
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
        })

    # ------------------------------------------------------------------
    # Chat completion
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        tool_choice: str = "auto",
        stream: bool = False,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        if stream:
            payload["stream"] = True

        url = self.config.api_base_url.rstrip("/") + "/chat/completions"
        logger.debug("POST %s  model=%s  messages=%d", url, self.config.model, len(messages))
        auth_type = "Bearer"
        auth_header = {"Authorization": f"{auth_type} {self.config.api_key}"}

        for attempt in range(3):
            try:
                resp = self._session.post(
                    url,
                    json=payload,
                    headers=auth_header,
                    timeout=self.config.timeout,
                    stream=stream,
                )
            except requests.RequestException as e:
                if attempt == 2:
                    raise APIError(f"Request failed: {e}") from e
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                logger.warning("Rate limited; waiting %ds", wait)
                time.sleep(wait)
                continue

            if not resp.ok:
                raise APIError(resp.text, resp.status_code)

            if stream:
                return self._collect_stream(resp)

            data = resp.json()
            logger.debug("Response: %s", json.dumps(data)[:200])
            return data

        raise APIError("Max retries exceeded")

    def _collect_stream(self, resp: requests.Response) -> dict:
        content_parts: list[str] = []
        tool_calls: dict[int, dict] = {}

        for raw in resp.iter_lines():
            if not raw or raw == b"data: [DONE]":
                continue
            if raw.startswith(b"data: "):
                raw = raw[6:]
            try:
                chunk = json.loads(raw)
            except json.JSONDecodeError:
                continue
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            if text := delta.get("content"):
                content_parts.append(text)
            for tc in delta.get("tool_calls", []):
                idx = tc["index"]
                if idx not in tool_calls:
                    tool_calls[idx] = {"id": tc.get("id", ""), "type": "function",
                                       "function": {"name": "", "arguments": ""}}
                if fn := tc.get("function", {}):
                    tool_calls[idx]["function"]["name"] += fn.get("name", "")
                    tool_calls[idx]["function"]["arguments"] += fn.get("arguments", "")

        message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts)}
        if tool_calls:
            message["tool_calls"] = list(tool_calls.values())

        return {
            "choices": [{"message": message, "finish_reason": "stop"}],
            "model": self.config.model,
        }

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(self, texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
        url = self.config.api_base_url.rstrip("/") + "/embeddings"
        auth_type = "Bearer"
        resp = self._session.post(
            url,
            json={"model": model, "input": texts},
            headers={"Authorization": f"{auth_type} {self.config.api_key}"},
            timeout=self.config.timeout,
        )
        if not resp.ok:
            raise APIError(resp.text, resp.status_code)
        return [item["embedding"] for item in resp.json()["data"]]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def simple_chat(self, prompt: str, system: str = "") -> str:
        """Single-turn convenience wrapper."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self.chat(messages)
        return resp["choices"][0]["message"]["content"] or ""
