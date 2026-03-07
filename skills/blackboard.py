"""Playwright helpers for PolyU Blackboard login."""

from __future__ import annotations

import os

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from playwright.async_api import async_playwright


class BlackboardError(RuntimeError):
    """Raised when Blackboard login automation fails."""


async def login(ctx: Context[ServerSession, None]) -> bool:
    """
    Args:
        ctx: MCP context
    Returns:
        True if login successful, else raises BlackboardError
    """
    if async_playwright is None:  # type: ignore
        raise BlackboardError(
            "Playwright is not available in this Python environment."
        )

    username = os.environ.get("BB_USERNAME", "")
    password = os.environ.get("BB_PASSWORD", "")

    if not username or not password:
        raise BlackboardError("username and password must be provided")

    url = "https://learn.polyu.edu.hk/"

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)
            page = await browser.new_page()
            await page.goto(url)

            # Match the NetID login form fields.
            await page.fill("#userNameInput, input[name='UserName']", username)
            await page.fill("#passwordInput, input[name='Password']", password)
            await page.click("#submitButton")
            await ctx.info(f"Navigated to {page.url}")
            return True
    except Exception as exc:  # noqa: BLE001
        raise BlackboardError(f"Playwright login failed: {exc}") from exc
