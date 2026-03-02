"""Search utilities backed by LangSearch API, exposed as MCP tools."""

from __future__ import annotations

import os
from typing import Any

import requests
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

try:
	from dotenv import load_dotenv

	load_dotenv()
except Exception:
	pass


class SearchError(RuntimeError):
	"""Raised when LangSearch operations fail."""


mcp = FastMCP(
	"Search MCP",
	instructions="Search the web using LangSearch API.",
	json_response=True,
)


def _require_env(name: str) -> str:
	value = os.environ.get(name, "").strip()
	if not value:
		raise SearchError(f"Missing required environment variable: {name}")
	return value


@mcp.tool()
async def search(
	ctx: Context[ServerSession, None],
	query: str,
	language: str = "en",
	max_results: int = 5,
) -> dict[str, Any]:
	"""Search the web using LangSearch API.

	Args:
		query: Search query string.
		language: Language code (e.g., 'en', 'es', 'fr'). Defaults to 'en'.
		max_results: Maximum number of results to return (1-20). Defaults to 5.
	"""
	cleaned_query = query.strip()
	if not cleaned_query:
		raise ValueError("query cannot be empty")

	api_key = _require_env("LANGSEARCH_KEY")
	max_results = max(1, min(max_results, 20))

	url = "https://api.langsearch.com/v1/search"
	headers = {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json",
	}
	payload = {
		"query": cleaned_query,
		"language": language,
		"max_results": max_results,
	}

	try:
		response = requests.post(url, headers=headers, json=payload, timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise SearchError(f"LangSearch API request failed: {exc}") from exc

	data = response.json()
	results = []
	for item in data.get("results", []):
		results.append(
			{
				"title": item.get("title"),
				"url": item.get("url"),
				"snippet": item.get("snippet"),
				"source": item.get("source"),
			}
		)

	await ctx.info(f"Retrieved {len(results)} search results for '{cleaned_query}'.")
	return {
		"query": cleaned_query,
		"language": language,
		"result_count": len(results),
		"results": results,
	}


def main() -> None:
	mcp.run()


if __name__ == "__main__":
	main()
