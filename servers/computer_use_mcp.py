#!/usr/bin/env python3
"""
MCP Server: Gemini Computer Use Tool Client (Playwright-based, ASYNC)

Tools:
  - initialize_browser(url: str, width: int=1440, height: int=900, headless: Optional[bool]=None)
  - execute_action(action_name: str, args: Dict[str, Any])
  - capture_state(action_name: str, result_ok: bool=True, error_msg: str="")
  - close_browser()

Profile/Login Modes:
  - Fresh Chromium (default): no logins, clean slate
  - CU_CDP_PORT=9222: auto-connect to YOUR Chrome (preserves all logins/cookies)
    If Chrome isn't running with CDP, it auto-launches Chrome for you.
  - CU_CHROME_PROFILE=path: use your Chrome profile directory
    (Chrome must NOT be running when using this mode)

Notes:
- Uses Playwright ASYNC API (MCP host runs an asyncio loop).
- Logs to stderr only.
"""

import os, sys, time, logging, subprocess, socket, shutil, asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from io import BytesIO

# ----- Logging (stderr only) -----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("ComputerUseMCP")

# ---------- FastMCP ----------
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    from fastmcp import FastMCP  # type: ignore

# ---------- Playwright (ASYNC) ----------
try:
    from playwright.async_api import (
        async_playwright, Playwright, Browser, BrowserContext, Page, TimeoutError
    )
    from PIL import Image
except ImportError as e:
    log.error("Missing dependency: %s (pip install playwright pillow)", e)
    log.error("Also run: playwright install chromium")
    raise

# --------- Configuration ---------
DEFAULT_HEADLESS = True  # silent by default
DEFAULT_SLOW_MO_MS = int(os.getenv("CU_SLOW_MO", "250"))  # ms between actions
SHOW_CURSOR = os.getenv("CU_SHOW_CURSOR", "").strip().lower() in ("1", "true", "yes")

# Profile / CDP connection
CDP_PORT = os.getenv("CU_CDP_PORT", "").strip()  # e.g. "9222", "chrome", or "auto"
CHROME_PROFILE = os.getenv("CU_CHROME_PROFILE", "").strip()  # user-data-dir path
USE_CDP = bool(CDP_PORT) and (CDP_PORT.isdigit() or CDP_PORT.lower() in ("chrome", "auto"))
USE_PROFILE = bool(CHROME_PROFILE) and os.path.isdir(CHROME_PROFILE)

def _detect_chrome_port() -> Optional[int]:
    """Detect CDP port from Chrome's DevToolsActivePort file (channel detection)."""
    try:
        profile_dir = _find_chrome_profile()
        if not profile_dir:
            return None
        port_file = os.path.join(profile_dir, "DevToolsActivePort")
        if os.path.isfile(port_file):
            with open(port_file) as f:
                first_line = f.readline().strip()
                port = int(first_line)
                if 1024 <= port <= 65535:
                    return port
    except Exception:
        pass
    return None

# ---------- Chrome Auto-Launch helpers ----------

def _find_chrome_exe() -> Optional[str]:
    """Find the Chrome/Chromium executable on this system."""
    candidates = []
    if sys.platform == "win32":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles%\Chromium\Application\chrome.exe"),
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    # Try PATH
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "chrome.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None

def _find_chrome_profile() -> Optional[str]:
    """Find the default Chrome user-data directory."""
    candidates = []
    if sys.platform == "win32":
        base = os.path.expandvars(r"%LocalAppData%\Google\Chrome\User Data")
        candidates.append(base)
    elif sys.platform == "darwin":
        candidates.append(os.path.expanduser("~/Library/Application Support/Google/Chrome"))
    else:
        candidates.append(os.path.expanduser("~/.config/google-chrome"))
    for d in candidates:
        if os.path.isdir(d):
            return d
    return None

async def _check_cdp_port(port: int) -> bool:
    """Check if something is listening on the CDP port."""
    # Try httpx first (proper HTTP check)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"http://localhost:{port}/json/version")
            return resp.status_code == 200
    except Exception:
        pass
    # Fallback: raw socket check
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        result = sock.connect_ex(("localhost", port))
        sock.close()
        return result == 0
    except Exception:
        pass
    return False

def _launch_chrome_with_cdp(port: int) -> Optional[subprocess.Popen]:
    """Launch Chrome with remote debugging enabled, using the user's profile."""
    chrome_exe = _find_chrome_exe()
    if not chrome_exe:
        log.error("Chrome executable not found. Cannot auto-launch.")
        return None

    profile_dir = _find_chrome_profile()
    if not profile_dir:
        log.warning("Chrome profile directory not found. Launching without profile.")

    cmd = [chrome_exe, f"--remote-debugging-port={port}"]
    if profile_dir:
        cmd.append(f"--user-data-dir={profile_dir}")

    if sys.platform == "win32":
        cmd.append("--disable-features=TranslateUI")
    elif sys.platform == "darwin":
        # macOS: must use `open` or the full path; also needs --args
        # Actually just exec-ing works on modern macOS
        pass

    log.info("Auto-launching Chrome: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # detach from our process group
        )
        return proc
    except Exception as e:
        log.error("Failed to launch Chrome: %s", e)
        return None

CURSOR_OVERLAY_JS = r"""
(() => {
  if (window.__mcpCursorInstalled) return;
  window.__mcpCursorInstalled = true;
  const cursor = document.createElement('div');
  cursor.id = 'mcp-cursor';
  cursor.style.cssText = `
    position: fixed; top:0; left:0; width:18px; height:18px;
    margin:-9px 0 0 -9px;
    border: 2px solid #00ffff; border-radius: 50%;
    background: rgba(0,255,255,0.25);
    pointer-events:none; z-index: 2147483647;
    transition: transform 90ms linear, background 120ms ease;
  `;
  document.documentElement.appendChild(cursor);
  window.__updateCursor = (x, y, click) => {
    cursor.style.transform = `translate(${x}px, ${y}px)`;
    if (click) {
      cursor.style.background = 'rgba(0,255,255,0.6)';
      setTimeout(() => { cursor.style.background = 'rgba(0,255,255,0.25)'; }, 120);
    }
  };
})();
"""

# ---------- Global state ----------
_STATE: Dict[str, Any] = {
    "playwright": None,   # Playwright
    "browser": None,      # Browser
    "context": None,      # BrowserContext
    "page": None,         # Page
    "screen_width": 1440,
    "screen_height": 900,
    "connect_mode": "fresh",  # "fresh", "cdp", or "profile"
    "chrome_proc": None,      # subprocess.Popen if we auto-launched Chrome
}

_SUPPORTED_ACTIONS = [
    "open_web_browser", "click_at", "type_text_at",
    "scroll_to_percent", "enter_text_at", "select_option_at",
    "drag_and_drop", "press_key", "execute_javascript",
]

# ---------- Helpers ----------
def denormalize_x(x: int, screen_width: int) -> int:
    return int(int(x) / 1000 * screen_width)

def denormalize_y(y: int, screen_height: int) -> int:
    return int(int(y) / 1000 * screen_height)

def get_page() -> Optional[Page]:
    return _STATE["page"]

async def _await_render(page: Page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except TimeoutError:
        log.warning("Page load wait timed out.")
    await page.wait_for_timeout(300)  # tiny settle

# ---------- Action handlers ----------
async def _execute_open_web_browser(args: Dict[str, Any]) -> Dict[str, Any]:
    page = get_page()
    if page is None:
        raise RuntimeError("Browser not initialized.")
    url = args.get("url", "about:blank")
    log.info("Navigating to: %s", url)
    await page.goto(url, timeout=20000)
    return {"status": f"Navigated to {page.url}"}

async def _execute_click_at(args: Dict[str, Any]) -> Dict[str, Any]:
    page = get_page()
    if page is None:
        raise RuntimeError("Browser not initialized.")
    if "x" not in args or "y" not in args:
        raise ValueError("click_at requires numeric 'x' and 'y' in 0..1000")
    x = denormalize_x(args["x"], _STATE["screen_width"])
    y = denormalize_y(args["y"], _STATE["screen_height"])
    log.info("Clicking at: (%d, %d)", x, y)

    try:
        await page.evaluate(f"window.__updateCursor && __updateCursor({x},{y},false)")
    except Exception:
        pass
    await page.mouse.move(x, y)
    await page.mouse.click(x, y)
    try:
        await page.evaluate(f"window.__updateCursor && __updateCursor({x},{y},true)")
    except Exception:
        pass

    return {"status": f"Clicked at ({x}, {y})"}

async def _execute_type_text_at(args: Dict[str, Any]) -> Dict[str, Any]:
    page = get_page()
    if page is None:
        raise RuntimeError("Browser not initialized.")
    for k in ("x", "y", "text"):
        if k not in args:
            raise ValueError("type_text_at requires 'x','y','text'")

    x = denormalize_x(args["x"], _STATE["screen_width"])
    y = denormalize_y(args["y"], _STATE["screen_height"])
    text = str(args["text"])
    press_enter = bool(args.get("press_enter", False))
    log.info("Typing at (%d, %d): %r (enter=%s)", x, y, text, press_enter)

    try:
        await page.evaluate(f"window.__updateCursor && __updateCursor({x},{y},false)")
    except Exception:
        pass

    await page.mouse.move(x, y)
    await page.mouse.click(x, y)

    # Try to focus a real text-receiving element at the click point
    focused_ok = await page.evaluate(
        """
        ([x, y]) => {
          const el = document.elementFromPoint(x, y);
          if (!el) return false;
          const target = el.closest('input,textarea,[contenteditable="true"],[role="searchbox"],[type="search"]');
          if (!target) return false;
          target.focus();
          try {
            // Select existing text if supported (but only in inputs/textareas)
            if (target.select) target.select();
            else if (target.setSelectionRange && typeof target.value === 'string') {
              target.setSelectionRange(0, target.value.length);
            }
          } catch (_) {}
          return true;
        }
        """,
        [x, y],
    )

    # Only do "Select All" if an editable is actually focused
    if focused_ok:
        # Optional: clear existing value via JS to avoid body-select-all
        try:
            await page.evaluate(
                "if (document.activeElement && 'value' in document.activeElement) document.activeElement.value='';"
            )
        except Exception:
            pass
    else:
        log.warning("No editable element at click point; skipping select-all to avoid page-wide selection.")

    await page.keyboard.type(text)
    if press_enter:
        await page.keyboard.press("Enter")

    try:
        await page.evaluate(f"window.__updateCursor && __updateCursor({x},{y},true)")
    except Exception:
        pass

    return {"status": f"Typed text at ({x}, {y}), enter: {press_enter}"}

async def _execute_scroll_to_percent(args: Dict[str, Any]) -> Dict[str, Any]:
    page = get_page()
    if page is None:
        raise RuntimeError("Browser not initialized.")
    if "y" not in args:
        raise ValueError("scroll_to_percent requires 'y' in 0..1000")
    y_norm = max(0, min(1000, int(args["y"])))

    await page.evaluate(f"""
        (async () => {{
          const H = Math.max(
            document.body?.scrollHeight || 0,
            document.documentElement?.scrollHeight || 0
          );
          const target = (H * {y_norm}) / 1000;
          window.scrollTo({{ top: target, behavior: 'smooth' }});
        }})();
    """)
    await page.wait_for_timeout(600)
    return {"status": f"Scrolled to {y_norm}/1000"}

async def _execute_press_key(args: Dict[str, Any]) -> Dict[str, Any]:
    page = get_page()
    if page is None:
        raise RuntimeError("Browser not initialized.")
    key = str(args.get("key", "")).strip()
    if not key:
        raise ValueError("press_key requires 'key', e.g., 'Enter' or 'Meta+L'")
    log.info("Pressing key: %s", key)
    await page.keyboard.press(key)  # supports chords (e.g., "Control+L", "Meta+L")
    return {"status": f"Pressed {key}"}

async def _execute_execute_javascript(args: Dict[str, Any]) -> Dict[str, Any]:
    page = get_page()
    if page is None:
        raise RuntimeError("Browser not initialized.")
    code = str(args.get("code", "")).strip()
    if not code:
        raise ValueError("execute_javascript requires 'code' string")
    log.info("Executing JS snippet (%d chars)", len(code))
    result = await page.evaluate(code)
    return {"status": "JS executed", "result": result}

# ---------- MCP server ----------
mcp = FastMCP("ComputerUse MCP")

@mcp.tool()
async def initialize_browser(
    url: str,
    width: int = 1440,
    height: int = 900,
    headless: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Initializes the Playwright browser, context, and page (ASYNC).

    Connection modes (set via env vars BEFORE starting the agent):
      - Default (no env vars): fresh Chromium, no logins
      - CU_CDP_PORT=9222: connect to your existing Chrome (preserves logins/cookies)
      - CU_CHROME_PROFILE=path: launch using your Chrome profile (Chrome must be closed)

    Args:
        url: initial URL
        width/height: viewport
        headless: if provided, overrides env defaults (True=headless, False=headful)
    """
    _STATE["screen_width"] = int(width)
    _STATE["screen_height"] = int(height)

    if get_page():
        log.warning("Browser already initialized. Closing and re-initializing.")
        await close_browser()

    try:
        _STATE["playwright"] = await async_playwright().start()

        # Resolve headless mode
        if headless is None:
            headful_env = os.getenv("CU_HEADFUL", "")
            effective_headless = not (headful_env.strip().lower() in ("1", "true", "yes"))
        else:
            effective_headless = bool(headless)

        launch_args: Dict[str, Any] = {}
        if os.getenv("CU_NO_SANDBOX", "").strip().lower() in ("1", "true", "yes"):
            launch_args["args"] = ["--no-sandbox"]

        # ---- MODE: Connect to user's Chrome via CDP ----
        if USE_CDP:
            # Resolve the port to use
            if CDP_PORT.lower() in ("chrome", "auto"):
                detected = _detect_chrome_port()
                if detected:
                    port = detected
                    log.info("Detected Chrome CDP port from DevToolsActivePort: %s", port)
                else:
                    log.warning("Could not detect Chrome port. Enable 'Allow remote debugging' at chrome://inspect/#remote-debugging")
                    if CDP_PORT.lower() == "auto":
                        log.info("Falling back to fresh Chromium.")
                    else:
                        raise RuntimeError(
                            "CU_CDP_PORT=chrome but no Chrome debugging port detected. "
                            "Open chrome://inspect/#remote-debugging and enable 'Allow remote debugging'"
                        )
            else:
                port = int(CDP_PORT)

            cdp_url = f"http://localhost:{port}"

            # Check if Chrome is already listening
            log.info("Checking for Chrome on port %s...", port)
            already_running = await _check_cdp_port(port)

            if not already_running and CDP_PORT.isdigit():
                # Auto-launch only for explicit port (not chrome/auto channel mode)
                log.info("No Chrome found on port %s. Auto-launching...", port)
                proc = _launch_chrome_with_cdp(port)
                if proc:
                    _STATE["chrome_proc"] = proc
                    log.info("Waiting for Chrome to start (up to 15s)...")
                    for _ in range(30):
                        await asyncio.sleep(0.5)
                        if await _check_cdp_port(port):
                            log.info("Chrome started and CDP is ready.")
                            break
                    else:
                        log.warning("Chrome launched but CDP not responding. Trying anyway...")

            # Connect via CDP
            log.info("Connecting to Chrome via CDP at %s", cdp_url)
            _STATE["browser"] = await _STATE["playwright"].chromium.connect_over_cdp(cdp_url)
            contexts = _STATE["browser"].contexts
            if contexts:
                _STATE["context"] = contexts[0]
                _STATE["page"] = contexts[0].pages[0] if contexts[0].pages else await contexts[0].new_page()
            else:
                _STATE["context"] = await _STATE["browser"].new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=2,
                )
                _STATE["page"] = await _STATE["context"].new_page()
            _STATE["connect_mode"] = "cdp"
            log.info("Connected to Chrome via CDP. Logins/cookies preserved.")

        # ---- MODE: Launch Chromium with user's Chrome profile ----
        elif USE_PROFILE:
            if effective_headless:
                log.warning("Profile mode forces headful (persistent context requirement).")
                effective_headless = False
            log.info("Launching Chromium with profile: %s", CHROME_PROFILE)
            _STATE["context"] = await _STATE["playwright"].chromium.launch_persistent_context(
                user_data_dir=CHROME_PROFILE,
                headless=False,
                slow_mo=DEFAULT_SLOW_MO_MS,
                viewport={"width": width, "height": height},
                device_scale_factor=2,
                **launch_args
            )
            _STATE["browser"] = None  # persistent context manages its own browser
            _STATE["page"] = _STATE["context"].pages[0] if _STATE["context"].pages else await _STATE["context"].new_page()
            _STATE["connect_mode"] = "profile"
            log.info("Chromium launched with profile. Logins/cookies preserved.")

        # ---- MODE: Fresh Chromium (default) ----
        else:
            _STATE["browser"] = await _STATE["playwright"].chromium.launch(
                headless=effective_headless,
                slow_mo=DEFAULT_SLOW_MO_MS,
                **launch_args
            )
            _STATE["context"] = await _STATE["browser"].new_context(
                viewport={"width": _STATE["screen_width"], "height": _STATE["screen_height"]},
                device_scale_factor=2,
            )
            _STATE["page"] = await _STATE["context"].new_page()
            _STATE["connect_mode"] = "fresh"

        # Optional cursor overlay
        if SHOW_CURSOR:
            await _STATE["page"].add_init_script(CURSOR_OVERLAY_JS)
            try:
                await _STATE["page"].evaluate(CURSOR_OVERLAY_JS)
            except Exception:
                pass

        await _STATE["page"].goto(url, timeout=20000)
        await _await_render(_STATE["page"])

        log.info(
            "Browser initialized to %s at %dx%d (mode=%s, headless=%s, slow_mo=%dms)",
            url, width, height, _STATE["connect_mode"], effective_headless, DEFAULT_SLOW_MO_MS
        )
        return {
            "ok": True,
            "url": _STATE["page"].url,
            "width": _STATE["screen_width"],
            "height": _STATE["screen_height"],
            "headless": effective_headless,
            "slow_mo_ms": DEFAULT_SLOW_MO_MS,
            "connect_mode": _STATE["connect_mode"],
        }
    except Exception as e:
        log.error("Initialization failed: %s", e)
        await close_browser()
        return {"ok": False, "error": f"Browser initialization failed: {e}"}

@mcp.tool()
async def execute_action(action_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a single Computer Use action (ASYNC).
    """
    page = get_page()
    if page is None:
        return {"ok": False, "error": "Browser not initialized. Use /computeruse:init first."}

    log.info("Executing action: %s with args: %s", action_name, args)

    try:
        result: Dict[str, Any] = {"status": "Action completed successfully."}

        if action_name == "open_web_browser":
            result.update(await _execute_open_web_browser(args))
        elif action_name == "click_at":
            result.update(await _execute_click_at(args))
        elif action_name == "type_text_at":
            result.update(await _execute_type_text_at(args))
        elif action_name == "scroll_to_percent":
            result.update(await _execute_scroll_to_percent(args))
        elif action_name == "press_key":
            result.update(await _execute_press_key(args))
        elif action_name == "execute_javascript":
            result.update(await _execute_execute_javascript(args))
        elif action_name in _SUPPORTED_ACTIONS:
            result = {
                "status": (
                    f"Warning: Action '{action_name}' is supported by the model "
                    f"but not implemented in this MCP. Skipping."
                ),
                "unimplemented": True,
            }
        else:
            result = {
                "status": f"Error: Unknown or unsupported action: {action_name}",
                "error": True,
            }

        await _await_render(page)
        return {"ok": True, "action_name": action_name, "result": result}

    except Exception as e:
        log.error("Error executing %s: %s", action_name, e)
        return {"ok": False, "action_name": action_name, "error": str(e), "result": {}}

@mcp.tool()
async def capture_state(action_name: str, result_ok: bool = True, error_msg: str = "") -> Dict[str, Any]:
    """
    Captures a screenshot and returns path + URL (ASYNC).
    """
    page = get_page()
    if page is None:
        return {"ok": False, "error": "Browser not initialized. Cannot capture state."}

    try:
        screenshot_bytes = await page.screenshot(type="png")
        temp_dir = Path("/tmp/gemini_computer_use")
        temp_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{int(time.time() * 1000)}_{action_name}.png"
        fpath = temp_dir / fname
        with open(fpath, "wb") as f:
            f.write(screenshot_bytes)

        current_url = page.url
        response_data: Dict[str, Any] = {"url": current_url}
        if not result_ok:
            response_data["error"] = error_msg

        return {
            "ok": True,
            "path": str(fpath),
            "mime_type": "image/png",
            "url": current_url,
            "response_data": response_data,
        }

    except Exception as e:
        log.error("Error capturing state: %s", e)
        return {"ok": False, "error": f"State capture failed: {e}"}

@mcp.tool()
async def click_selector(selector: str, nth: int = 0) -> Dict[str, Any]:
    page = get_page()
    if page is None:
        return {"ok": False, "error": "Browser not initialized."}
    loc = page.locator(selector).nth(nth)
    await loc.wait_for(state="visible", timeout=8000)
    await loc.click()
    await _await_render(page)
    return {"ok": True, "status": f"Clicked selector {selector} [nth={nth}]"}

@mcp.tool()
async def fill_selector(selector: str, text: str, press_enter: bool = False, clear: bool = True) -> Dict[str, Any]:
    page = get_page()
    if page is None:
        return {"ok": False, "error": "Browser not initialized."}
    loc = page.locator(selector).first
    await loc.wait_for(state="visible", timeout=8000)
    await loc.click()
    if clear:
        try:
            await loc.fill("")  # uses element.value when possible
        except Exception:
            # Fallback JS clear
            await page.evaluate(
                "(sel)=>{const el=document.querySelector(sel); if(el && 'value' in el) el.value='';}", selector
            )
    await loc.type(text)
    if press_enter:
        await page.keyboard.press("Enter")
    await _await_render(page)
    return {"ok": True, "status": f"Filled {selector} with text", "pressed_enter": press_enter}

@mcp.tool()
async def close_browser() -> Dict[str, Any]:
    """Closes the Playwright browser and releases resources (ASYNC)."""
    mode = _STATE.get("connect_mode", "fresh")
    try:
        if mode == "cdp":
            # CDP: only close our context/page, don't kill user's Chrome
            if _STATE["context"]:
                await _STATE["context"].close()
            if _STATE["page"]:
                _STATE["page"] = None
            log.info("Disconnected from CDP browser (user's Chrome remains open).")
        elif mode == "profile":
            # Profile: close persistent context (browser managed internally)
            if _STATE["context"]:
                await _STATE["context"].close()
        else:
            # Fresh: close context, browser, then stop Playwright
            if _STATE["context"]:
                await _STATE["context"].close()
            if _STATE["browser"]:
                await _STATE["browser"].close()
        if _STATE["playwright"]:
            await _STATE["playwright"].stop()
        log.info("Browser closed successfully. (mode=%s)", mode)
        return {"ok": True}
    except Exception as e:
        log.error("Error closing browser: %s", e)
        return {"ok": False, "error": str(e)}
    finally:
        _STATE.update({
            "playwright": None, "browser": None, "context": None, "page": None,
            "screen_width": 1440, "screen_height": 900, "connect_mode": "fresh",
            "chrome_proc": None,
        })

if __name__ == "__main__":
    try:
        log.info("✅ ComputerUse MCP (ASYNC) ready on stdio. PID=%s", os.getpid())
        mcp.run()
    except Exception as e:
        log.exception("MCP server crashed: %s", e)
        sys.exit(1)
