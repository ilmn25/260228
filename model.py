"""LLM model interaction logic for Azure AI inference."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
import google.generativeai as genai
from ollama import Client
from dotenv import load_dotenv
load_dotenv()


@dataclass
class AzureModelsClient:
    """Client for interacting with Azure AI inference API."""

    def __post_init__(self):
        # Read configuration from environment variables
        self.token = os.environ.get("GITHUB_TOKEN", "")
        if not self.token:
            raise RuntimeError("GITHUB_TOKEN environment variable is required")
        
        self.model = os.environ.get("AZURE_MODEL", "gpt-4o-mini")
        self.endpoint = os.environ.get("AZURE_ENDPOINT", "https://models.inference.ai.azure.com")
        
        # create the Azure ChatCompletionsClient once
        self.client = ChatCompletionsClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.token),
        )

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        """Call the LLM and return the raw response content."""
        response = self.client.complete(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message["content"].strip()


@dataclass
class GitHubModelsClient:
    """Client for interacting with GitHub Models API."""

    def __post_init__(self):
        # Read configuration from environment variables
        self.token = os.environ.get("GITHUB_TOKEN", "")
        if not self.token:
            raise RuntimeError("GITHUB_TOKEN environment variable is required")
        
        self.model = os.environ.get("GITHUB_MODEL", "gpt-4o-mini")
        self.endpoint = "https://models.inference.ai.azure.com"
        
        # create the ChatCompletionsClient for GitHub Models
        self.client = ChatCompletionsClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.token),
        )

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        """Call the LLM and return the raw response content."""
        response = self.client.complete(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message["content"].strip()


@dataclass
class GeminiClient:
    """Client for interacting with Google Gemini API."""

    def __post_init__(self):
        if not genai:
            raise RuntimeError(
                "google-generativeai package is required. Install it with: pip install google-generativeai"
            )
        
        # Read configuration from environment variables
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is required")
        
        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        
        # Configure the Gemini API
        genai.configure(api_key=self.api_key)
        self.client = genai.GenerativeModel(self.model)

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        """Call the LLM and return the raw response content."""
        # Convert messages to Gemini format
        contents = self._format_messages_for_gemini(messages)
        response = self.client.generate_content(
            contents,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
            ),
        )
        return response.text.strip()

    @staticmethod
    def _format_messages_for_gemini(messages: list[dict[str, str]]) -> list:
        """Convert standard message format to Gemini format."""
        formatted = []
        for msg in messages:
            role = "user" if msg.get("role") == "user" else "model"
            formatted.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}]
            })
        return formatted

@dataclass
class OllamaClient:
    """Client for interacting with Ollama API."""

    def __post_init__(self):
        self.model = os.environ.get("OLLAMA_MODEL", "llama3")
        self.endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
        self.api_key = os.environ.get("OLLAMA_API_KEY", "")
        
        # Create the Ollama client with host and optional headers
        headers = {}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        self.client = Client(
            host=self.endpoint,
            headers=headers if headers else None
        )

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        """Call the LLM and return the raw response content."""
        full_response = ""
        
        # Use the client.chat method with streaming
        for part in self.client.chat(
            model=self.model,
            messages=messages,
            stream=True,
            options={
                "temperature": temperature,
            }
        ):
            if 'message' in part and 'content' in part['message']:
                full_response += part['message']['content']
        
        return full_response.strip()


def parse_model_response(raw: str, tool_names: set[str] | None = None) -> dict[str, Any]:
    """
    Parse and normalize the LLM response into a command dict.
    
    Returns a dict with:
    - action: "tool", "final", "ask", or "leave"
    - tool: tool name (if action is "tool")
    - arguments: tool arguments (if action is "tool")
    - message/question: content for final/ask/leave actions
    """
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


async def process_llm_response(
    client: AzureModelsClient | GitHubModelsClient | GeminiClient | OllamaClient,
    messages: list[dict[str, str]],
    tool_names: set[str] | None = None,
) -> dict[str, Any]:
    """
    Process messages through the LLM and return parsed command.
    
    Args:
        client: AzureModelsClient or GitHubModelsClient instance
        messages: conversation messages
        tool_names: set of available tool names for normalization
    
    Returns:
        Parsed command dict from parse_model_response
    """
    raw_response = client.complete(messages)
    return parse_model_response(raw_response, tool_names)
