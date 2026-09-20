"""
Dynamic DOM State Observer & In-DOM Error Extractor.
Extracts clickable, focusable, and form elements, assigns step-scoped IDs,
and scans for in-DOM error messages following Emergent's SDET inspection patterns.
"""

from typing import Dict, Any, List


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
            // Skip non-visible elements
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
    def observe(cls, page) -> Dict[str, Any]:
        """
        Executes in-page inspection to capture dynamic elements and in-DOM error notices.
        """
        try:
            eval_res = page.evaluate(cls.EXTRACT_ELEMENTS_SCRIPT)
            elements: List[Dict[str, Any]] = eval_res.get("elements", [])
            can_scroll_down: bool = eval_res.get("can_scroll_down", False)
        except Exception:
            elements = []
            can_scroll_down = False

        try:
            dom_errors: List[str] = page.evaluate(cls.EXTRACT_ERRORS_SCRIPT)
        except Exception:
            dom_errors = []

        try:
            title = page.title()
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
        console_errors: List[str] = None,
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

        # In-DOM Errors
        if dom_errors:
            out.append("\n⚠️ **IN-DOM ERROR ALERTS ON PAGE**:")
            for err in dom_errors[:5]:
                out.append(f"  - {err}")
        else:
            out.append("- **In-DOM Errors**: None visible.")

        # Console / Crash Status
        if console_errors:
            out.append(f"- **Browser Console/Runtime Logs ({len(console_errors)})**:")
            for cerr in console_errors[-4:]:
                out.append(f"  - `{cerr}`")
        else:
            out.append("- **Browser Console Health**: Clean. Zero uncaught exceptions or network crashes.")

        if can_scroll_down:
            out.append("- **Scroll Status**: Page extends below viewport. You can call `browser_scroll(direction='down')` if needed.")

        # Interactive Controls
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
                out.append(f"  - [{el['id']}] <{el['tag']}> \"{el['text']}\"{detail_str}")

            if len(elements) > 28:
                out.append(f"  - ... and {len(elements) - 28} more elements.")

        out.append("\nDecide your next action by invoking one of the browser tools (or browser_finish to conclude):")
        return "\n".join(out)
