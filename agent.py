"""Minimal MCP-aware agent that uses GitHub Models (OpenAI family) for reasoning.

Usage
-----
1. Install deps: pip install "mcp[cli]" requests
2. Export a GitHub token with access to Models API (free tier works). The token
   must have `models:read` permission and will be sent to a Microsoft service:
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

import requests
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
You are an autonomous planner that can call Google Calendar tools via MCP.
You MUST respond with ONLY a single JSON object. No explanation, no markdown, no extra text.

The JSON must follow EXACTLY one of these two shapes:

To call a tool:
{"action":"tool","tool":"<tool-name>","arguments":{...}}

To finish:
{"action":"final","message":"<human-readable summary>"}

Rules:
- "action" must be EXACTLY "tool" or "final". Never use a tool name as the action value.
- "tool" must be one of the available tool names listed below.
- "arguments" must match the fields listed for that tool.
- Do NOT use "payload", "params", or any other key instead of "arguments".

Example tool call (ALWAYS include timezone for create_event and update_event):
{"action":"tool","tool":"create_event","arguments":{"summary":"Team sync","start_time":"2026-03-02T10:00:00","end_time":"2026-03-02T10:30:00","timezone":"Asia/Hong_Kong"}}

If the user does not specify a timezone, default to "Asia/Hong_Kong".

Example finish:
{"action":"final","message":"Done. Created the event successfully."}
""".strip()


@dataclass
class GitHubModelsClient:
    token: str
    model: str = "openai/gpt-4o"
    endpoint: str = "https://models.github.ai/inference/chat/completions"

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Client-Name": "mcp-gcal-agent",
            "X-Client-Version": "1.0",
        }
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": messages,
        }
        response = requests.post(self.endpoint, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:  # pragma: no cover (API contract)
            raise RuntimeError(f"Unexpected model response: {data}") from exc


def describe_tools(tools: Iterable[types.Tool]) -> str:
    lines = []
    for tool in tools:
        sig = tool.name
        if tool.inputSchema:
            sig += f"(fields: {list(tool.inputSchema.get('properties', {}).keys())})"
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
    if action not in ("tool", "final") and tool_names and action in tool_names:
        args = cmd.get("arguments") or cmd.get("payload") or cmd.get("params") or {}
        cmd = {"action": "tool", "tool": action, "arguments": args}

    return cmd


def _default_timezone() -> str:
    return (
        os.environ.get("GOOGLE_CALENDAR_TIMEZONE")
        or os.environ.get("DEFAULT_TIMEZONE")
        or "Asia/Hong_Kong"
    )


def _normalize_event_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_name not in {"create_event", "update_event"}:
        return arguments

    normalized = dict(arguments)

    # Accept alternative model shapes:
    # - payload: {start: {dateTime, timeZone}, end: {dateTime, timeZone}}
    # - payload: {start_time, end_time, timezone}
    start_obj = normalized.get("start")
    end_obj = normalized.get("end")

    if isinstance(start_obj, dict) and "start_time" not in normalized:
        if isinstance(start_obj.get("dateTime"), str):
            normalized["start_time"] = start_obj["dateTime"]
        if isinstance(start_obj.get("timeZone"), str) and not normalized.get("timezone"):
            normalized["timezone"] = start_obj["timeZone"]

    if isinstance(end_obj, dict) and "end_time" not in normalized:
        if isinstance(end_obj.get("dateTime"), str):
            normalized["end_time"] = end_obj["dateTime"]
        if isinstance(end_obj.get("timeZone"), str) and not normalized.get("timezone"):
            normalized["timezone"] = end_obj["timeZone"]

    # Ensure timezone fallback for event operations.
    if not normalized.get("timezone"):
        normalized["timezone"] = _default_timezone()

    return normalized


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
        raise RuntimeError("GITHUB_TOKEN environment variable is required for GitHub Models API.")

    gh_client = GitHubModelsClient(token=token, model=args.model)
    server_params = StdioServerParameters(command=args.server_command, args=args.server_args)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_response = await session.list_tools()
            tool_descriptions = describe_tools(tools_response.tools)
            tool_names = {tool.name for tool in tools_response.tools}

            system_block = {"role": "system", "content": f"{SYSTEM_PROMPT}\nAvailable tools:\n{tool_descriptions}"}

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

                while True:
                    model_reply = gh_client.complete(conversation)
                    command = parse_agent_command(model_reply, tool_names)

                    if command.get("action") == "final":
                        print(command.get("message", "Done."))
                        conversation.append({"role": "assistant", "content": model_reply})
                        break

                    if command.get("action") != "tool":
                        raise RuntimeError(f"Unknown action from model: {command}")

                    tool_name = command.get("tool")
                    if tool_name not in tool_names:
                        raise RuntimeError(f"Model requested unknown tool: {tool_name}")

                    arguments = command.get("arguments") or {}
                    if not isinstance(arguments, dict):
                        arguments = {}
                    arguments = _normalize_event_arguments(tool_name, arguments)
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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Custom MCP agent powered by GitHub Models")
    # persistent-only agent: no positional prompt, interact via REPL
    parser.add_argument(
        "--server-command",
        default="python",
        help="Executable used to launch the MCP server (defaults to python)",
    )
    parser.add_argument(
        "--server-args",
        nargs=argparse.REMAINDER,
        default=["calender.py"],
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
