from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import discord
from discord.ext import commands
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from cli import (
    AzureModelsClient,
    describe_tools,
    parse_agent_command,
    serialize_tool_result,
)
from prompts import SYSTEM_PROMPT, DISCORD_LEAVE_INSTRUCTION

# Optional .env support for local development.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


@dataclass
class MCPAgentBridge:
    token: str
    model: str
    server_command: str
    server_args: list[str]
    max_calls_per_prompt: int = 10

    gh_client: AzureModelsClient = field(init=False)
    _exit_stack: AsyncExitStack = field(init=False)
    session: ClientSession | None = field(init=False, default=None)
    tool_names: set[str] = field(init=False, default_factory=set)
    system_block: dict[str, str] = field(init=False)
    conversation: list[dict[str, str]] = field(init=False)
    _busy: bool = field(init=False, default=False)
    _stop_requested: bool = field(init=False, default=False)
    _active_user_id: int | None = field(init=False, default=None)
    _active_channel_id: int | None = field(init=False, default=None)
    pending_messages: list[str] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.gh_client = AzureModelsClient(
            token=self.token,
            model=self.model,
            max_calls_per_prompt=self.max_calls_per_prompt,
        )
        self._exit_stack = AsyncExitStack()

    async def start(self) -> None:
        server_params = StdioServerParameters(command=self.server_command, args=self.server_args)
        read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
        self.session = await self._exit_stack.enter_async_context(ClientSession(read, write))

        await self.session.initialize()
        tools_response = await self.session.list_tools()
        self.tool_names = {tool.name for tool in tools_response.tools}
        tool_descriptions = describe_tools(tools_response.tools)
        self.system_block = {
            "role": "system",
            "content": f"{SYSTEM_PROMPT}\n{DISCORD_LEAVE_INSTRUCTION}\n{tool_descriptions}",
        }
        self.conversation = [self.system_block]

    async def close(self) -> None:
        await self._exit_stack.aclose()

    def reset_conversation(self) -> None:
        self.conversation = [self.system_block]

    def try_acquire(self) -> bool:
        if self._busy:
            return False
        self._busy = True
        return True

    def release(self) -> None:
        self._busy = False
    
    def request_stop(self) -> None:
        self._stop_requested = True
    
    def set_active_user(self, user_id: int, channel_id: int) -> None:
        self._active_user_id = user_id
        self._active_channel_id = channel_id
    
    def clear_active_user(self) -> None:
        self._active_user_id = None
        self._active_channel_id = None
    
    def is_user_active(self, user_id: int, channel_id: int) -> bool:
        return self._active_user_id == user_id and self._active_channel_id == channel_id

    async def run_prompt(self, prompt_text: str, on_tool_call: Callable[[str], Awaitable[None]] | None = None) -> str:
        if not self.session:
            raise RuntimeError("MCP session is not initialized.")

        self.pending_messages = []
        self._stop_requested = False
        self.conversation.append({"role": "user", "content": prompt_text})
        self.gh_client.reset_call_count()

        while True:
            if self._stop_requested:
                return "Operation stopped."
            model_reply = self.gh_client.complete(self.conversation)
            command = parse_agent_command(model_reply, self.tool_names)
            action = command.get("action")

            if action == "final":
                self.conversation.append({"role": "assistant", "content": model_reply})
                return command.get("message", "")

            if action == "ask":
                self.conversation.append({"role": "assistant", "content": model_reply})
                return command.get("question", "Please provide more information.")

            if action == "leave":
                self.conversation.append({"role": "assistant", "content": model_reply})
                return f"__LEAVE__::{command.get('message', '')}"

            if action != "tool":
                raise RuntimeError(f"Unknown action from model: {command}")

            tool_name = command.get("tool")
            if tool_name not in self.tool_names:
                raise RuntimeError(f"Model requested unknown tool: {tool_name}")

            tool_msg = f"Model calling tool: {tool_name}()"
            if on_tool_call:
                await on_tool_call(tool_msg)
            else:
                self.pending_messages.append(tool_msg)
            arguments = command.get("arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {}

            tool_result: types.CallToolResult = await self.session.call_tool(tool_name, arguments)
            result_payload = serialize_tool_result(tool_result)
            self.conversation.extend(
                [
                    {"role": "assistant", "content": model_reply},
                    {
                        "role": "user",
                        "content": json.dumps({"tool": tool_name, "result": result_payload}),
                    },
                ]
            )


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


def extract_activation_word_command(text: str) -> str | None:
    normalized = text.strip().strip('"').strip("'")
    patterns = [
        r"^set\s+activation\s+word\s+to\s+(.+)$",
        r"^activation\s+word\s*=\s*(.+)$",
        r"^set\s+discord\s+activation\s+word\s+to\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, normalized, flags=re.IGNORECASE)
        if match:
            word = match.group(1).strip().strip('"').strip("'")
            return word if word else None
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discord bot bridge for the MCP agent")
    parser.add_argument(
        "--server-command",
        default="python",
        help="Executable used to launch the MCP server (defaults to python)",
    )
    parser.add_argument(
        "--server-args",
        nargs=argparse.REMAINDER,
        default=["skills/combined.py"],
        help="Arguments passed to the MCP server command",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="GitHub Models identifier for Azure inference",
    )
    return parser


async def main() -> None:
    args = build_arg_parser().parse_args()
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

    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise RuntimeError("GITHUB_TOKEN environment variable is required.")

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    bridge = MCPAgentBridge(
        token=github_token,
        model=args.model,
        server_command=args.server_command,
        server_args=args.server_args,
    )

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
        is_active_session = bridge.is_user_active(message.author.id, message.channel.id)
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
            bridge.set_active_user(message.author.id, message.channel.id)

        if content == "/reset":
            bridge.reset_conversation()
            await message.reply("Conversation reset.", mention_author=False)
            return
        
        if content == "/stop":
            bridge.request_stop()
            await message.reply("Stop requested.", mention_author=False)
            return
        
        requested_activation_word = extract_activation_word_command(content)
        if requested_activation_word:
            if not bridge.session:
                await message.reply("MCP session is not ready yet.", mention_author=False)
                return

            tool_to_call = None
            arguments: dict[str, Any] = {}
            if "set_discord_activation_word" in bridge.tool_names:
                tool_to_call = "set_discord_activation_word"
                arguments = {"word": requested_activation_word}
            elif "edit_env" in bridge.tool_names:
                tool_to_call = "edit_env"
                arguments = {
                    "field": "DISCORD_ACTIVATION_WORD",
                    "content": requested_activation_word,
                }

            if not tool_to_call:
                await message.reply("No env editing tool is available.", mention_author=False)
                return

            await message.channel.send(f"Model calling tool: {tool_to_call}()")
            try:
                await bridge.session.call_tool(tool_to_call, arguments)
                await message.reply(
                    f"Activation word updated to: {requested_activation_word}. Restart bot to apply.",
                    mention_author=False,
                )
            except Exception as exc:
                await message.reply(f"Error updating activation word: {exc}", mention_author=False)
            return

        if not bridge.try_acquire():
            await message.reply("Bot is busy, please wait for the current operation to complete.", mention_author=False)
            return

        async def send_tool_message(msg: str) -> None:
            await message.channel.send(msg)

        try:
            response = await bridge.run_prompt(content, on_tool_call=send_tool_message)
        except Exception as exc:
            error_msg = f"Error: {exc}"
            bridge.pending_messages.append(error_msg)
            response = error_msg
        finally:
            bridge.release()

        # Send pending messages (errors, etc.)
        for pending_msg in bridge.pending_messages:
            await message.channel.send(pending_msg)

        if response.startswith("__LEAVE__::"):
            bridge.clear_active_user()
            leave_message = response.removeprefix("__LEAVE__::").strip()
            if leave_message != "":
                await message.reply(leave_message, mention_author=False)
            return

        if response.strip() == "":
            return
        # Then send the final response
        chunks = split_for_discord(response)
        for idx, chunk in enumerate(chunks):
            if idx == 0:
                await message.reply(chunk, mention_author=False)
            else:
                await message.channel.send(chunk)

    try:
        await bot.start(discord_token)
    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
