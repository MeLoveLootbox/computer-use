# ComputerUse — Playwright Browser Automation Skill

[![skills.sh](https://skills.sh/b/MeLoveLootbox/computer-use)](https://skills.sh/MeLoveLootbox/computer-use)

An AI agent skill that gives any agent full browser automation capabilities through a local Playwright-powered MCP server. No cloud dependencies, no API keys.

## What it does

- **Browse websites** (Chromium via Playwright)
- **Fill and submit forms** (CSS selector targeting)
- **Take screenshots** (PNG with timestamped filenames)
- **Click elements** (by CSS selector)
- **Scroll pages** (smooth, visible motion)
- **Run JavaScript** (extract data, interact with DOM)
- **Press keyboard keys** (Enter, shortcuts, etc.)

## Install

### As a skill (for AI agents)
```bash
npx skills add MeLoveLootbox/computer-use
```

### One-command setup

**macOS / Linux:**
```bash
git clone https://github.com/MeLoveLootbox/computer-use.git
cd computer-use
bash setup.sh
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/MeLoveLootbox/computer-use.git
cd computer-use
.\setup.ps1
```

This creates a `.venv`, installs all Python deps, downloads Chromium, and prints the MCP config snippet for your agent.

### Register with your agent

**OpenCode** — Add to `opencode.json`:
```json
{
  "mcp": {
    "computerUse": {
      "type": "local",
      "command": ["/path/to/.venv/bin/python3", "/path/to/servers/computer_use_mcp.py"],
      "enabled": true
    }
  }
}
```

**Claude Code** — Add to `.claude.json`:
```json
{
  "mcpServers": {
    "computerUse": {
      "command": "/path/to/.venv/bin/python3",
      "args": ["/path/to/servers/computer_use_mcp.py"]
    }
  }
}
```

## Supported Agents

Works with any agent that supports MCP servers via stdio transport:
- OpenCode
- Claude Code
- Cursor
- Gemini CLI
- GitHub Copilot
- Windsurf
- Codex
- Cline / Roo Code
- And more

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `CU_HEADFUL` | Show visible browser (1=yes) | `0` (headless) |
| `CU_SLOW_MO` | Action delay in ms | `250` |
| `CU_SHOW_CURSOR` | Show cursor overlay | `false` |
| `CU_NO_SANDBOX` | Disable sandbox (Docker) | `0` |
| `CU_BROWSER` | chromium, firefox, webkit | `chromium` |
| `CU_CDP_PORT` | Connect to YOUR Chrome (preserves logins) | (unset) |
| `CU_CHROME_PROFILE` | Path to Chrome user data directory | (unset) |

### Use Your Own Chrome (No More Logins)

```bash
# 1. Close Chrome, then relaunch with debugging:
chrome.exe --remote-debugging-port=9222

# 2. Set env var before starting your agent:
export CU_CDP_PORT=9222
```

## Based on

[GeminiCLI_ComputerUse_Extension](https://github.com/automateyournetwork/GeminiCLI_ComputerUse_Extension) by [automateyournetwork](https://github.com/automateyournetwork)

## License

Apache 2.0 — see [LICENSE](LICENSE)
