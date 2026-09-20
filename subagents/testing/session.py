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

            # 4. Native Dialog (alert / confirm / prompt) Auto-Acceptor
            def on_dialog(dialog):
                dialog_text = dialog.message
                self.actions_executed.append(f"Auto-accepted browser dialog [{dialog.type}]: '{dialog_text}'")
                try:
                    dialog.accept()
                except Exception:
                    pass

            self._page.on("dialog", on_dialog)

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
        Normalizes both tool-call dictionaries and legacy action dictionaries.
        """
        args = action.get("arguments", {}) if isinstance(action.get("arguments"), dict) else action
        raw_name = action.get("name") or action.get("action") or ""
        act = raw_name.lower().strip().removeprefix("browser_")

        el_id = str(args.get("id") or args.get("element_id") or "").strip()
        reason = str(args.get("reason") or "").strip()

        try:
            if act == "click":
                return self._click(el_id, reason)
            elif act == "type":
                text = str(args.get("text", ""))
                raw_enter = args.get("press_enter", False)
                if isinstance(raw_enter, str):
                    press_enter = raw_enter.strip().lower() in ("true", "1", "yes")
                else:
                    press_enter = bool(raw_enter)
                return self._type(el_id, text, reason, press_enter)
            elif act == "select":
                value = str(args.get("value", ""))
                return self._select(el_id, value, reason)
            elif act == "hover":
                return self._hover(el_id, reason)
            elif act == "press_key":
                key = str(args.get("key", "Escape"))
                return self._press_key(key, reason)
            elif act == "drag_and_drop":
                source_id = str(args.get("source_id") or el_id)
                target_id = str(args.get("target_id") or "")
                return self._drag_and_drop(source_id, target_id, reason)
            elif act == "upload_file":
                file_path = str(args.get("file_path", ""))
                return self._upload_file(el_id, file_path, reason)
            elif act == "scroll":
                direction = str(args.get("direction", "down"))
                return self._scroll(direction, reason)
            elif act == "wait":
                seconds = float(args.get("seconds", 1.0))
                return self._wait(seconds, reason)
            elif act == "assert_text":
                text = str(args.get("text", ""))
                return self._assert_text(text, reason)
            elif act == "navigate":
                url = str(args.get("url", ""))
                return self._navigate(url, reason)
            elif act in ("finish", "done"):
                return "Session finished."
            else:
                return f"Error: Unsupported action '{act}'."
        except Exception as e:
            err_line = str(e).split("\n")[0]
            target_str = f" on '{el_id}'" if el_id else ""
            err_msg = f"Failed action '{act}'{target_str}: {err_line}"
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
            # Retry with force=True to bypass modal/backdrop overlays
            loc.first.click(force=True, timeout=2000)

        # Smart settling: allow async network calls or animations to settle
        try:
            self.page.wait_for_load_state("networkidle", timeout=1200)
        except Exception:
            self.page.wait_for_timeout(400)

        desc = f"Clicked '{el_id}'" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Successfully clicked '{el_id}'."

    def _type(self, el_id: str, text: str, reason: str, press_enter: bool = False) -> str:
        selector = f"[data-sdet-id='{el_id}']"
        loc = self.page.locator(selector)
        if loc.count() == 0:
            return f"Element '{el_id}' not found on current page."

        loc.first.fill(text, timeout=3000)
        if press_enter:
            loc.first.press("Enter", timeout=2000)
            try:
                self.page.wait_for_load_state("networkidle", timeout=1200)
            except Exception:
                self.page.wait_for_timeout(400)

        enter_note = " (pressed Enter)" if press_enter else ""
        desc = f"Typed '{text}' into '{el_id}'{enter_note}" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Successfully typed text into '{el_id}'{enter_note}."

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
            self.page.wait_for_timeout(300)

        desc = f"Selected '{value}' in '{el_id}'" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Successfully selected '{value}' in '{el_id}'."

    def _hover(self, el_id: str, reason: str) -> str:
        selector = f"[data-sdet-id='{el_id}']"
        loc = self.page.locator(selector)
        if loc.count() == 0:
            return f"Element '{el_id}' not found on current page."

        loc.first.hover(timeout=3000)
        self.page.wait_for_timeout(300)
        desc = f"Hovered on '{el_id}'" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Successfully hovered over '{el_id}'."

    def _press_key(self, key: str, reason: str) -> str:
        clean_key = str(key or "Escape").strip()
        self.page.keyboard.press(clean_key)
        self.page.wait_for_timeout(300)
        desc = f"Pressed key '{clean_key}'" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Successfully pressed key '{clean_key}'."

    def _drag_and_drop(self, source_id: str, target_id: str, reason: str) -> str:
        src_sel = f"[data-sdet-id='{source_id}']"
        dst_sel = f"[data-sdet-id='{target_id}']"
        src_loc = self.page.locator(src_sel)
        dst_loc = self.page.locator(dst_sel)
        if src_loc.count() == 0:
            return f"Source element '{source_id}' not found on current page."
        if dst_loc.count() == 0:
            return f"Target element '{target_id}' not found on current page."

        src_loc.first.drag_to(dst_loc.first, timeout=4000)
        self.page.wait_for_timeout(400)
        desc = f"Dragged '{source_id}' onto '{target_id}'" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Successfully dragged '{source_id}' to '{target_id}'."

    def _upload_file(self, el_id: str, file_path: str, reason: str) -> str:
        selector = f"[data-sdet-id='{el_id}']"
        loc = self.page.locator(selector)
        if loc.count() == 0:
            return f"Element '{el_id}' not found on current page."

        loc.first.set_input_files(file_path, timeout=3000)
        self.page.wait_for_timeout(300)
        desc = f"Uploaded '{file_path}' into '{el_id}'" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Successfully set file '{file_path}' on '{el_id}'."

    def _scroll(self, direction: str, reason: str) -> str:
        dir_clean = direction.lower().strip() if direction else "down"
        delta_y = 500 if dir_clean == "down" else -500
        self.page.mouse.wheel(0, delta_y)
        self.page.wait_for_timeout(350)
        desc = f"Scrolled {dir_clean}" + (f" ({reason})" if reason else "")
        self.actions_executed.append(desc)
        return f"Scrolled viewport {dir_clean} by 500px."

    def _wait(self, seconds: float, reason: str) -> str:
        safe_seconds = min(max(seconds, 0.1), 3.0)
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

    def take_screenshot(self, output_path: str) -> bool:
        """Captures a screenshot of the active page and saves it to output_path."""
        if not self._page:
            return False
        try:
            self._page.screenshot(path=output_path, full_page=False)
            return True
        except Exception as e:
            logger.warning(f"[PlaywrightBrowserSession] Screenshot capture failed: {e}")
            return False

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
