"""Combined MCP server that exposes calendar, system, and memory skills."""

import sys
from pathlib import Path

# Add the skills directory to the path so we can import the modules
skills_dir = str(Path(__file__).resolve().parent)
if skills_dir not in sys.path:
    sys.path.insert(0, skills_dir)

# Import all the tools from both modules
from calender import (
    list_events, create_event, 
    update_event, delete_event, get_event
)
from system import edit_env, get_time, obtain_oauth_token
from powershell import run_powershell_command
from memory import embed_memory, retrieve_memory, remove_memory
from search import search
from github import (
    get_repository, create_repository, list_issues, create_issue,
    list_pull_requests, create_pull_request, get_user, list_repositories,
    search_repositories, get_file_contents, create_branch, list_commits
)
from gmail import (
    get_messages, send_email, get_labels, mark_as_read, mark_as_unread,
    delete_email, get_message_details, get_drafts, create_draft, update_draft,
    delete_draft
)

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

# Create a combined MCP instance
mcp = FastMCP("Combined Skills", instructions="Calendar, system, memory, and search utilities", json_response=True)

# Register all calendar tools
mcp.tool()(obtain_oauth_token)
mcp.tool()(list_events)
mcp.tool()(create_event)
mcp.tool()(update_event)
mcp.tool()(delete_event)
mcp.tool()(get_event)

# Register all system tools
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

# Register GitHub tools
mcp.tool()(get_repository)
mcp.tool()(create_repository)
mcp.tool()(list_issues)
mcp.tool()(create_issue)
mcp.tool()(list_pull_requests)
mcp.tool()(create_pull_request)
mcp.tool()(get_user)
mcp.tool()(search_repositories)
mcp.tool()(list_repositories)
mcp.tool()(get_file_contents)
mcp.tool()(create_branch)
mcp.tool()(list_commits)

# Register Gmail tools
mcp.tool()(get_messages)
mcp.tool()(send_email)
mcp.tool()(get_labels)
mcp.tool()(mark_as_read)
mcp.tool()(mark_as_unread)
mcp.tool()(delete_email)
mcp.tool()(get_message_details)
mcp.tool()(get_drafts)
mcp.tool()(create_draft)
mcp.tool()(update_draft)
mcp.tool()(delete_draft)

def main() -> None:
    """Run the combined MCP server."""
    mcp.run()

if __name__ == "__main__":
    main()
