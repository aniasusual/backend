"""
Goal-Driven Autonomous UI & Browser Testing Subagent.
Inspired by Emergent's SDET architecture (testing_agent_v4 & run_browser_use).
Dynamically observes DOM state, drives user workflows, detects in-DOM errors and console crashes,
and generates structured QA audit reports with actionable fix instructions.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

import ollama

from config.settings import DEFAULT_MODEL_ID, OLLAMA_HOST
from subagents.base import BaseSubagent
from subagents.testing.prompts import SDET_SYSTEM_PROMPT, FALLBACK_SMOKE_REPORT_TEMPLATE
from subagents.testing.observer import DOMObserver
from subagents.testing.session import PlaywrightBrowserSession

logger = logging.getLogger(__name__)


class UITestingSubagent(BaseSubagent):
    """
    Specialized Autonomous SDET Browser Testing Subagent.
    Dynamically inspects live DOM state after every interaction, executes multi-turn
    workflows, traps in-DOM errors and console crashes, and produces Emergent-style QA reports.
    """

    def __init__(
        self,
        sandbox_path: Optional[Path] = None,
        model_name: str = DEFAULT_MODEL_ID,
        max_steps: int = 8,
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

    @property
    def allowed_tools(self) -> Set[str]:
        """Set of supported testing actions."""
        return {"click", "type", "select", "wait", "assert_text", "navigate", "done"}

    @property
    def system_prompt(self) -> str:
        return SDET_SYSTEM_PROMPT

    def _clean_and_parse_action(self, text: str) -> Optional[Dict[str, Any]]:
        """Extracts and deserializes JSON action object from model response."""
        if not text:
            return None

        content = text.strip()
        # Remove code block markdown if present
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # Direct JSON parse attempt
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "action" in parsed:
                return parsed
        except Exception:
            pass

        # Regex fallback to find nested JSON object containing "action"
        match = re.search(r"\{[^{}]*\"action\"\s*:\s*\"[a-zA-Z_-]+\"[^{}]*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict) and "action" in parsed:
                    return parsed
            except Exception:
                pass

        return None

    def _run_deterministic_smoke(
        self,
        session: PlaywrightBrowserSession,
        observation: Dict[str, Any],
        instructions: str,
    ) -> str:
        """
        Resilient smoke test fallback executed if the LLM loop encounters errors.
        Clicks primary buttons/links and captures console/DOM errors deterministically.
        """
        elements = observation.get("elements", [])
        page_title = observation.get("title", "Untitled Web Application")
        url = observation.get("url", "")
        dom_errors = observation.get("dom_errors", [])

        # Click up to 2 primary interactive elements to verify responsiveness
        clicked = []
        for el in elements:
            if el.get("tag") in ["button", "a"] and not el.get("disabled"):
                try:
                    session.execute_action({"action": "click", "id": el["id"], "reason": "Smoke check element"})
                    clicked.append(f"Clicked `<{el['tag']}>` \"{el['text']}\" (ID: `{el['id']}`)")
                    if len(clicked) >= 2:
                        break
                except Exception:
                    pass

        # Re-observe post-clicks
        post_obs = DOMObserver.observe(session.page)
        final_errors = post_obs.get("dom_errors", dom_errors)

        has_issues = bool(final_errors or session.console_errors or session.network_failures)
        status_badge = "⚠️ COMPLETED WITH WARNINGS" if has_issues else "✅ PASSED"

        elements_summary = "\n".join(
            [f"- `<{el['tag']}>`: **\"{el['text']}\"** (ID: `{el['id']}`)" for el in elements[:6]]
        ) or "- No interactive controls found."

        actions_summary = "\n".join([f"- {act}" for act in session.actions_executed]) or "- Initial page load verified."

        dom_errors_summary = (
            "\n".join([f"- `{err}`" for err in final_errors[:5]])
            if final_errors
            else "- None detected in visible DOM."
        )

        console_health_summary = (
            "\n".join([f"- `{err}`" for err in session.console_errors[:5]])
            if session.console_errors
            else "- Zero runtime crashes or unhandled JavaScript exceptions detected."
        )

        fix_instructions = (
            "Review detected warnings or console errors and verify component error boundaries."
            if has_issues
            else "No blocking UI regressions detected. You may proceed to conclude the task with `finish`."
        )

        return FALLBACK_SMOKE_REPORT_TEMPLATE.format(
            status_badge=status_badge,
            url=url,
            page_title=page_title,
            elements_count=len(elements),
            elements_summary=elements_summary,
            actions_summary=actions_summary,
            dom_errors_summary=dom_errors_summary,
            console_health_summary=console_health_summary,
            fix_instructions=fix_instructions,
        )

    def run_ui_test(self, url: str, instructions: str = "") -> str:
        """
        Navigates to the preview application, dynamically inspects DOM state,
        executes an intelligent multi-turn testing workflow, and returns a structured report.
        """
        if not instructions or not instructions.strip():
            instructions = "Verify page loads properly, all main buttons and links function, and no errors or crashes occur."

        session = PlaywrightBrowserSession(headless=True)
        connected, conn_err = session.start(url, timeout_ms=15000)

        if not connected:
            return f"""# ❌ UI Test Failed: Connection Error
- **Target URL**: `{url}`
- **Error**: Could not connect to the target web application.
- **Details**: `{conn_err}`
- **Instructions for Main Engineer**: Ensure the preview server is active by calling `run_background_command(command="npm run dev")`.
"""

        try:
            # Client connection to Ollama
            client = ollama.Client(host=OLLAMA_HOST)
        except Exception as e:
            logger.warning(f"[UITestingSubagent] Failed to create Ollama client: {e}. Using deterministic smoke fallback.")
            initial_obs = DOMObserver.observe(session.page)
            res = self._run_deterministic_smoke(session, initial_obs, instructions)
            session.close()
            return res

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": f"Test Instructions: {instructions}\nInitial Target URL: {url}",
            },
        ]

        previous_action_result = ""
        final_report_summary = ""
        final_fix_instructions = ""
        final_status = "PASSED"
        used_fallback = False

        # Autonomous Observation & Interaction Loop
        for step in range(1, self.max_steps + 1):
            if self.event_callback:
                self.event_callback({
                    "type": "subagent_event",
                    "subagent": "invoke_testing_agent",
                    "event": "iteration_start",
                    "iteration": step,
                    "max_iterations": self.max_steps,
                })

            # 1. Dynamic DOM Observation after every interaction
            observation = DOMObserver.observe(session.page)

            # 2. Format observation for model prompt
            obs_prompt = DOMObserver.format_observation_for_llm(
                observation=observation,
                step=step,
                max_steps=self.max_steps,
                console_errors=session.console_errors,
                previous_action_result=previous_action_result,
            )
            messages.append({"role": "user", "content": obs_prompt})

            # 3. Request next action from Ollama
            try:
                response = client.chat(
                    model=self.model_name,
                    messages=messages,
                    options={"temperature": 0.0},
                )
                assistant_content = response.get("message", {}).get("content", "").strip()
            except Exception as e:
                logger.warning(f"[UITestingSubagent] LLM chat failed on step {step}: {e}. Falling back to deterministic smoke.")
                used_fallback = True
                break

            messages.append({"role": "assistant", "content": assistant_content})

            # 4. Parse action
            action = self._clean_and_parse_action(assistant_content)
            if not action:
                # If model failed to provide valid action JSON, attempt fallback extraction or smoke
                logger.info(f"[UITestingSubagent] Unparseable response on step {step}: '{assistant_content[:60]}'")
                if step == 1:
                    used_fallback = True
                    break
                else:
                    previous_action_result = "Invalid action format. Please emit a valid JSON action."
                    continue

            act = action.get("action", "").lower().strip()

            # 5. Check if subagent concluded testing
            if act == "done":
                final_status = action.get("status", "PASSED").upper()
                final_report_summary = action.get("report", "Interactive verification completed successfully.")
                final_fix_instructions = action.get("fix_instructions", "")
                break

            # 6. Execute action in browser session
            action_result = session.execute_action(action)
            previous_action_result = action_result

            # 7. Telemetry callback
            if self.event_callback:
                self.event_callback({
                    "type": "subagent_event",
                    "subagent": "invoke_testing_agent",
                    "event": "action_executed",
                    "action": act,
                    "target": action.get("id", ""),
                    "iteration": step,
                })

        # Post-loop check: if fallback triggered
        if used_fallback:
            latest_obs = DOMObserver.observe(session.page)
            report = self._run_deterministic_smoke(session, latest_obs, instructions)
            session.close()
            return report

        # Final dynamic observation for the report
        final_obs = DOMObserver.observe(session.page)
        session.close()

        # Build Final Structured Emergent-Style QA Report
        dom_errors = final_obs.get("dom_errors", [])
        has_errors = bool(dom_errors or session.console_errors or session.network_failures or final_status == "FAILED")

        if final_status == "FAILED":
            status_badge = "❌ FAILED"
        elif has_errors:
            status_badge = "⚠️ COMPLETED WITH WARNINGS"
        else:
            status_badge = "✅ PASSED"

        elements = final_obs.get("elements", [])
        page_title = final_obs.get("title", "Untitled Web Application")

        res = f"""# 🧪 UI Test Report — {status_badge}
- **Target URL**: `{url}`
- **Page Title**: `{page_title}`
- **Interactive Controls Discovered**: **{len(elements)} controls**

---

### 📋 Elements Summary:
"""
        for el in elements[:8]:
            res += f"- `<{el['tag']}>`: **\"{el['text']}\"** (ID: `{el['id']}`)\n"
        if len(elements) > 8:
            res += f"- ... and {len(elements) - 8} more interactive controls.\n"

        if session.actions_executed:
            res += "\n### 🎯 Interactive Actions Executed:\n"
            for act in session.actions_executed:
                res += f"- {act}\n"

        if dom_errors:
            res += "\n### ⚠️ In-DOM Errors Detected:\n"
            for err in dom_errors[:5]:
                res += f"- `{err}`\n"

        if session.console_errors:
            res += "\n### ⚠️ Browser Console Errors / Warnings:\n"
            for err in session.console_errors[:5]:
                res += f"- `{err}`\n"
        else:
            res += "\n### 🛡️ Browser Console Health:\n- Zero runtime crashes or unhandled JavaScript exceptions detected.\n"

        if session.network_failures:
            res += "\n### 🌐 Failed Network Requests:\n"
            for net in session.network_failures[:5]:
                res += f"- `{net}`\n"

        if final_report_summary:
            res += f"\n### 📝 SDET Assessment:\n{final_report_summary}\n"

        res += "\n---\n### 📋 Instructions for Main Engineer:\n"
        if final_fix_instructions:
            res += f"{final_fix_instructions}\n"
        elif has_errors:
            res += "- Inspect the detected console warnings or in-DOM errors and fix broken component states or API routes.\n"
        else:
            res += "- All tested user flows passed without error. You may proceed to conclude the task with `finish`.\n"

        return res
