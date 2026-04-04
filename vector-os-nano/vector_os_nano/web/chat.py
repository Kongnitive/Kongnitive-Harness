"""ChatManager — async AI chat with conversation memory.

Manages multi-turn conversation with Claude Haiku via OpenRouter.
Detects robot commands vs general chat and routes accordingly.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

def _load_agent_prompt() -> str:
    """Load agent.md system prompt."""
    from pathlib import Path
    for p in [
        Path("config/agent.md"),
        Path(__file__).parent.parent.parent / "config" / "agent.md",
    ]:
        if p.exists():
            return p.read_text()
    return (
        "You are V, the AI agent for Vector OS Nano. "
        "You control a SO-101 robot arm. Keep responses concise. "
        "No markdown. Match the user's language.\n\n"
        "Mode: {mode}\nArm: {arm_status}\nGripper: {gripper_status}\n"
        "Objects: {objects_info}"
    )

_AGENT_PROMPT_TEMPLATE = _load_agent_prompt()

# Commands that should be routed to Agent.execute()
_COMMAND_KEYWORDS = [
    "pick", "grab", "grasp", "抓起", "抓住", "抓取",
    "place", "put", "放下", "放到",
    "home",
    "scan",
    "detect", "检测",
    "open", "打开夹", "张开",
    "close", "关闭夹", "合上",
    "stop", "停止",
]

_CHAT_OVERRIDES = [
    "你能", "你可以", "你会", "什么", "怎么", "如何", "为什么", "哪",
    "can you", "what", "how", "why", "which", "tell me", "explain",
    "help me", "is there", "are there", "do you", "could you",
]


def _is_robot_command(text: str) -> bool:
    """Heuristic: does this message look like a robot command?"""
    lower = text.lower().strip()
    if any(phrase in lower for phrase in _CHAT_OVERRIDES):
        return False
    return any(kw in lower for kw in _COMMAND_KEYWORDS)


class ChatManager:
    """Manages AI conversation with multi-turn memory.

    Args:
        api_key: OpenRouter API key.
        model: LLM model identifier.
        api_base: API base URL.
        max_history: max conversation turns to keep.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-haiku-4-5",
        api_base: str = "https://openrouter.ai/api/v1",
        max_history: int = 30,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._endpoint = f"{api_base.rstrip('/')}/chat/completions"
        self._max_history = max_history
        self._history: list[dict[str, str]] = []
        self._http = httpx.AsyncClient(timeout=30.0)

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    def add_system_message(self, content: str) -> None:
        """Add a system/execution result to history."""
        self._history.append({"role": "assistant", "content": content})
        self._trim_history()

    async def chat(
        self,
        user_message: str,
        state_info: str = "",
        objects_info: str = "",
    ) -> str:
        """Send a message and get AI response.

        Returns the AI's text response. Updates conversation history.
        """
        self._history.append({"role": "user", "content": user_message})
        self._trim_history()

        system = _AGENT_PROMPT_TEMPLATE.format(
            mode=state_info or "unknown",
            arm_status="connected",
            gripper_status="unknown",
            objects_info=objects_info or "unknown",
        )

        messages = [{"role": "system", "content": system}] + self._history

        try:
            resp = await self._http.post(
                self._endpoint,
                json={
                    "model": self._model,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 1024,
                },
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            logger.warning("Chat LLM error: %s", exc)
            text = f"LLM error: {exc}"

        self._history.append({"role": "assistant", "content": text})
        self._trim_history()
        return text

    def is_command(self, text: str) -> bool:
        """Check if user message is a robot command."""
        return _is_robot_command(text)

    def _trim_history(self) -> None:
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    async def close(self) -> None:
        await self._http.aclose()
