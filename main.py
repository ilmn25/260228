"""Multi-interface runner with built-in terminal CLI.

Starts the shared agent bridge and optionally the Discord bot if a token
is provided or ``--bot`` is passed.  The CLI is always active; other
integrations can be added in the same way.
"""

from __future__ import annotations
import sys
from pathlib import Path
import asyncio
import os
from dotenv import load_dotenv
import log

# make sure the parent folder is on sys.path for local imports
parent = str(Path(__file__).resolve().parent.parent)
if parent not in sys.path:
    sys.path.insert(0, parent)

load_dotenv()

from bridge import AgentBridge
from cli import run_terminal_cli
from discord_bot import _run_discord


if __name__ == "__main__":
    use_cli = True
    args = sys.argv[1:]
    use_bot = ("--bot" in args or "bot" in args or
               bool(os.environ.get("DISCORD_BOT_TOKEN")))

    log.clear()
    async def entry() -> None:
        bridge = AgentBridge()
        tasks: list[asyncio.Task] = []

        if use_bot:
            tasks.append(asyncio.create_task(_run_discord(bridge)))
        if use_cli:
            tasks.append(asyncio.create_task(run_terminal_cli(bridge)))

        if tasks:
            await asyncio.gather(*tasks)
        else:
            print("Nothing to run; specify --bot or set DISCORD_BOT_TOKEN.")

    asyncio.run(entry())
