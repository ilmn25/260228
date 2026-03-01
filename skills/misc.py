"""Miscellaneous utilities exposed via MCP tools."""

from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from mcp.server.session import ServerSession
from mcp.server.fastmcp import Context

mcp = FastMCP("Miscellaneous MCP", instructions="Utility tools", json_response=True)


@mcp.tool()
async def get_time(ctx: Context[ServerSession, None]) -> dict[str, str]:
    """Return the current UTC time in ISO 8601 format."""
    now = datetime.now(timezone.utc).isoformat()
    await ctx.info(f"Current time is {now}")
    return {"utc_time": now}


def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
