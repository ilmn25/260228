"""Shared bridge logic used by various interfaces.

This module encapsulates the ``AgentBridge`` class and utility helpers such
as ``split_for_discord``.  The bridge hides agent/session management so the
same code can drive CLI, Discord, Slack, etc., without duplication.
"""

from __future__ import annotations

import sys
import asyncio
from pathlib import Path
from typing import Any, Callable, Awaitable

# make sure the repository root is on sys.path so "prompts" and "skills" packages are importable
parent = str(Path(__file__).resolve().parent.parent)
if parent not in sys.path:
    sys.path.insert(0, parent)

from prompts.system import SYSTEM_PROMPT, DISCORD_LEAVE_INSTRUCTION, SPEECH_INPUT_PROMPT
from agent import Agent, AgentManager


class AgentBridge:
    """Generic state management wrapper for an ``Agent`` instance.

    Originally Discord-specific, the bridge now drives any front end that
    needs to interact with the agent.  It manages sessions, channels, and
    provides a thin ``process_prompt`` façade.
    """

    def __init__(self, extra_system_prompt: str = DISCORD_LEAVE_INSTRUCTION, activation_timeout_seconds: float | None = None):
        self.manager: AgentManager = AgentManager(
            extra_system_prompt=extra_system_prompt,
        )
        self.agent: Agent | None = None
        self._active_session: bool = False
        self._channel: Any | None = None
        self._activation_timeout_seconds = activation_timeout_seconds
        self._timeout_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Initialize the agent.

        Idempotent; calling repeatedly has no effect after the first start so
        the bridge may safely be shared between CLI and bot instances.
        """
        if self.agent is None:
            self.agent = await self.manager.start(SYSTEM_PROMPT)

    async def close(self) -> None:
        """Clean up resources.

        Manager shutdown may raise errors from underlying MCP client when the
        async generator is closed; those are non-fatal for our application and
        can be safely ignored.
        """
        try:
            await self.manager.close()
        except Exception as exc: 
            pass

    def reset_conversation(self) -> None:
        """Reset the conversation history."""
        if self.agent:
            self.agent.reset_conversation()

    def request_stop(self) -> None:
        """Request the agent to stop processing."""
        if self.agent:
            self.agent.request_stop()

    # session helpers -----------------------------------------------------
    async def _auto_leave_on_timeout(self) -> None:
        """Auto-deactivate session after timeout expires."""
        if self._activation_timeout_seconds is None:
            return
        
        try:
            await asyncio.sleep(self._activation_timeout_seconds)
            if self._active_session:
                print(f"⏱️  Session timeout ({self._activation_timeout_seconds}s) - auto-leaving...")
                self.deactivate_session()
        except asyncio.CancelledError:
            pass  # Timeout was cancelled due to user activity

    def activate_session(self) -> None:
        """Mark session as active and start timeout if configured."""
        self._active_session = True
        # Cancel any existing timeout task
        if self._timeout_task is not None:
            self._timeout_task.cancel()
        # Start a new timeout task if timeout is configured
        if self._activation_timeout_seconds is not None:
            self._timeout_task = asyncio.create_task(self._auto_leave_on_timeout())

    def deactivate_session(self) -> None:
        """Mark session as inactive and cancel timeout."""
        self._active_session = False
        # Cancel the timeout task
        if self._timeout_task is not None:
            self._timeout_task.cancel()
            self._timeout_task = None

    def is_session_active(self) -> bool:
        """Check if there's an active session."""
        return self._active_session

    def _reset_timeout(self) -> None:
        """Reset the timeout timer during active session (called on user input)."""
        if self._active_session and self._activation_timeout_seconds is not None:
            # Cancel existing timeout and start a new one
            if self._timeout_task is not None:
                self._timeout_task.cancel()
            self._timeout_task = asyncio.create_task(self._auto_leave_on_timeout())

    def set_channel(self, channel: Any) -> None:
        """Set the channel for sending messages."""
        self._channel = channel

    async def send(self, message: str) -> None:
        """Send a message to the current channel (like ``print()`` for CLI).

        The text is automatically split into Discord-friendly chunks so the
        caller never has to worry about the 2k character limit.
        """
        if not self._channel:
            raise RuntimeError("Channel is not set.")

        chunks = split_for_discord(message)
        for chunk in chunks:
            await self._channel.send(chunk)





    async def process_prompt(
        self,
        content: str,
        send: Callable[[str], Awaitable[None]],
    ) -> str:
        """Handle a user prompt and send the resulting message.

        Calls into :class:`Agent` for the core logic, then formats the result
        and handles side‑effects (e.g. deactivating the session on ``leave``)
        before dispatching the text via ``send``.
        
        Resets activation timeout on user input during active session.

        Returns the action returned by the agent (e.g. "final", "ask",
        "leave", "stop"), allowing callers (like the CLI) to react.
        """
        if not self.agent:
            raise RuntimeError("Agent is not initialized.")

        # Reset timeout on user input if session is active
        if self._active_session:
            self._reset_timeout()

        # delegate to agent, which now returns (message, action)
        message, action = await self.agent.process_prompt(content, send)
        if action == "leave":
            self.deactivate_session()
        if message.strip():
            await send(message)

        # If stop is requested, close bridge resources and let each front-end
        # decide how to terminate its own loop/process.
        if action == "stop":
            self.deactivate_session()
            try:
                await self.close()
            except Exception:
                pass

        # propagate action for the caller (mostly useful for CLI tests)
        return action


# ---------------------------------------------------------------------------
# utility helpers
# ---------------------------------------------------------------------------

def split_for_discord(text: str, max_len: int = 1900) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        split_at = remaining.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks
