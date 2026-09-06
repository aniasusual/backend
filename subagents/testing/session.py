"""
Playwright Browser Session Manager & Action Executor.
Handles Chromium lifecycle, sanitized console/network error trapping (inspired by Emergent),
and resilient DOM interaction primitives.
"""

import logging
import re
import time
from typing import List, Optional, Tuple
from playwright.sync_api import sync_playwright, Browser, Page, Playwright

logger = logging.getLogger(__name__)

# Emergent-style console filter patterns to suppress noisy non-actionable logs
SKIP_LOGS_PATTERNS = [
    re.compile(r"Using fallback translation for", re.IGNORECASE),
    re.compile(r"posthog", re.IGNORECASE),
    re.compile(r"fonts\.googleapis\.com", re.IGNORECASE),
    re.compile(r"fonts\.gstatic\.com", re.IGNORECASE),
    re.compile(r"favicon\.ico", re.IGNORECASE),
    re.compile(r"chrome-extension://", re.IGNORECASE),
]


class PlaywrightBrowserSession:
    """
    Encapsulates Playwright Chromium lifecycle, live log sanitization,
    and high-level testing primitives.
    """

    def __init__(self, headless: bool = True, viewport: Optional[dict] = None):
        self.headless = headless
        self.viewport = viewport or {"width": 1280, "height": 800}

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

        self.console_errors: List[str] = []
        self.network_failures: List[str] = []
        self.actions_executed: List[str] = []

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser session not started. Call start(url) first.")
        return self._page

    def _should_skip_log(self, text: str) -> bool:
        """Determines if a console warning/error should be omitted based on noise filter."""
        for pattern in SKIP_LOGS_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def start(self, url: str, timeout_ms: int = 15000) -> Tuple[bool, str]:
        """
        Launches Chromium, binds console/crash listeners, and navigates to target URL.
        Returns (success, error_message_if_any).
        """
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = self._browser.new_context(viewport=self.viewport)
            self._page = context.new_page()

            # 1. Console Listener
            def on_console(msg):
                if msg.type in ["error", "warning"]:
                    text = msg.text
                    if not self._should_skip_log(text):
                        self.console_errors.append(f"[{msg.type.upper()}] {text}")

            self._page.on("console", on_console)

            # 2. Page Crash / Uncaught Exception Listener
            def on_page_error(err):
                err_text = str(err)
                if not self._should_skip_log(err_text):
                    self.console_errors.append(f"[CRASH] {err_text}")

            self._page.on("pageerror", on_page_error)

            # 3. Failed Network Requests (e.g. 404, 500)
            def on_request_failed(request):
                url_str = request.url
                if not self._should_skip_log(url_str):
                    self.network_failures.append(f"[NET_FAIL] {request.method} {url_str} - {request.failure}")

            self._page.on("requestfailed", on_request_failed)

            # Navigate to target preview URL
            self._page.goto(url, wait_until="load", timeout=timeout_ms)
            time.sleep(0.8)  # Allow initial framework hydration to settle
            return True, ""

        except Exception as e:
            err_msg = str(e)
            logger.error(f"[PlaywrightBrowserSession] Failed to connect to {url}: {err_msg}")
            self.close()
            return False, err_msg

    def execute_action(self, action: dict) -> str:
        """
        Dispatches and executes a goal-driven testing action.
        """
        act = action.get("action", "").lower().strip()
        el_id = action.get("id", "").strip()
        reason = action.get("reason", "")

        try:
            if act == "click":
                return self._click(el_id, reason)
            elif act == "type":
                text = action.get("text", "")
                return self._type(el_id, text, reason)
            elif act == "select":
                value = action.get("value", "")
                return self._select(el_id, value, reason)
            elif act == "wait":
                seconds = float(action.get("seconds", 1.0))
                return self._wait(seconds, reason)
            elif act == "assert_text":
                text = action.get("text", "")
                return self._assert_text(text, reason)
            elif act == "navigate":
                url = action.get("url", "")
                return self._navigate(url, reason)
            else:
                return f"Error: Unknown action '{act}'."
        except Exception as e:
            err_line = str(e).split("\n")[0]
            err_msg = f"Failed action '{act}' on '{el_id}': {err_line}"
            self.actions_executed.append(f"❌ {err_msg}")
            return err_msg

    def _click(self, el_id: str, reason: str) -> str:
        selector = f"[data-sdet-id='{el_id}']"
        loc = self.page.locator(selector)
        if loc.count() == 0:
            return f"Element '{el_id}' not found on current page."

        try:
            loc.first.click(timeout=3000)
        except Exception:
            # Emergent rule: Retry with force=True to bypass modal/backdrop overlays
            loc.first.click(force=True, timeout=2000)

        self.page.wait_for_timeout(300)  # Settle animations / dropdowns
        desc = f"Clicked '{el_id}'" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Successfully clicked '{el_id}'."

    def _type(self, el_id: str, text: str, reason: str) -> str:
        selector = f"[data-sdet-id='{el_id}']"
        loc = self.page.locator(selector)
        if loc.count() == 0:
            return f"Element '{el_id}' not found on current page."

        loc.first.fill(text, timeout=3000)
        desc = f"Typed '{text}' into '{el_id}'" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Successfully typed text into '{el_id}'."

    def _select(self, el_id: str, value: str, reason: str) -> str:
        selector = f"[data-sdet-id='{el_id}']"
        loc = self.page.locator(selector)
        if loc.count() == 0:
            return f"Element '{el_id}' not found on current page."

        try:
            loc.first.select_option(value, timeout=3000)
        except Exception:
            # Fall back to clicking if custom select component
            loc.first.click(timeout=2000)
            self.page.wait_for_timeout(200)

        desc = f"Selected '{value}' in '{el_id}'" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Successfully selected '{value}' in '{el_id}'."

    def _wait(self, seconds: float, reason: str) -> str:
        safe_seconds = min(max(seconds, 0.1), 5.0)
        self.page.wait_for_timeout(int(safe_seconds * 1000))
        desc = f"Waited {safe_seconds}s" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Waited {safe_seconds}s."

    def _assert_text(self, text: str, reason: str) -> str:
        if not text:
            return "Error: No text provided for assertion."

        loc = self.page.get_by_text(text, exact=False)
        visible = loc.count() > 0 and loc.first.is_visible()
        if visible:
            desc = f"Asserted visible text: '{text}'" + (f" ({reason})" if reason else "")
            self.actions_executed.append(desc)
            return f"Assertion passed: '{text}' is visible on screen."
        else:
            desc = f"Assertion failed: '{text}' not found" + (f" ({reason})" if reason else "")
            self.actions_executed.append(f"❌ {desc}")
            return f"Assertion failed: Text '{text}' was not visible on screen."

    def _navigate(self, url: str, reason: str) -> str:
        self.page.goto(url, wait_until="load", timeout=8000)
        time.sleep(0.5)
        desc = f"Navigated to '{url}'" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Navigated to '{url}' successfully."

    def close(self):
        """Safely shuts down Playwright browser resources."""
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

        self._page = None
        self._browser = None
        self._playwright = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
