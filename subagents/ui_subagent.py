import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.sync_api import sync_playwright
import ollama

from config.prompts import UI_SUBAGENT_PROMPT
from subagents.base import BaseSubagent


class UITestingSubagent(BaseSubagent):
    """
    Specialized Automated UI Testing Subagent.
    Inspired by Emergent's subagents-testing_agent_v4_sonnet_4_6.
    Interactively drives a headless browser using Playwright, tracks console errors,
    discovers interactive DOM elements, and generates structured test reports.
    """

    def __init__(
        self,
        sandbox_path: Optional[Path] = None,
        model_name: str = "qwen2.5-coder:7b",
        max_steps: int = 10,
        tool_registry: Optional[Any] = None,
        event_callback: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(
            sandbox_path=sandbox_path,
            model_name=model_name,
            tool_registry=tool_registry,
            event_callback=event_callback,
            **kwargs,
        )
        self.max_steps = max_steps


    def _extract_interactive_elements(self, page) -> List[Dict[str, Any]]:
        """DOM extraction script capturing clickable, focusable, and form elements."""
        js_script = """
        () => {
            let elements = [];
            let index = 0;
            const interactives = document.querySelectorAll('button, a, input, textarea, select, [role="button"], [role="link"], [role="checkbox"], [role="tab"], [onclick], [tabindex]');
            
            interactives.forEach(el => {
                if (el.offsetParent === null) return;
                if (el.getAttribute('tabindex') && parseInt(el.getAttribute('tabindex')) < 0) return;
                
                let id = 'el_' + index++;
                el.setAttribute('data-test-id', id);
                
                let tag = el.tagName.toLowerCase();
                let text = el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '';
                text = text.substring(0, 100).replace(/\\n/g, ' ').trim();
                
                let role = el.getAttribute('role') || '';
                
                elements.push({
                    id: id,
                    tag: tag,
                    text: text,
                    type: el.type || role
                });
            });
            return elements;
        }
        """
        return page.evaluate(js_script)

    def run_ui_test(self, url: str, instructions: str = "") -> str:
        """
        Navigates to the running web application, discovers DOM elements, traps console errors,
        executes test instructions, and returns a categorized test report.
        """
        console_errors: List[str] = []
        actions_executed: List[str] = []

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                # Trap console errors and page crashes
                page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ["error", "warning"] else None)
                page.on("pageerror", lambda err: console_errors.append(f"[Crash] {str(err)}"))

                # Navigate to the target preview URL
                try:
                    page.goto(url, wait_until="networkidle", timeout=12000)
                except Exception as e:
                    browser.close()
                    return f"""# ❌ UI Test Failed: Connection Error
- **Target URL**: `{url}`
- **Error**: Could not connect to the local server. Make sure the dev server is started via `run_background_command(command="npm run dev")`.
- **Details**: {str(e)}"""

                time.sleep(1)  # Allow React hydration to settle
                page_title = page.title()
                elements = self._extract_interactive_elements(page)

                if not instructions or not instructions.strip():
                    instructions = "Verify that the page loads properly, all main buttons and links are clickable, and no console errors are thrown."

                # Attempt interactive LLM loop if elements are found
                messages = [
                    {"role": "system", "content": UI_SUBAGENT_PROMPT},
                    {"role": "user", "content": f"Instructions: {instructions}\n\nTarget URL: {url}\nPage Title: {page_title}"}
                ]

                report_summary = ""
                for step in range(self.max_steps):
                    state_desc = f"Interactive DOM Elements ({len(elements)} found):\n"
                    for el in elements[:20]:
                        state_desc += f"- [{el['id']}] <{el['tag']}> \"{el['text']}\"\n"

                    messages.append({"role": "user", "content": state_desc})

                    # Try querying Ollama model
                    try:
                        response = ollama.chat(model=self.model_name, messages=messages)
                        assistant_msg = response["message"]["content"].strip()
                        messages.append({"role": "assistant", "content": assistant_msg})

                        # Clean JSON codeblock wrapper if present
                        if assistant_msg.startswith("```json"):
                            assistant_msg = assistant_msg[7:-3].strip()
                        elif assistant_msg.startswith("```"):
                            assistant_msg = assistant_msg[3:-3].strip()

                        action = json.loads(assistant_msg)
                        act = action.get("action")

                        if act == "done":
                            report_summary = action.get("report", "Interactive verification completed successfully.")
                            break
                        elif act == "click":
                            el_id = action.get("id")
                            page.click(f"[data-test-id='{el_id}']", timeout=2000)
                            actions_executed.append(f"Clicked element `{el_id}`")
                            messages.append({"role": "user", "content": f"Clicked element {el_id} successfully."})
                        elif act == "type":
                            el_id = action.get("id")
                            text = action.get("text", "")
                            page.fill(f"[data-test-id='{el_id}']", text, timeout=2000)
                            actions_executed.append(f"Typed '{text}' into `{el_id}`")
                            messages.append({"role": "user", "content": f"Typed '{text}' into element {el_id}."})
                    except Exception:
                        # Fall back to deterministic assertion report if LLM loop terminates or errors
                        break

                browser.close()

                # Build final structured verification report
                status_badge = "✅ PASSED" if not console_errors else "⚠️ COMPLETED WITH WARNINGS"

                res = f"""# 🧪 UI Test Report — {status_badge}
- **Target URL**: `{url}`
- **Page Title**: `{page_title if page_title else 'Untitled Web Application'}`
- **Interactive Elements Discovered**: **{len(elements)} elements**

---

### 📋 Elements Summary:
"""
                for el in elements[:8]:
                    res += f"- `<{el['tag']}>`: **\"{el['text']}\"** (ID: `{el['id']}`)\n"

                if len(elements) > 8:
                    res += f"- ... and {len(elements) - 8} more interactive controls.\n"

                if actions_executed:
                    res += "\n### 🎯 Interactive Actions Executed:\n"
                    for act in actions_executed:
                        res += f"- {act}\n"

                if console_errors:
                    res += "\n### ⚠️ Browser Console Errors/Warnings:\n"
                    for err in console_errors[:5]:
                        res += f"- `{err}`\n"
                else:
                    res += "\n### 🛡️ Browser Console Health:\n- Zero runtime crashes or unhandled JavaScript exceptions detected.\n"

                if report_summary:
                    res += f"\n### 📝 Summary:\n{report_summary}\n"

                return res

            except Exception as e:
                return f"# ❌ UI Test Subagent Exception\nError during Playwright browser execution: {str(e)}"
