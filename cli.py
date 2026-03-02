"""Minimal MCP-aware agent that uses an Azure AI inference endpoint for reasoning.

Usage
-----
1. Install deps: pip install "mcp[cli]" requests azure-ai-inference azure-core
2. Configure environment variables (required):
    setx GITHUB_TOKEN <your-token>
3. Ensure the MCP server can be launched via the configured command.
4. Start the persistent agent REPL: 
    python cli.py
   Type prompts at the `agent>` prompt. Use `/reset` to clear conversation and `/exit` to quit.

Environment Variables
---------------------
GITHUB_TOKEN (required): GitHub token for Azure inference
AZURE_MODEL (optional): Model identifier (default: gpt-4o-mini)
MCP_SERVER_COMMAND (optional): Command to launch MCP server (default: python)
MCP_SERVER_ARGS (optional): Arguments for MCP server (default: skills/combined.py)
"""

from __future__ import annotations

import asyncio

from agent import AgentManager
from prompts import SYSTEM_PROMPT


async def run_agent() -> None:
    manager = AgentManager()

    try:
        agent = await manager.start(SYSTEM_PROMPT)
        
        # Persistent REPL mode (always): spawn server once and accept many prompts.
        print("Starting persistent agent. Type prompts, `/reset` to clear conversation, `/exit` to quit.")

        while True:
            prompt_text = await asyncio.to_thread(input, "agent> ")
            if not prompt_text:
                continue
            if prompt_text.strip() in ("/exit", "exit"):
                print("Exiting persistent agent.")
                break
            if prompt_text.strip() == "/reset":
                agent.reset_conversation()
                print("Conversation reset.")
                continue

            try:
                result = await agent.run_prompt(prompt_text)
                
                while True:
                    action = result.get("action")

                    if action == "final":
                        print(result.get("message", "Done."))
                        print("=====================================\n")
                        break

                    if action == "ask":
                        question = result.get("question", "Please provide more information:")
                        print(f"agent: {question}")
                        user_answer = await asyncio.to_thread(input, "you> ")
                        result = await agent.continue_with_user_input(user_answer)
                        continue

                    if action == "stop":
                        print(result.get("message", "Stopped."))
                        print("=====================================\n")
                        break

                    # Unexpected action
                    print(f"Unexpected action: {action}")
                    break

            except Exception as e:
                print(f"Error: {e}")
                print("Agent finalizing due to error.")
    finally:
        await manager.close()


if __name__ == "__main__":
    asyncio.run(run_agent())
