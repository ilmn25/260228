"""Unified agent logic for MCP-aware interactions with Azure AI inference."""

from __future__ import annotations

import sys
from pathlib import Path

parent = str(Path(__file__).resolve().parent.parent)
if parent not in sys.path:
    sys.path.insert(0, parent)

import log
import json
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from system.model import AzureModelsClient, GitHubModelsClient, GeminiClient, OllamaClient, parse_model_response

# Optional .env support
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def describe_tools(tools: Iterable[types.Tool]) -> str:
    lines = []
    for tool in tools:
        sig = tool.name
        if tool.inputSchema:
            sig += f"(arguments: {list(tool.inputSchema.get('properties', {}).keys())})"
        desc = tool.description or "no description"
        lines.append(f"- {sig}: {desc}")
    return "\n".join(lines)


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
        gh_client: AzureModelsClient | GitHubModelsClient | GeminiClient | OllamaClient,
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
        command = parse_model_response(model_reply, self.tool_names)
        log.add(str(command))
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

        return await self.run_prompt_internal(on_tool_call)

    def reset_conversation(self) -> None:
        """Reset conversation to initial system block."""
        log.clear()
        if self.conversation:
            system_block = self.conversation[0]
            self.conversation = [system_block]


class AgentManager:
    """Manages MCP session lifecycle and Agent creation."""

    def __init__(
        self,
        extra_system_prompt: str = "",
    ):
        # Read MCP server configuration from environment variables
        self.server_command = os.environ.get("MCP_SERVER_COMMAND", "python")
        self.server_args = os.environ.get("MCP_SERVER_ARGS", "skills/mcp_server.py").split()
        self.model_provider = os.environ.get("MODEL_PROVIDER", "gemini")  # "azure", "github", "gemini", or "ollama"
        self.extra_system_prompt = extra_system_prompt
        self.gh_client: AzureModelsClient | GitHubModelsClient | GeminiClient | OllamaClient | None = None
        self._exit_stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.agent: Agent | None = None

    async def start(self, base_system_prompt: str) -> Agent:
        """Initialize the MCP session and create an Agent."""
        if self.model_provider == "github":
            self.gh_client = GitHubModelsClient()
        elif self.model_provider == "gemini":
            self.gh_client = GeminiClient()
        elif self.model_provider == "ollama":
            self.gh_client = OllamaClient()
        else:
            self.gh_client = AzureModelsClient()
        
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
