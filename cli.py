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


    # ensure the agent is started (idempotent)
    await bridge.start()
    # CLI channel needs an async ``send`` method; print is synchronous so wrap
    # it in an async function.
    async def _cli_send(message: str) -> None:  # noqa: D401
        print(message)

    bridge.set_channel(SimpleNamespace(send=_cli_send))

    print(
        "Starting persistent agent. Type prompts, ask to 'reset' conversation, or type 'exit' to quit."
    )

    while True:
        prompt_text = await asyncio.to_thread(input, "> ")
        if not prompt_text:
            continue
        stripped = prompt_text.strip()
        if stripped in ("/exit", "exit"):
            print("Exiting persistent agent.")
            break

        await bridge.process_prompt(prompt_text, bridge.send)

    await bridge.close()
