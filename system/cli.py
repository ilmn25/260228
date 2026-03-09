"""Terminal CLI interface.

Provides a simple REPL that drives a shared ``AgentBridge`` instance.
"""

from __future__ import annotations
import asyncio
from types import SimpleNamespace

from bridge import AgentBridge

async def run_terminal_cli(bridge: AgentBridge | None = None) -> None:
    """Run the agent in a simple terminal REPL.

    ``bridge`` may be provided when the CLI runs alongside another
    interface (for example, the Discord bot); otherwise a fresh bridge
    is created.
    """
    if bridge is None:
        bridge = AgentBridge()

    await bridge.start()
    async def _cli_send(message: str) -> None:  # noqa: D401
        print(message)

    bridge.set_channel(SimpleNamespace(send=_cli_send))

    try:
        while True:
            try:
                prompt_text = await asyncio.to_thread(input, "> ")
            except EOFError:
                print("Input closed, exiting.")
                break

            if not prompt_text:
                continue

            await bridge.process_prompt(prompt_text, bridge.send)
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, shutting down.")
    finally:
        await bridge.close()
