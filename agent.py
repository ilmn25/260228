"""Minimal MCP-aware agent that uses an Azure AI inference endpoint for reasoning.
Usage
-----
1. Install deps: pip install "mcp[cli]" requests azure-ai-inference azure-core
2. Export a GitHub token with access to the inference deployment:
    setx GITHUB_TOKEN <your-token>
3. Ensure the MCP server (calender.py) can be launched via `python calender.py`.
4. Start the persistent agent REPL:
    python agent.py
   Type prompts at the `agent>` prompt. Use `/reset` to clear conversation and `/exit` to quit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Iterable

from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

# Optional .env support for local development. If python-dotenv is installed,
# this will load environment variables from a `.env` file in the working dir.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # dotenv is optional; fall back to environment variables.
    pass

SYSTEM_PROMPT = """
You are an autonomous planner that can call a set of planning tools via MCP.
You MUST respond with ONLY a single JSON object. No explanation, no markdown, no extra text.

The JSON must follow EXACTLY one of these three shapes:

To call a tool for information or an operation:
{"action":"tool","tool":"<tool-name>","arguments":{...}}

To ask the user for missing information:
{"action":"ask","question":"<question-for-user>"}

To finish:
{"action":"final","message":"<human-readable summary>"}

Rules:
- "action" must be EXACTLY "tool", "ask", or "final"
- execute the target operation once you have sufficient information.
- finish with a clear summary of what was accomplished.

[Calendar Tool]
For update_event, delete_event, get_event:
1. Use list_events first to get a list of all events and then search for the existing event's id and information
2. For update_event: omitted fields (start_time, end_time, location, description, attendees) uses existing event's information

Available tools:
""".strip()


@dataclass
class AzureModelsClient:
    token: str
    model: str = "gpt-4o-mini"
    endpoint: str = "https://models.inference.ai.azure.com"
    max_calls_per_prompt: int = 10  # Safety limit to prevent endpoint spam

    def __post_init__(self):
        # create the Azure ChatCompletionsClient once
        self.client = ChatCompletionsClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.token),
        )
        self.call_count = 0

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        self.call_count += 1
        if self.call_count > self.max_calls_per_prompt:
            raise RuntimeError(
                f"Azure API call limit exceeded ({self.max_calls_per_prompt} calls per prompt). "
                "This likely indicates a loop bug. Please review your request."
            )
        response = self.client.complete(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message["content"].strip()
    
    def reset_call_count(self) -> None:
        """Reset the call counter for a new prompt."""
        self.call_count = 0


def describe_tools(tools: Iterable[types.Tool]) -> str:
    lines = []
    for tool in tools:
        sig = tool.name
        if tool.inputSchema:
            sig += f"(arguments: {list(tool.inputSchema.get('properties', {}).keys())})"
        desc = tool.description or "no description"
        lines.append(f"- {sig}: {desc}")
    return "\n".join(lines)


def parse_agent_command(raw: str, tool_names: set[str] | None = None) -> dict[str, Any]:
    try:
        cmd = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Model response was not valid JSON. Raw response:\n{raw}"
        ) from exc

    # Normalize off-schema responses like:
    # {"action":"create_event","payload":{...}}
    action = cmd.get("action")
    if action not in ("tool", "final", "ask") and tool_names and action in tool_names:
        args = cmd.get("arguments") or cmd.get("payload") or cmd.get("params") or cmd.get("fields") or {}
        cmd = {"action": "tool", "tool": action, "arguments": args}
    
    # Also normalize if action is 'tool' but using wrong parameter name
    if action == "tool" and "arguments" not in cmd:
        cmd["arguments"] = cmd.get("fields") or cmd.get("payload") or cmd.get("params") or {}

    return cmd


def serialize_tool_result(result: types.CallToolResult) -> dict[str, Any]:
    structured = result.structuredContent
    text_blocks = []
    for content in result.content:
        if isinstance(content, types.TextContent):
            text_blocks.append(content.text)
    text = "\n".join(text_blocks)
    return {"structured": structured, "text": text}


async def run_agent(args: argparse.Namespace) -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN environment variable is required for the Azure inference API.")

    gh_client = AzureModelsClient(token=token, model=args.model)
    server_params = StdioServerParameters(command=args.server_command, args=args.server_args)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_response = await session.list_tools()
            tool_descriptions = describe_tools(tools_response.tools)
            tool_names = {tool.name for tool in tools_response.tools}

            system_block = {"role": "system", "content": f"{SYSTEM_PROMPT}\n{tool_descriptions}"}

            # Persistent REPL mode (always): spawn server once and accept many prompts.
            print("Starting persistent agent. Type prompts, `/reset` to clear conversation, `/exit` to quit.")
            conversation: list[dict[str, str]] = [system_block]

            while True:
                prompt_text = await asyncio.to_thread(input, "agent> ")
                if not prompt_text:
                    continue
                if prompt_text.strip() in ("/exit", "exit"):
                    print("Exiting persistent agent.")
                    break
                if prompt_text.strip() == "/reset":
                    conversation = [system_block]
                    print("Conversation reset.")
                    continue

                conversation.append({"role": "user", "content": prompt_text})

                try:
                    gh_client.reset_call_count()  # Reset counter for new prompt
                    while True:
                        model_reply = gh_client.complete(conversation) 
                        command = parse_agent_command(model_reply, tool_names) 
                        
                        tool_name = command.get("tool")

                        if command.get("action") == "final":
                            print(command.get("message", "Done."))
                            conversation.append({"role": "assistant", "content": model_reply})
                            print("=====================================\n")
                            break

                        if command.get("action") == "ask":
                            question = command.get("question", "Please provide more information:")
                            print(f"agent: {question}")
                            user_answer = await asyncio.to_thread(input, "you> ")
                            conversation.extend([
                                {"role": "assistant", "content": model_reply},
                                {"role": "user", "content": user_answer}
                            ])
                            continue

                        if command.get("action") != "tool":
                            raise RuntimeError(f"Unknown action from model: {command}")

                        if tool_name not in tool_names:
                            raise RuntimeError(f"Model requested unknown tool: {tool_name}")

                        print(f"Model calling tool: {command.get('tool')}()")
                        arguments = command.get("arguments") or {}
                        if not isinstance(arguments, dict):
                            arguments = {}
                        
                        tool_result: types.CallToolResult = await session.call_tool(tool_name, arguments)
                        result_payload = serialize_tool_result(tool_result)
                        conversation.extend(
                            [
                                {"role": "assistant", "content": model_reply},
                                {
                                    "role": "user",
                                    "content": json.dumps(
                                        {
                                            "tool": tool_name,
                                            "result": result_payload,
                                        }
                                    ),
                                },
                            ]
                        )
                except Exception as e:
                    print(f"Error: {e}")
                    print("Agent finalizing due to error.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Custom MCP agent powered by Azure inference service")
    # persistent-only agent: no positional prompt, interact via REPL
    parser.add_argument(
        "--server-command",
        default="python",
        help="Executable used to launch the MCP server (defaults to python)",
    )
    parser.add_argument(
        "--server-args",
        nargs=argparse.REMAINDER,
        default=["skills/calender.py"],
        help="Arguments passed to the MCP server command",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="GitHub Models identifier (see https://docs.github.com/en/github-models)",
    )
    return parser


if __name__ == "__main__":
    cli_args = build_arg_parser().parse_args()
    asyncio.run(run_agent(cli_args))
