"""Resume and job-application related MCP tools."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

parent = str(Path(__file__).resolve().parent.parent)
if parent not in sys.path:
	sys.path.insert(0, parent)

from gmail import create_draft
from prompts.system import JOB_DRAFT_SYSTEM_PROMPT
from system.model import get_model_client


def _parse_generated_email(raw: str) -> tuple[str, str]:
	try:
		data: dict[str, Any] = json.loads(raw)
	except json.JSONDecodeError:
		start = raw.find("{")
		if start < 0:
			raise ValueError(f"Model response is not valid JSON: {raw}")
		decoder = json.JSONDecoder()
		data, _ = decoder.raw_decode(raw[start:])

	subject = str(data.get("subject", "")).strip()
	body = str(data.get("body", "")).strip()

	if not subject:
		subject = "Application Interest"
	if not body:
		raise ValueError("Generated email body is empty")

	return subject, body


async def draft_job_email(
	ctx: Context[ServerSession, None],
	receiver_name: str,
	job_info: str,
) -> dict[str, str]:
	"""Generate a tailored job email and create a Gmail draft.

	Args:
		receiver_name: Receiver name string.
		job_info: Job information string used for tailoring the email.

	Returns:
		Dictionary containing the created draft email ID.
	"""
	receiver_name = receiver_name.strip()
	job_info = job_info.strip()

	if not receiver_name:
		raise ValueError("receiver_name is required")
	if not job_info:
		raise ValueError("job_info is required")

	provider = os.environ.get("MODEL_PROVIDER", "gemini")
	client = get_model_client(provider, reuse=True)
	messages = [
		{"role": "system", "content": JOB_DRAFT_SYSTEM_PROMPT},
		{
			"role": "user",
			"content": (
				f"Receiver name: {receiver_name}\n"
				f"Job info:\n{job_info}"
			),
		},
	]

	raw = client.complete(messages, temperature=0.3)
	subject, body = _parse_generated_email(raw)

	draft_result = await create_draft(
		ctx=ctx,
		to=receiver_name,
		subject=subject,
		body=body,
	)

	draft_id = draft_result.get("draft_id", "")
	if not draft_id:
		raise RuntimeError(f"Draft creation failed: {draft_result}")

	return {"draft_id": draft_id}
