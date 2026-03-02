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
import json

from agent import AgentManager
from prompts import SYSTEM_PROMPT


def log_to_file(message: str, log_file: str = "agent_output.log") -> None:
    """Append message to log file."""
    with open(log_file, 'a') as f:
        f.write(message + '\n')


def print_and_log(message: str, log_file: str = "agent_output.log") -> None:
    """Print to console and log to file."""
    print(message)
    log_to_file(message, log_file)


async def run_agent() -> None:
    manager = AgentManager()
    log_file = "agent_output.log"
    
    # Clear log file at start
    open(log_file, 'w').close()

    try:
        agent = await manager.start(SYSTEM_PROMPT)
        print("Starting persistent agent. Type prompts, `/reset` to clear conversation, `/exit` to quit.")

        while True:
            prompt_text = await asyncio.to_thread(input, "> ")
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
                
                # Log the full JSON result
                result_json = json.dumps(result, indent=2, default=str)
                log_to_file(result_json, log_file)
                
                while True:
                    action = result.get("action")

                    if action == "final":
                        message = result.get("message", "Done.")
                        print(message)
                        print("=====================================")
                        break

                    if action == "ask":
                        question = result.get("question", "Please provide more information:")
                        print(f"agent: {question}")
                        user_answer = await asyncio.to_thread(input, "> ")
                        result = await agent.continue_with_user_input(user_answer)
                        continue

                    if action == "stop":
                        message = result.get("message", "Stopped.")
                        print(message)
                        print("=====================================")
                        break

                    # Unexpected action
                    print(f"Unexpected action: {action}")
                    break

            except Exception as e:
                error_msg = str(e)
                print(f"Error: {error_msg}")
                print("Agent finalizing due to error.")
    finally:
        await manager.close()


if __name__ == "__main__":
    asyncio.run(run_agent())
