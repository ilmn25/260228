"""Memory utilities backed by Pinecone, exposed as MCP tools."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from functools import lru_cache
from typing import Any

from azure.ai.inference import EmbeddingsClient
from azure.core.credentials import AzureKeyCredential
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from dotenv import load_dotenv
load_dotenv()

from pinecone import Pinecone, ServerlessSpec


class MemoryError(RuntimeError):
	"""Raised when Pinecone memory operations fail."""

mcp = FastMCP(
	"Memory MCP",
	instructions="Store, retrieve, and remove vector memories in Pinecone.",
	json_response=True,
)

def _require_env(name: str) -> str:
	value = os.environ.get(name, "").strip()
	if not value:
		raise MemoryError(f"Missing required environment variable: {name}")
	return value


def _to_embedding_vector(record: Any) -> list[float]:
	if isinstance(record, dict):
		values = record.get("values") or record.get("embedding") or record.get("vector")
		if isinstance(values, list):
			return [float(v) for v in values]

	for attr in ("values", "embedding", "vector"):
		values = getattr(record, attr, None)
		if isinstance(values, list):
			return [float(v) for v in values]

	raise MemoryError("Unable to parse embedding response from Pinecone.")


def _extract_embeddings(response: Any) -> list[Any]:
	if isinstance(response, dict):
		for key in ("data", "embeddings", "result"):
			items = response.get(key)
			if isinstance(items, list):
				return items

	for attr in ("data", "embeddings", "result"):
		items = getattr(response, attr, None)
		if isinstance(items, list):
			return items

	raise MemoryError("Unexpected embedding response payload from Pinecone.")


@lru_cache(maxsize=1)
def _get_client() -> Any:
	if Pinecone is None:
		raise MemoryError("The 'pinecone' package is not installed. Add it to requirements and install dependencies.")

	api_key = _require_env("PINECONE_API_KEY")
	return Pinecone(api_key=api_key)


@lru_cache(maxsize=1)
def _get_embeddings_client() -> EmbeddingsClient:
	github_key = _require_env("GITHUB_TOKEN")
	endpoint = os.environ.get("GITHUB_MODELS_ENDPOINT", "https://models.inference.ai.azure.com")
	return EmbeddingsClient(
		endpoint=endpoint,
		credential=AzureKeyCredential(github_key),
	)


def _index_name() -> str:
	return os.environ.get("PINECONE_INDEX_NAME", "agent-memory").strip() or "agent-memory"


def _namespace() -> str:
	return _require_env("PINECONE_NAMESPACE")


def _ensure_index() -> Any:
	client = _get_client()
	name = _index_name()

	existing_names = set(client.list_indexes().names())
	if name not in existing_names:
		if ServerlessSpec is None:
			raise MemoryError("Pinecone serverless spec is unavailable. Check your pinecone package installation.")

		dimension = int(os.environ.get("PINECONE_DIMENSION", "1536"))
		metric = os.environ.get("PINECONE_METRIC", "cosine")
		cloud = os.environ.get("PINECONE_CLOUD", "aws")
		region = os.environ.get("PINECONE_REGION", "us-east-1")

		client.create_index(
			name=name,
			dimension=dimension,
			metric=metric,
			spec=ServerlessSpec(cloud=cloud, region=region),
		)

		for _ in range(30):
			description = client.describe_index(name)
			status = getattr(description, "status", None)
			if isinstance(status, dict) and status.get("ready"):
				break
			time.sleep(1)

	return client.Index(name)


def _embed_text(text: str, *, input_type: str) -> list[float]:
	_ = input_type
	model = os.environ.get("PINECONE_OPENAI_EMBED_MODEL", "text-embedding-3-small")
	client = _get_embeddings_client()
	response = client.embed(
		model=model,
		input=[text],
	)
	embeddings = _extract_embeddings(response)
	if not embeddings:
		raise MemoryError("Embedding model returned no embeddings.")
	return _to_embedding_vector(embeddings[0])


@mcp.tool()
async def embed_memory(
	ctx: Context[ServerSession, None],
	text: str,
) -> dict[str, Any]:
	"""Embed and store a memory item in Pinecone.

	Args:
		text: Memory content to store.
	"""
	cleaned_text = text.strip()
	if not cleaned_text:
		raise ValueError("text cannot be empty")

	namespace = _namespace()

	vector_id = str(uuid.uuid4())

	vector = await asyncio.to_thread(_embed_text, cleaned_text, input_type="passage")
	index = await asyncio.to_thread(_ensure_index)

	metadata: dict[str, Any] = {
		"text": cleaned_text,
		"created_at": int(time.time()),
	}

	await asyncio.to_thread(
		index.upsert,
		vectors=[{"id": vector_id, "values": vector, "metadata": metadata}],
		namespace=namespace,
	)

	await ctx.info(f"Stored memory {vector_id} in Pinecone namespace '{namespace}'.")
	return {
		"status": "stored",
		"memory_id": vector_id,
		"namespace": namespace,
		"index": _index_name(),
	}


@mcp.tool()
async def retrieve_memory(
	ctx: Context[ServerSession, None],
	query: str,
	top_k: int = 5,
) -> dict[str, Any]:
	"""Retrieve relevant memories from Pinecone by semantic similarity."""
	cleaned_query = query.strip()
	if not cleaned_query:
		raise ValueError("query cannot be empty")

	namespace = _namespace()

	limit = max(1, min(top_k, 20))
	vector = await asyncio.to_thread(_embed_text, cleaned_query, input_type="query")
	index = await asyncio.to_thread(_ensure_index)

	response = await asyncio.to_thread(
		index.query,
		vector=vector,
		top_k=limit,
		include_metadata=True,
		namespace=namespace,
	)

	raw_matches = []
	if isinstance(response, dict):
		raw_matches = response.get("matches", []) or []
	else:
		raw_matches = getattr(response, "matches", []) or []

	matches: list[dict[str, Any]] = []
	for match in raw_matches:
		if isinstance(match, dict):
			metadata = match.get("metadata") or {}
			matches.append(
				{
					"memory_id": match.get("id"),
					"score": match.get("score"),
					"text": metadata.get("text"),
					"metadata": metadata,
				}
			)
			continue

		metadata = getattr(match, "metadata", {}) or {}
		matches.append(
			{
				"memory_id": getattr(match, "id", None),
				"score": getattr(match, "score", None),
				"text": metadata.get("text"),
				"metadata": metadata,
			}
		)

	await ctx.info(f"Retrieved {len(matches)} memory items from namespace '{namespace}'.")
	return {
		"query": cleaned_query,
		"namespace": namespace,
		"top_k": limit,
		"matches": matches,
	}


@mcp.tool()
async def remove_memory(
	ctx: Context[ServerSession, None],
	memory_id: str,
) -> dict[str, Any]:
	"""Delete a memory vector from Pinecone by ID."""
	vector_id = memory_id.strip()
	if not vector_id:
		raise ValueError("memory_id cannot be empty")

	namespace = _namespace()

	index = await asyncio.to_thread(_ensure_index)
	await asyncio.to_thread(index.delete, ids=[vector_id], namespace=namespace)
	await ctx.info(f"Removed memory {vector_id} from namespace '{namespace}'.")
	return {
		"status": "removed",
		"memory_id": vector_id,
		"namespace": namespace,
		"index": _index_name(),
	}


def main() -> None:
	mcp.run()


if __name__ == "__main__":
	main()
