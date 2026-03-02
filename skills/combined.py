"""Combined MCP server that exposes calendar, miscellaneous, and memory skills."""

import sys

# Add the skills directory to the path so we can import the modules
sys.path.insert(0, '.')

# Import all the tools from both modules
from calender import (
    obtain_oauth_token, list_events, create_event, 
    update_event, delete_event, get_event
)
from misc import edit_env, get_time
from powershell import run_powershell_command
from memory import embed_memory, retrieve_memory, remove_memory
from search import search

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

# Create a combined MCP instance
mcp = FastMCP("Combined Skills", instructions="Calendar, miscellaneous, memory, and search utilities", json_response=True)

# Register all calendar tools
mcp.tool()(obtain_oauth_token)
mcp.tool()(list_events)
mcp.tool()(create_event)
mcp.tool()(update_event)
mcp.tool()(delete_event)
mcp.tool()(get_event)

# Register all misc tools
mcp.tool()(get_time)
mcp.tool()(edit_env)

# Register all memory tools
mcp.tool()(embed_memory)
mcp.tool()(retrieve_memory)
mcp.tool()(remove_memory)


# Register search tools
mcp.tool()(search)

# Register powershell tool
mcp.tool()(run_powershell_command)

def main() -> None:
    """Run the combined MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
