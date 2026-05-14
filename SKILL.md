---
name: computer-use
description: Full Playwright-powered browser automation for AI agents. Navigate websites, click elements, fill forms, scroll pages, take screenshots, and run JavaScript. Use when the user wants to browse the web, scrape data, fill online forms, take page screenshots, inspect pages, test web apps, interact with web UIs, or extract content from web pages. Also triggers on "browse," "open browser," "go to URL," "headless browser," "web automation," "scrape this page," "take a screenshot of," "fill out this form online," "click on this website," "find on YouTube," or any task requiring a real browser.
---

# ComputerUse — Browser Automation via MCP

A self-contained MCP (Model Context Protocol) server that gives AI agents full control over a Chromium browser through Playwright. No cloud dependency. No API key. Runs locally.

## When to Use

- Navigating to URLs and browsing websites
- Taking screenshots of web pages
- Filling and submitting web forms
- Clicking elements by CSS selector
- Scrolling pages and inspecting content
- Running JavaScript to extract data
- Searching YouTube, Wikipedia, and other sites
- Web scraping and data extraction
- Visual QA and testing
- Any task where "just curl the page" is insufficient (JS-rendered content, logins, interactive workflows)

## Prerequisites (one-time setup)

The ComputerUse MCP server ships with this skill. To install it:

```bash
# 1. Create Python venv
python -m venv .venv

# 2. Install Python dependencies
.venv/bin/pip install -r servers/requirements.txt   # macOS/Linux
.venv\Scripts\pip install -r servers\requirements.txt   # Windows

# 3. Install Chromium browser for Playwright
.venv/bin/playwright install chromium
```

Requirements: **Python >= 3.10**, `pip`.

## MCP Configuration

After setup, register the MCP server with your agent.

### OpenCode
In `opencode.json` (project or `~/.config/opencode/`):
```json
{
  "mcp": {
    "computerUse": {
      "type": "local",
      "command": ["/absolute/path/to/.venv/bin/python3", "/absolute/path/to/servers/computer_use_mcp.py"],
      "enabled": true
    }
  }
}
```

### Claude Code
In `.claude.json` or `~/.claude.json`:
```json
{
  "mcpServers": {
    "computerUse": {
      "command": "/absolute/path/to/.venv/bin/python3",
      "args": ["/absolute/path/to/servers/computer_use_mcp.py"]
    }
  }
}
```

### Gemini CLI
```
gemini extensions install https://github.com/your-org/computer-use.git
```

### Generic MCP (Codex, Cursor, Windsurf, etc.)
Add to your agent's MCP config using `stdio` transport with the venv Python path and the `computer_use_mcp.py` script.

After configuring, restart your agent.

## Tools Reference

### `initialize_browser`
Initializes the Playwright browser.
```
Args:
  url (str):          Initial URL to navigate to
  width (int):        Viewport width (default 1440)
  height (int):       Viewport height (default 900)
  headless (bool):    Force headless/headful (default: headless unless CU_HEADFUL=1)
```

### `capture_state`
Takes a PNG screenshot. Returns `path` (where file was saved), `url` (current page URL), `mime_type`.
```
Args:
  action_name (str):  Label for the screenshot filename
  result_ok (bool):   Was the previous action successful? (default true)
  error_msg (str):    Error message if previous action failed
```

### `click_selector`
Clicks an element by CSS selector.
```
Args:
  selector (str):     CSS selector (e.g., "button.submit", "#login", "a[href='/next']")
  nth (int):          Index of match when multiple elements match (0-based, default 0)
```

### `fill_selector`
Types text into an input/textarea, optionally pressing Enter.
```
Args:
  selector (str):     CSS selector for the input element
  text (str):         Text to type
  press_enter (bool): Hit Enter after typing (default false)
  clear (bool):       Clear existing content first (default true)
```

### `execute_action`
Multi-purpose action runner. Supported action names:
- **`open_web_browser`** — Navigate to a URL: `{"url": "https://..."}` 
- **`scroll_to_percent`** — Scroll vertically: `{"y": 500}` (0=top, 1000=bottom)
- **`execute_javascript`** — Run JS in page: `{"code": "document.title"}`
- **`press_key`** — Press a key: `{"key": "Enter"}` or `{"key": "Meta+L"}`
- **`click_at`** — Click coordinates: `{"x": 500, "y": 300}` (0-1000 normalized)
- **`type_text_at`** — Type at coordinates: `{"x": 500, "y": 300, "text": "hello", "press_enter": false}`
- **`drag_and_drop`** — Drag between points: `{"start_x": 100, "start_y": 200, "end_x": 500, "end_y": 400}`

### `close_browser`
Closes the browser and releases all resources. Always call this at the end of a session.

## Environment Variables

Set before starting your agent to control browser behavior:

| Variable | Purpose | Example |
|----------|---------|---------|
| `CU_HEADFUL` | Show visible browser window (headless=false) | `1` |
| `CU_SLOW_MO` | Milliseconds delay between actions (makes browsing visible) | `700` |
| `CU_SHOW_CURSOR` | Show a cyan cursor ring overlay | `true` |
| `CU_NO_SANDBOX` | Disable Chromium sandbox (Docker/Codespaces) | `1` |
| `CU_BROWSER` | Force browser: `chromium`, `firefox`, `webkit` | `chromium` |
| `CU_DEVICE_SCALE` | Retina scaling (use 2 on macOS) | `2` |

Typical headful demo setup:
```bash
export CU_HEADFUL=1
export CU_SLOW_MO=800
export CU_SHOW_CURSOR=true
```

## Proven Workflows

### Workflow 1: Browse → Extract → Report
```
1. initialize_browser(url="https://example.com")
2. scroll_to_percent → capture_state (repeat for different scroll positions)
3. execute_action("execute_javascript", {code: "extraction JS"})
4. Produce a markdown report from the extracted data
5. close_browser()
```

### Workflow 2: Form Filling
```
1. initialize_browser(url="https://site-with-form.com")
2. fill_selector("input[name='email']", "user@example.com")
3. fill_selector("input[name='password']", "secret", press_enter=true)
4. capture_state("logged_in")
5. close_browser()
```

### Workflow 3: Search → Click → Read
```
1. initialize_browser(url="https://wikipedia.org")
2. fill_selector("input[name='search']", "topic", press_enter=true)
3. capture_state("search_results")
4. click_selector("a[href*='/wiki/']:first-child")
5. scroll_to_percent → capture_state (multiple positions)
6. execute_action("execute_javascript", {code: "extract content JS"})
7. close_browser()
```

## CAPTCHA & Anti-Bot Strategies

Headless browsers are often detected. Mitigations in order of effectiveness:

1. **Headful mode** — Set `CU_HEADFUL=1` to use a visible browser window. This alone often bypasses basic bot detection.
2. **Slow down** — Set `CU_SLOW_MO=800` so actions look human-paced.
3. **Show cursor** — Set `CU_SHOW_CURSOR=true` to show mouse movements.
4. **Use bot-friendly sites first** — Wikipedia, DuckDuckGo, and many developer tools don't challenge automated browsers.
5. **Official APIs** — For Google/YouTube, use their official APIs (Google Custom Search, YouTube Data API) instead of scraping.
6. **Profiles & cookies** — If the agent supports it, use a real browser profile with existing login cookies.

If a site shows a CAPTCHA, don't keep trying — switch to an API or a bot-friendly alternative.

## Error Recovery

- **Browser stuck?** Call `close_browser()` and re-initialize.
- **Element not found?** Try scrolling first, then retry. Dynamic content may need a `wait_for_timeout`.
- **Navigation timeout?** The page may be slow. Retry with a longer implicit wait.
- **JavaScript returns empty?** The content may be in a shadow DOM or loaded asynchronously. Try different selectors or add a delay.

## Notes

- Screenshots are saved to `/tmp/gemini_computer_use/` (or `\tmp\gemini_computer_use\` on Windows).
- Always call `close_browser()` when done to free resources.
- The browser persists between tool calls within a session — you don't need to re-initialize for each navigation.
- Use `scroll_to_percent` instead of instant jumps for human-visible browsing.
- Prefer CSS selectors over coordinate-based clicks for reliability.
