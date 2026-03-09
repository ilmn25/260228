# Multi-Interface AI Agent

A flexible AI agent system supporting Discord bot, terminal CLI, and speech-to-text interfaces. Built with MCP (Model Context Protocol) integration for extensible tool calling and task automation.

## Features

**Multiple Interfaces**
- Discord bot with activation word and session timeout
- Terminal CLI for direct interaction
- Speech-to-text input using Whisper (optional)
- Concurrent operation (run CLI and Discord bot simultaneously)

**AI Model Support**
- Ollama (local models)
- Google Gemini
- Azure AI Inference
- GitHub Models API

**Integrated Skills**
- Google Calendar management
- Gmail operations
- GitHub repository interaction
- Web search (LangSearch)
- PowerShell command execution
- Vector memory storage (Pinecone)
- Blackboard for persistent notes
- Resume/document parsing

**MCP Integration**
- Model Context Protocol client for extensible tool system
- Dynamic tool discovery and execution
- Support for custom MCP servers

## Installation

1. Clone the repository and navigate to the project directory

2. Create a virtual environment:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Fill in required credentials (see Configuration section)

## Configuration

### Required Environment Variables

**Model Provider** (choose one):
```
MODEL_PROVIDER=ollama          # Options: ollama, gemini, azure, github
OLLAMA_MODEL=gpt-oss:120b      # For Ollama
OLLAMA_ENDPOINT=https://ollama.com
GEMINI_API_KEY=your_key        # For Gemini
GITHUB_TOKEN=your_token        # For GitHub Models or GitHub skill
```

**Google Services** (for Calendar/Gmail skills):
```
GOOGLE_APPLICATION_CREDENTIALS=env/google.json
GOOGLE_TOKEN_FILE=env/token.json
GOOGLE_DEFAULT_EMAIL=your_email@gmail.com
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_TIMEZONE=Asia/Hong_Kong
```

**Discord Bot** (optional):
```
DISCORD_BOT_TOKEN=your_discord_token
DISCORD_USER_ID=123456789      # Optional: restrict to specific user
ACTIVATION_WORD=hey            # Word to activate the bot
ACTIVATION_TIMEOUT=60          # Auto-deactivate after N seconds
```

**Vector Memory** (optional):
```
PINECONE_API_KEY=your_key
PINECONE_INDEX_NAME=agent-memory
PINECONE_NAMESPACE=agent
PINECONE_DIMENSION=1536
```

### File Locations

Place authentication files in the `env/` directory:
- `google.json` - Google service account credentials
- `token.json` - OAuth token for Calendar/Gmail
- `vectors.json` - Local vector storage (auto-created)
- `runtime_state.json` - Runtime configuration (auto-created)

## Running the Application

**From workspace root:**
```powershell
python system\main.py            # CLI + Discord bot (if token set)
python system\main.py --no-cli   # Discord bot only
python system\main.py --bot      # Force Discord bot mode
```

**Using batch file** (Windows):
```powershell
system\run.bat                   # Runs in background using pythonw.exe
```

**Activation:**
- Discord: Send a message containing your activation word (default: "hey")
- CLI: Type directly at the prompt
- Speech: Enable with `ENABLE_SPEECH_ON_START=true`

## Project Structure

```
system/              Main application modules
  main.py            Entry point and interface orchestration
  agent.py           Core agent logic with MCP integration
  bridge.py          Shared interface abstraction layer
  cli.py             Terminal CLI interface
  discord_bot.py     Discord bot interface
  speech.py          Speech-to-text interface
  model.py           LLM client implementations
  log.py             Logging utilities

skills/              Agent capabilities and integrations
  calender.py        Google Calendar operations
  gmail.py           Gmail operations
  github.py          GitHub API integration
  search.py          Web search functionality
  memory.py          Vector memory storage
  blackboard.py      Persistent note system
  powershell.py      PowerShell command execution
  mcp_server.py      MCP server management
  runtime_state.py   Runtime configuration

prompts/             System prompts and instructions
  system.py          Base system prompt configuration

env/                 Credentials and runtime data
  google.json        Google service account (gitignored)
  token.json         OAuth tokens (gitignored)
  vectors.json       Vector embeddings (gitignored)
  runtime_state.json Runtime state (gitignored)
```

## Usage Examples

**Discord Bot:**
1. Invite bot to your server
2. Send: "hey, what's on my calendar today?"
3. Bot activates and responds
4. Session auto-deactivates after timeout

**Terminal CLI:**
```
> analyze my recent GitHub commits
> send an email to john@example.com about the meeting
> search for information about MCP protocol
> stop
```

**Speech Input:**
Enable with environment variable and speak naturally after the voice activity detection triggers.

## Notes

- The agent maintains conversation context across multiple turns
- MCP servers are initialized on startup and provide dynamic tools
- Sessions can be reset with the "leave" command
- Use "stop" to terminate the application gracefully
- Log output is written to `agent_output.log` in the workspace root

## Dependencies

Core requirements: Python 3.10+, azure-ai-inference, discord.py, google-genai, mcp, ollama

See `requirements.txt` for full dependency list.
