"""Unified agent logic for MCP-aware interactions with Azure AI inference."""

from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable

from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

# Optional .env support
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


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
    if action not in ("tool", "final", "ask", "leave") and tool_names and action in tool_names:
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


class Agent:
    """Unified agent for tool-calling interactions with MCP servers."""

    def __init__(
        self,
        gh_client: AzureModelsClient,
        session: ClientSession,
        tool_names: set[str],
        initial_conversation: list[dict[str, str]],
    ):
        self.gh_client = gh_client
        self.session = session
        self.tool_names = tool_names
        self.conversation = initial_conversation
        self._stop_requested = False

    def request_stop(self) -> None:
        """Request the agent to stop processing."""
        self._stop_requested = True

    async def _process_once(
        self,
        on_tool_call: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """
        Process one step in the agent loop.
        Returns decision from the model.
        """
        if not self.session:
            raise RuntimeError("MCP session is not initialized.")

        if self._stop_requested:
            return {"action": "stop", "message": "Operation stopped."}

        model_reply = self.gh_client.complete(self.conversation)
        command = parse_agent_command(model_reply, self.tool_names)
        action = command.get("action")

        if action == "final":
            self.conversation.append({"role": "assistant", "content": model_reply})
            return {
                "action": "final",
                "message": command.get("message", ""),
            }

        if action == "ask":
            self.conversation.append({"role": "assistant", "content": model_reply})
            return {
                "action": "ask",
                "question": command.get("question", "Please provide more information."),
            }

        if action == "leave":
            self.conversation.append({"role": "assistant", "content": model_reply})
            return {
                "action": "leave",
                "message": command.get("message", ""),
            }

        if action != "tool":
            raise RuntimeError(f"Unknown action from model: {command}")

        tool_name = command.get("tool")
        if tool_name not in self.tool_names:
            raise RuntimeError(f"Model requested unknown tool: {tool_name}")

        tool_msg = f"Model calling tool: {tool_name}()"
        if on_tool_call:
            await on_tool_call(tool_msg)

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
        return {"action": "tool"}

    async def continue_with_user_input(
        self,
        user_input: str,
        on_tool_call: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """
        Continue processing after an 'ask' action with user input.
        Appends the user input to conversation and continues the agent loop.
        """
        self.conversation.append({"role": "user", "content": user_input})
        return await self.run_prompt_internal(on_tool_call)

    async def run_prompt_internal(
        self,
        on_tool_call: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Internal loop that processes until a terminal action is reached."""
        while True:
            result = await self._process_once(on_tool_call)
            action = result.get("action")

            if action in ("final", "ask", "leave", "stop"):
                return result

            # action == "tool": just continue the loop

    async def run_prompt(
        self,
        prompt_text: str,
        on_tool_call: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """
        Run a single prompt and return the result.
        
        Returns a dict with keys:
        - action: "final", "ask", or "leave"
        - message/question: the content for that action
        """
        if not self.session:
            raise RuntimeError("MCP session is not initialized.")

        self._stop_requested = False
        self.conversation.append({"role": "user", "content": prompt_text})
        self.gh_client.reset_call_count()

        return await self.run_prompt_internal(on_tool_call)

    def reset_conversation(self) -> None:
        """Reset conversation to initial system block."""
        if self.conversation:
            system_block = self.conversation[0]
            self.conversation = [system_block]


class AgentManager:
    """Manages MCP session lifecycle and Agent creation."""

    def __init__(
        self,
        extra_system_prompt: str = "",
        max_calls_per_prompt: int = 10,
    ):
        # Read all configuration from environment variables
        self.token = os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise RuntimeError("GITHUB_TOKEN environment variable is required")
        
        self.model = os.environ.get("AZURE_MODEL", "gpt-4o-mini")
        self.server_command = os.environ.get("MCP_SERVER_COMMAND", "python")
        self.server_args = os.environ.get("MCP_SERVER_ARGS", "skills/combined.py").split()
        self.max_calls_per_prompt = max_calls_per_prompt
        self.extra_system_prompt = extra_system_prompt
        self.gh_client: AzureModelsClient | None = None
        self._exit_stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.agent: Agent | None = None

    async def start(self, base_system_prompt: str) -> Agent:
        """Initialize the MCP session and create an Agent."""
        self.gh_client = AzureModelsClient(
            token=self.token,
            model=self.model,
            max_calls_per_prompt=self.max_calls_per_prompt,
        )
        
        server_params = StdioServerParameters(
            command=self.server_command,
            args=self.server_args
        )
        read, write = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self.session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )

        await self.session.initialize()
        tools_response = await self.session.list_tools()
        tool_names = {tool.name for tool in tools_response.tools}
        tool_descriptions = describe_tools(tools_response.tools)
        
        system_content = base_system_prompt
        if self.extra_system_prompt:
            system_content = f"{system_content}\n{self.extra_system_prompt}"
        system_content = f"{system_content}\n{tool_descriptions}"
        
        system_block = {"role": "system", "content": system_content}
        
        self.agent = Agent(
            self.gh_client,
            self.session,
            tool_names,
            [system_block],
        )
        return self.agent

    async def close(self) -> None:
        """Clean up the MCP session."""
        await self._exit_stack.aclose()
