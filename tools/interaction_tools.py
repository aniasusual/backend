from typing import Any, Dict, List, Optional, Callable


class InteractionTools:
    """
    Dedicated handler for structured human-in-the-loop interaction (clarifying questions,
    option selection chips) and task lifecycle finalization (structured summaries, next steps).
    """

    def __init__(self, event_callback: Optional[Callable[[dict], None]] = None, sandbox_path: Optional[Any] = None):
        self.event_callback = event_callback
        self.sandbox_path = sandbox_path
        self._browser_session: Optional[PlaywrightBrowserSession] = None

    @property
    def browser_session(self) -> "PlaywrightBrowserSession":
        if self._browser_session is None:
            self._browser_session = PlaywrightBrowserSession(self.sandbox_path)
        return self._browser_session

    async def browser_navigate(self, url: str) -> str:
        """Navigate browser to a URL and inspect the resulting DOM state and errors."""
        try:
            return await self.browser_session.navigate(url)
        except Exception as e:
            return f"Error navigating to {url}: {str(e)}"

    async def browser_click(self, selector: str) -> str:
        """Click on an interactive element by data-sdet-id (e.g. 'el_0') or CSS selector."""
        try:
            return await self.browser_session.click(selector)
        except Exception as e:
            return f"Error clicking {selector}: {str(e)}"

    async def browser_fill(self, selector: str, value: str) -> str:
        """Fill an input field or textarea by data-sdet-id (e.g. 'el_1') or CSS selector."""
        try:
            return await self.browser_session.fill(selector, value)
        except Exception as e:
            return f"Error filling {selector}: {str(e)}"

    async def browser_snapshot(self) -> str:
        """Inspect the current active browser page DOM state, error notices, and interactive elements."""
        try:
            return await self.browser_session.snapshot()
        except Exception as e:
            return f"Error inspecting DOM: {str(e)}"

    async def browser_screenshot(self, file_path: Optional[str] = None) -> str:
        """Take a screenshot of the active browser page."""
        try:
            return await self.browser_session.screenshot(file_path)
        except Exception as e:
            return f"Error capturing screenshot: {str(e)}"

    async def browser_scroll(self, direction: str = "down", amount: int = 500) -> str:
        """Scroll the page 'up' or 'down' by a specified pixel amount."""
        try:
            return await self.browser_session.scroll(direction, amount)
        except Exception as e:
            return f"Error scrolling: {str(e)}"

    def cleanup(self):
        """Clean up and close active Playwright browser session."""
        if self._browser_session:
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                loop.create_task(self._browser_session.close())
            except RuntimeError:
                try:
                    import asyncio
                    asyncio.run(self._browser_session.close())
                except Exception:
                    pass
            except Exception:
                pass
            self._browser_session = None
    def ask_human(self, question: str, options: Optional[List[str]] = None) -> str:
        """Ask the human user a clarifying question or present multiple design/architecture options.

        Args:
            question: The question or clarification prompt to ask the user.
            options: Optional list of selectable choice strings (e.g. ['Tailwind CSS', 'Vanilla CSS', 'Dark Mode']).

        Returns:
            A formatted acknowledgement indicating the question was dispatched to the user.
        """
        if not question or not question.strip():
            return "Error: question parameter must not be empty."

        clean_question = question.strip()
        opts_list = options if isinstance(options, list) else []

        payload = {
            "type": "ask_human",
            "question": clean_question,
            "options": opts_list,
        }

        if self.event_callback:
            self.event_callback(payload)

        formatted = f"❓ [Question sent to user]: {clean_question}"
        if opts_list:
            formatted += "\nOptions provided:\n" + "\n".join(f"  - {opt}" for opt in opts_list)

        return formatted

    def finish(self, summary: str, next_steps: Optional[str] = None) -> str:
        """Conclude the current task and provide a structured summary of accomplishments and next steps.

        Args:
            summary: Comprehensive summary of all files created/edited, features implemented, and verification results.
            next_steps: Optional guidance on how to run, test, or extend the app.

        Returns:
            A formatted completion confirmation.
        """
        if not summary or not summary.strip():
            return "Error: summary parameter must not be empty."

        clean_summary = summary.strip()
        clean_next = next_steps.strip() if next_steps else None

        payload = {
            "type": "task_finished",
            "summary": clean_summary,
            "next_steps": clean_next,
        }

        if self.event_callback:
            self.event_callback(payload)

        res = f"🎉 [Task Completed Successfully]\n\n**Summary:**\n{clean_summary}"
        if clean_next:
            res += f"\n\n**Next Steps:**\n{clean_next}"

        return res


class PlaywrightBrowserSession:
    """Manages an active Playwright browser instance and page context for UI testing."""

    def __init__(self, sandbox_path: Optional[Any] = None):
        self.sandbox_path = sandbox_path
        self.playwright = None
        self.browser = None
        self.page = None
        self.console_logs: List[str] = []
        self.step_count = 0

    async def ensure_page(self):
        if self.page and not self.page.is_closed():
            return self.page

        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        context = await self.browser.new_context(viewport={"width": 1280, "height": 800})
        self.page = await context.new_page()

        def handle_console(msg):
            text = f"[{msg.type.upper()}] {msg.text}"
            self.console_logs.append(text)
            if len(self.console_logs) > 50:
                self.console_logs.pop(0)

        def handle_error(err):
            self.console_logs.append(f"[PAGE_ERROR] {err}")

        self.page.on("console", handle_console)
        self.page.on("pageerror", handle_error)
        return self.page

    async def navigate(self, url: str) -> str:
        page = await self.ensure_page()
        self.step_count += 1
        clean_url = url.strip()
        if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
            clean_url = f"http://{clean_url}"

        await page.goto(clean_url, timeout=15000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        obs = await DOMObserver.observe(page)
        return DOMObserver.format_observation_for_llm(
            observation=obs,
            step=self.step_count,
            max_steps=20,
            instructions=f"Navigated to {clean_url}",
            console_errors=self.console_logs,
        )

    async def click(self, selector_or_id: str) -> str:
        page = await self.ensure_page()
        self.step_count += 1
        target = str(selector_or_id).strip()
        if target.startswith("el_") or target.isdigit():
            clean_id = target if target.startswith("el_") else f"el_{target}"
            target = f'[data-sdet-id="{clean_id}"]'

        await page.click(target, timeout=5000)
        await page.wait_for_timeout(500)
        obs = await DOMObserver.observe(page)
        return DOMObserver.format_observation_for_llm(
            observation=obs,
            step=self.step_count,
            max_steps=20,
            instructions=f"Clicked '{selector_or_id}'",
            console_errors=self.console_logs,
        )

    async def fill(self, selector_or_id: str, value: str) -> str:
        page = await self.ensure_page()
        self.step_count += 1
        target = str(selector_or_id).strip()
        if target.startswith("el_") or target.isdigit():
            clean_id = target if target.startswith("el_") else f"el_{target}"
            target = f'[data-sdet-id="{clean_id}"]'

        await page.fill(target, value, timeout=5000)
        await page.wait_for_timeout(300)
        obs = await DOMObserver.observe(page)
        return DOMObserver.format_observation_for_llm(
            observation=obs,
            step=self.step_count,
            max_steps=20,
            instructions=f"Filled '{selector_or_id}' with '{value}'",
            console_errors=self.console_logs,
        )

    async def snapshot(self) -> str:
        page = await self.ensure_page()
        self.step_count += 1
        obs = await DOMObserver.observe(page)
        return DOMObserver.format_observation_for_llm(
            observation=obs,
            step=self.step_count,
            max_steps=20,
            instructions="Current live application state",
            console_errors=self.console_logs,
        )

    async def screenshot(self, file_path: Optional[str] = None) -> str:
        page = await self.ensure_page()
        import tempfile
        from pathlib import Path
        save_path = Path(file_path) if file_path else Path(tempfile.gettempdir()) / f"screenshot_{self.step_count}.png"
        await page.screenshot(path=str(save_path))
        return f"Screenshot saved to '{save_path}'."

    async def scroll(self, direction: str = "down", amount: int = 500) -> str:
        page = await self.ensure_page()
        self.step_count += 1
        delta = amount if direction == "down" else -amount
        await page.evaluate(f"window.scrollBy(0, {delta});")
        await page.wait_for_timeout(300)
        obs = await DOMObserver.observe(page)
        return DOMObserver.format_observation_for_llm(
            observation=obs,
            step=self.step_count,
            max_steps=20,
            instructions=f"Scrolled {direction} by {amount}px",
            console_errors=self.console_logs,
        )

    async def close(self):
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass
        finally:
            self.page = None
            self.browser = None
            self.playwright = None
class DOMObserver:
    """
    Evaluates page state in real-time using Playwright page context.
    Discovers interactive elements and captures in-DOM error notices.
    """

    EXTRACT_ELEMENTS_SCRIPT = """
    () => {
        let elements = [];
        let index = 0;
        const selector = 'button, a, input, textarea, select, [role="button"], [role="link"], [role="checkbox"], [role="tab"], [role="menuitem"], [onclick], [tabindex]';
        const interactives = document.querySelectorAll(selector);

        interactives.forEach(el => {
            if (el.offsetParent === null && el.tagName.toLowerCase() !== 'body') return;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
            if (el.getAttribute('tabindex') && parseInt(el.getAttribute('tabindex')) < 0) return;

            let sdetId = 'el_' + index++;
            el.setAttribute('data-sdet-id', sdetId);

            let tag = el.tagName.toLowerCase();
            let text = el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || el.getAttribute('title') || '';
            text = text.substring(0, 80).replace(/\\n/g, ' ').trim();

            let role = el.getAttribute('role') || '';
            let type = el.getAttribute('type') || role;
            let placeholder = el.getAttribute('placeholder') || '';
            let testId = el.getAttribute('data-testid') || el.getAttribute('data-test-id') || '';
            let name = el.getAttribute('name') || '';
            let isDisabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
            let isChecked = el.checked || el.getAttribute('aria-checked') === 'true';

            elements.push({
                id: sdetId,
                tag: tag,
                type: type,
                text: text,
                placeholder: placeholder,
                testid: testId,
                name: name,
                disabled: isDisabled,
                checked: isChecked,
            });
        });

        const canScrollDown = (window.innerHeight + window.scrollY) < document.documentElement.scrollHeight - 20;

        return {
            elements: elements,
            can_scroll_down: canScrollDown,
            scroll_y: Math.round(window.scrollY),
            page_height: document.documentElement.scrollHeight,
        };
    }
    """

    EXTRACT_ERRORS_SCRIPT = """
    () => {
        const errorSelectors = '.error, [class*="error"], [id*="error"], [role="alert"], [aria-invalid="true"], .alert, .text-destructive';
        const errorNodes = document.querySelectorAll(errorSelectors);
        let errors = [];

        errorNodes.forEach(node => {
            if (node.offsetParent === null) return;
            const style = window.getComputedStyle(node);
            if (style.display === 'none' || style.visibility === 'hidden') return;

            let text = node.innerText ? node.innerText.trim() : '';
            if (text && text.length > 0 && text.length < 300 && !errors.includes(text)) {
                errors.push(text);
            }
        });
        return errors;
    }
    """

    @classmethod
    async def observe(cls, page: Any) -> Dict[str, Any]:
        """
        Executes in-page inspection to capture dynamic elements and in-DOM error notices.
        """
        try:
            eval_res = await page.evaluate(cls.EXTRACT_ELEMENTS_SCRIPT)
            elements = eval_res.get("elements", []) if isinstance(eval_res, dict) else []
            can_scroll_down = eval_res.get("can_scroll_down", False) if isinstance(eval_res, dict) else False
        except Exception:
            elements = []
            can_scroll_down = False

        try:
            dom_errors = await page.evaluate(cls.EXTRACT_ERRORS_SCRIPT)
        except Exception:
            dom_errors = []

        try:
            title = await page.title()
        except Exception:
            title = "Untitled Page"

        try:
            url = page.url
        except Exception:
            url = ""

        return {
            "url": url,
            "title": title,
            "elements": elements,
            "dom_errors": dom_errors,
            "can_scroll_down": can_scroll_down,
        }
    @classmethod
    def format_observation_for_llm(
        cls,
        observation: Dict[str, Any],
        step: int,
        max_steps: int,
        instructions: str = "",
        console_errors: Optional[List[str]] = None,
        previous_action_result: str = "",
    ) -> str:
        """
        Formats real-time DOM snapshot, active errors, and console health into prompt state.
        """
        if console_errors is None:
            console_errors = []

        elements = observation.get("elements", [])
        dom_errors = observation.get("dom_errors", [])
        can_scroll_down = observation.get("can_scroll_down", False)
        title = observation.get("title", "")
        url = observation.get("url", "")

        out = [f"### [Step {step}/{max_steps}] Live Application Observation"]
        if instructions:
            out.append(f"- **Testing Instructions**: {instructions}")
        out.append(f"- **Active URL**: `{url}` | **Page Title**: `{title}`")

        if previous_action_result:
            out.append(f"- **Previous Action Result**: {previous_action_result}")

        if dom_errors and isinstance(dom_errors, list):
            out.append("\n⚠️ **IN-DOM ERROR ALERTS ON PAGE**:")
            for err in dom_errors[:5]:
                out.append(f"  - {err}")
        else:
            out.append("- **In-DOM Errors**: None visible.")
        if console_errors:
            out.append(f"- **Browser Console/Runtime Logs ({len(console_errors)})**:")
            for cerr in console_errors[-4:]:
                out.append(f"  - `{cerr}`")
        else:
            out.append("- **Browser Console Health**: Clean. Zero uncaught exceptions or network crashes.")

        if can_scroll_down:
            out.append("- **Scroll Status**: Page extends below viewport.")

        out.append(f"\n📋 **Interactive Controls Discovered ({len(elements)} total)**:")
        if not elements:
            out.append("  (No interactive elements currently visible)")
        else:
            for el in elements[:28]:
                details = []
                if el.get("testid"):
                    details.append(f"testid='{el['testid']}'")
                if el.get("type"):
                    details.append(f"type='{el['type']}'")
                if el.get("placeholder"):
                    details.append(f"placeholder='{el['placeholder']}'")
                if el.get("name"):
                    details.append(f"name='{el['name']}'")
                if el.get("disabled"):
                    details.append("DISABLED")
                if el.get("checked"):
                    details.append("CHECKED")

                detail_str = f" ({', '.join(details)})" if details else ""
                el_id = el.get("id", "el")
                el_tag = el.get("tag", "element")
                el_text = el.get("text", "")
                out.append(f'  - [{el_id}] <{el_tag}> "{el_text}"{detail_str}')
            if len(elements) > 28:
                out.append(f"  - ... and {len(elements) - 28} more elements.")

        return "\n".join(out)
