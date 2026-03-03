from __future__ import annotations
import sys
from pathlib import Path

parent = str(Path(__file__).resolve().parent.parent)
if parent not in sys.path:
    sys.path.insert(0, parent)

import asyncio
import os
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import discord
from discord.ext import commands

from system.agent import Agent, AgentManager
from prompts.system import SYSTEM_PROMPT, DISCORD_LEAVE_INSTRUCTION
from dotenv import load_dotenv
load_dotenv()


@dataclass
class DiscordBridge:
    """Discord-specific state management for the agent."""
    
    manager: AgentManager = field(init=False)
    agent: Agent | None = field(init=False, default=None)
    _active_session: bool = field(init=False, default=False)
    _channel: discord.abc.Messageable | None = field(init=False, default=None)

    def __init__(self):
        self.manager = AgentManager(
            extra_system_prompt=DISCORD_LEAVE_INSTRUCTION,
        )
        self._active_session = False
        self._channel = None

    async def start(self) -> None:
        """Initialize the agent."""
        self.agent = await self.manager.start(SYSTEM_PROMPT)

    async def close(self) -> None:
        """Clean up resources."""
        await self.manager.close()

    def reset_conversation(self) -> None:
        """Reset the conversation history."""
        if self.agent:
            self.agent.reset_conversation()

    def request_stop(self) -> None:
        """Request the agent to stop processing."""
        if self.agent:
            self.agent.request_stop()
    
    def activate_session(self) -> None:
        """Mark session as active."""
        self._active_session = True
    
    def deactivate_session(self) -> None:
        """Mark session as inactive."""
        self._active_session = False
    
    def is_session_active(self) -> bool:
        """Check if there's an active session."""
        return self._active_session

    def set_channel(self, channel: discord.abc.Messageable) -> None:
        """Set the channel for sending messages."""
        self._channel = channel

    async def send(self, message: str) -> None:
        """Send a message to the current channel (like print() for CLI)."""
        if not self._channel:
            raise RuntimeError("Channel is not set.")
        
        chunks = split_for_discord(message)
        for chunk in chunks:
            await self._channel.send(chunk)

    async def run_prompt(
        self,
        prompt_text: str,
        on_tool_call: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Run a prompt and return a string response."""
        if not self.agent:
            raise RuntimeError("Agent is not initialized.")

        result = await self.agent.run_prompt(
            prompt_text,
            on_tool_call=on_tool_call,
        )
        action = result.get("action")

        if action == "final":
            return result.get("message", "")

        if action == "ask":
            return result.get("question", "Please provide more information.")

        if action == "leave":
            return f"__LEAVE__::{result.get('message', '')}"

        if action == "stop":
            return "Operation stopped."

        raise RuntimeError(f"Unexpected action from agent: {action}")


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


async def main() -> None:
    activation_word = (os.environ.get("DISCORD_ACTIVATION_WORD") or "").strip()
    if (activation_word.startswith('"') and activation_word.endswith('"')) or (
        activation_word.startswith("'") and activation_word.endswith("'")
    ):
        activation_word = activation_word[1:-1].strip()
    allowed_user_id_raw = (os.environ.get("DISCORD_USER_ID") or "").strip()
    allowed_user_id = int(allowed_user_id_raw) if allowed_user_id_raw.isdigit() else None

    discord_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not discord_token:
        raise RuntimeError("DISCORD_BOT_TOKEN environment variable is required.")

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    bridge = DiscordBridge()

    @bot.event
    async def setup_hook() -> None:
        await bridge.start()

    @bot.event
    async def on_ready() -> None:
        print(f"Logged in as {bot.user}")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return

        if allowed_user_id is not None and message.author.id != allowed_user_id:
            return

        bot_user = bot.user
        if not bot_user:
            return

        is_dm = message.guild is None
        is_mention = bot_user in message.mentions
        message_text = message.content.strip()
        is_activation_word = bool(activation_word) and message_text.lower().startswith(activation_word.lower())
        # Check if this is an active session or a new message to activate
        is_active_session = bridge.is_session_active()
        is_new_activation = not is_active_session and (is_dm or is_mention or is_activation_word)
        
        if not is_active_session and not is_new_activation:
            return

        content = message.content
        for mention in (bot_user.mention, f"<@!{bot_user.id}>", f"<@{bot_user.id}>"):
            content = content.replace(mention, "")
        if is_activation_word and activation_word:
            content = content[len(activation_word):]
        content = content.strip()

        # Activate session on first allowed trigger
        if is_new_activation:
            bridge.activate_session()

        # Set the channel for this message context
        bridge.set_channel(message.channel)

        if content == "/reset":
            bridge.reset_conversation()
            await bridge.send("Conversation reset.")
            return
        
        if content == "/stop":
            bridge.request_stop()
            await bridge.send("Stop requested.")
            return

        async def send_tool_message(msg: str) -> None:
            await bridge.send(msg)

        try:
            response = await bridge.run_prompt(
                content,
                on_tool_call=send_tool_message,
            )
        except Exception as exc:
            response = f"Error: {exc}"

        if response.startswith("__LEAVE__::"):
            bridge.deactivate_session()
            leave_message = response.removeprefix("__LEAVE__::").strip()
            if leave_message != "":
                await bridge.send(leave_message)
            return

        if response.strip() == "":
            return
        
        # Send the final response
        await bridge.send(response)

    try:
        await bot.start(discord_token)
    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
