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
from system_tools import edit_env, get_time, list_env, set_speech_mode
from google_auth import add_oauth_token, list_authed_emails
from powershell import run_powershell_command, open_with_powershell
from memory import embed_memory, retrieve_memory, remove_memory
from search import search
from github import (
    get_repository, create_repository, list_issues, create_issue,
    list_pull_requests, create_pull_request, get_user, list_repositories,
    search_repositories, get_file_contents, create_branch, list_commits
)
from gmail import (
    list_emails, send_email, get_labels, mark_as_read, mark_as_unread,
    delete_email, get_email_details, get_drafts, create_draft, update_draft,
    delete_draft
)
from resume import draft_job_email
from blackboard import login as blackboard_login

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

# Create a combined MCP instance
mcp = FastMCP("Combined Skills", instructions="Calendar, system, memory, and search utilities", json_response=True)

# Register all calendar tools 
mcp.tool()(list_events)
mcp.tool()(create_event)
mcp.tool()(update_event)
mcp.tool()(delete_event)
mcp.tool()(get_event)

# Register all system tools
mcp.tool()(get_time)
mcp.tool()(edit_env)
# expose a tool for enumerating the current .env variables
mcp.tool()(list_env)
mcp.tool()(set_speech_mode)

# Register Google auth tools
mcp.tool()(list_authed_emails)
mcp.tool()(add_oauth_token)

# Register all memory tools
mcp.tool()(embed_memory)
mcp.tool()(retrieve_memory)
mcp.tool()(remove_memory)

# Register search tools
mcp.tool()(search)

# Register powershell tools
mcp.tool()(run_powershell_command)
mcp.tool()(open_with_powershell)

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
mcp.tool()(list_emails)
mcp.tool()(send_email)
mcp.tool()(get_labels)
mcp.tool()(mark_as_read)
mcp.tool()(mark_as_unread)
mcp.tool()(delete_email)
mcp.tool()(get_email_details)
mcp.tool()(get_drafts)
mcp.tool()(create_draft)
mcp.tool()(update_draft)
mcp.tool()(delete_draft)

# Register resume/job tools
mcp.tool()(draft_job_email)

# Register Blackboard tools
mcp.tool()(blackboard_login)

def main() -> None:
    """Run the combined MCP server."""
    mcp.run()

if __name__ == "__main__":
    main()
