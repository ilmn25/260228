# MCP-Aware AI Agent

An intelligent agent system built with the Model Context Protocol (MCP) that can interact through CLI or Discord. The agent supports multiple LLM providers and includes calendar management and utility skills.

## Features

- 🤖 Multiple LLM provider support (Azure AI, GitHub Models, Google Gemini, Ollama)
- 📅 Google Calendar integration (view, create, update, delete events)
- 💬 CLI and Discord bot interfaces
- 🔧 Extensible skill system with MCP server
- 🔗 PowerShell utilities including opening websites or applications
- 🌐 Time zone aware operations

## Prerequisites

- Python 3.8 or higher
- A GitHub account (for Azure/GitHub Models access)
- Google Cloud credentials (for Calendar features)
- Discord bot token (for Discord interface)

## Installation

### 1. Clone and Navigate to Project

```bash
cd c:\Users\user\Desktop\vscode\260228
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
```

### 3. Activate Virtual Environment

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
.venv\Scripts\activate.bat
```

**Linux/Mac:**
```bash
source .venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

## Configuration

### Environment Variables

Create a `.env` file in the project root (use `.env.example` as template):

```bash
cp .env.example .env
```

#### Required Variables (depending on your use case):

| Variable | Description | Required For |
|----------|-------------|--------------|
| `MODEL_PROVIDER` | LLM provider to use (`azure`, `github`, `gemini`, `ollama`) | All modes |
| `GITHUB_TOKEN` | GitHub personal access token | Azure/GitHub Models |
| `GEMINI_API_KEY` | Google Gemini API key | Gemini provider |
| `DISCORD_BOT_TOKEN` | Discord bot token | Discord bot mode |

#### Optional Variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `AZURE_MODEL` | Azure AI model name | `gpt-4o-mini` |
| `AZURE_ENDPOINT` | Azure inference endpoint | `https://models.inference.ai.azure.com` |
| `OLLAMA_MODEL` | Ollama model name | - |
| `OLLAMA_ENDPOINT` | Ollama API endpoint | `http://localhost:11434` |
| `OLLAMA_NUM_CTX` | Ollama context window size | `8192` |
| `DISCORD_USER_ID` | Specific Discord user ID to respond to | - |
| `DISCORD_ACTIVATION_WORD` | Word to activate bot responses | - |

#### Google API Variables:

| Variable | Description |
|----------|-------------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Google service account JSON (e.g., `env/google.json`) |
| `GOOGLE_TOKEN_FILE` | Path to OAuth token file used by calendar, gmail, etc. (e.g., `env/token.json`) |
| `GOOGLE_CALENDAR_ID` | Your Google Calendar ID (usually email) |
| `GOOGLE_CALENDAR_TIMEZONE` | Calendar timezone (e.g., `America/New_York`) |
| `DEFAULT_TIMEZONE` | Default timezone for events (e.g., `America/New_York`) |

### Google Calendar Setup

1. **Create Google Cloud Project:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable Google Calendar API

2. **Create Service Account:**
   - Navigate to "IAM & Admin" > "Service Accounts"
   - Create service account
   - Download JSON key file
   - Save as `env/google.json`

3. **OAuth Token:**
   - Run the calendar skill to generate OAuth token
   - Token will be saved to `env/token.json`

4. **Share Calendar:**
   - Open Google Calendar
   - Share your calendar with the service account email

## Usage

### Terminal CLI Mode (Recommended for Testing)

Run the main entry point which handles both the built-in CLI and the
Discord bot.  The bot will start automatically when `DISCORD_BOT_TOKEN` is
set (or you can force it with `--bot`).

```bash
python main.py              # CLI + bot if token present
python main.py --bot        # CLI + bot (regardless of token)
```

CLI-only mode is no longer a thing; there’s no need for a separate
script.

**Commands:**
- Type your prompts at the `>` prompt
- `/reset` - Clear conversation history
- `/exit` or `exit` - Quit the agent

**Example session:**
```
> What events do I have today?
> Schedule a meeting tomorrow at 2pm
> /reset
> exit
```

### Discord Bot Mode

Run the Discord bot:

```bash
python discord_cli.py
```

**Features:**
- Responds to mentions or activation word
- Can be limited to specific user with `DISCORD_USER_ID`
- Maintains conversation context per channel

## Project Structure

```
260228/
├── main.py               # Entry point for CLI and Discord bot
├── discord_bridge.py     # Shared bridge class and helpers
├── cli.py                # Terminal CLI interface and prompt handling
├── discord_bot.py        # Discord-specific event handlers
├── config.py             # Configuration helpers
├── log.py                # Logging helpers
├── system/               # Core agent & model code
├── prompts/              # System prompts
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (create from .env.example)
├── .env.example          # Example environment configuration
├── env/                  # Credentials directory
│   ├── google.json       # Google service account credentials
│   └── token.json        # OAuth token (auto-generated)
└── skills/               # MCP server skills
    ├── calender.py       # Google Calendar operations
    ├── misc.py           # Utility functions (time, env editing)
    └── combined.py       # Combined MCP server (main server)
```

## Available Skills

The agent has access to the following tools through MCP:

### Calendar Skills
- `list_events` - View calendar events
- `create_event` - Create new calendar events
- `update_event` - Modify existing events
- `delete_event` - Remove events
- `get_event` - Get details of specific event
- `add_oauth_token` - Initialize OAuth authentication

### Utility Skills
- `get_time` - Get current time in specified timezone
- `edit_env` - Modify environment variables

## Troubleshooting

### Virtual Environment Issues
- Make sure you activated the virtual environment before installing packages
- On Windows, you may need to run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` if PowerShell blocks script execution

### API Errors
- Verify all required environment variables are set
- Check that your API keys are valid and have proper permissions
- For GitHub Models, ensure your token has necessary scopes

### Calendar Access
- Verify `google.json` exists in `env/` folder
- Ensure calendar is shared with service account email
- Run `add_oauth_token` tool if `token.json` is missing

### Discord Bot
- Ensure bot has proper permissions in your Discord server
- Check that `DISCORD_BOT_TOKEN` is correctly set
- Verify bot has "Message Content Intent" enabled in Discord Developer Portal

## Getting API Keys

### GitHub Token (for Azure/GitHub Models)
1. Go to GitHub Settings > Developer settings > Personal access tokens
2. Generate new token (classic)
3. No special scopes needed for API access
4. Copy and set as `GITHUB_TOKEN`

### Gemini API Key
1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create or select a project
3. Generate API key
4. Copy and set as `GEMINI_API_KEY`

### Discord Bot Token
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create new application
3. Go to "Bot" section
4. Create bot and copy token
5. Enable "Message Content Intent" under Privileged Gateway Intents
6. Copy and set as `DISCORD_BOT_TOKEN`

## Development

### Adding New Skills

1. Create skill function in `skills/` directory
2. Import and register in `skills/combined.py`
3. Skills automatically become available to the agent

### Modifying Prompts

Edit `prompts.py` to customize:
- `SYSTEM_PROMPT` - Core agent behavior
- `DISCORD_LEAVE_INSTRUCTION` - Discord-specific instructions

## License

This project is for educational and personal use.

## Support

For issues or questions, please check:
1. Environment variables are correctly set
2. Virtual environment is activated
3. All dependencies are installed
4. API keys are valid

---

**Quick Start Checklist:**
- [ ] Virtual environment created and activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created with required variables
- [ ] Google credentials configured (if using calendar)
- [ ] API keys obtained and configured
- [ ] Tested running CLI alone and with the bot (`--bot` or token)
