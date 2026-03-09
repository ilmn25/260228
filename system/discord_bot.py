"""Discord bot interface.

This module is responsible for wiring the Discord.py event handlers to the
shared ``AgentBridge`` logic defined in other modules.  Keeping bot-
specific code here keeps the entry point clean and allows additional
integrations (WhatsApp, SMS, etc.) to be added later.
"""

from __future__ import annotations

import os
from typing import Any

from bridge import AgentBridge

# discord dependency is optional for CLI mode; gracefully handle absence
try:
    import discord
    from discord.ext import commands
except ImportError:  # pragma: no cover - cannot import in CLI-only environments
    discord = None  # type: ignore
    commands = None  # type: ignore


async def _run_discord(bridge: AgentBridge) -> None:
    """Start the Discord bot using an existing bridge."""
    if discord is None or commands is None:
        raise RuntimeError(
            "discord.py is required to run in bot mode."
            " Install it with `pip install discord.py` or run in CLI mode."
        )

    activation_word = (os.environ.get("ACTIVATION_WORD") or "").strip()
    if (activation_word.startswith('"') and activation_word.endswith('"')) or (
        activation_word.startswith("'") and activation_word.endswith("'")):
        activation_word = activation_word[1:-1].strip()
    allowed_user_id_raw = (os.environ.get("DISCORD_USER_ID") or "").strip()
    allowed_user_id = int(allowed_user_id_raw) if allowed_user_id_raw.isdigit() else None

    discord_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not discord_token:
        raise RuntimeError("DISCORD_BOT_TOKEN environment variable is required.")

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def setup_hook() -> None:
        await bridge.start()

    @bot.event
    async def on_ready() -> None:
        print(f"Logged in as {bot.user}")

    @bot.event
    async def on_message(message: Any) -> None:
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

        # delegate to shared handler which also handles reset/stop/leave logic
        await bridge.process_prompt(content, bridge.send)

    try:
        await bot.start(discord_token)
    finally:
        # bridge closed by caller
        pass
