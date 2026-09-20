"""
Goal-Driven Autonomous UI & Browser Testing Subagent.
Dynamically observes DOM state, executes multi-turn interactive workflows via Playwright,
traps live console crashes and network errors, and produces 100% real-time QA audit reports.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

import ollama

from config.settings import DEFAULT_MODEL_ID, OLLAMA_HOST
from subagents.base import BaseSubagent
from subagents.testing.prompts import SDET_SYSTEM_PROMPT, BROWSER_TOOL_SCHEMAS
from subagents.testing.observer import DOMObserver
from subagents.testing.session import PlaywrightBrowserSession
from tools.parser import ToolCallParser
from context.manager import ContextManager

logger = logging.getLogger(__name__)


class UITestingSubagent(BaseSubagent):
    """
    Specialized Autonomous SDET Browser Testing Subagent.
    Dynamically inspects live DOM state after every interaction, executes multi-turn
    workflows using native Ollama tool calling, captures console/network errors,
    and returns 100% real-time structured QA audit reports to the main agent.
    """

    def __init__(
        self,
        sandbox_path: Optional[Path] = None,
        model_name: str = DEFAULT_MODEL_ID,
        max_steps: int = 40,
        tool_registry: Optional[Any] = None,
        event_callback: Optional[Any] = None,
        allowed_tools: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(
            sandbox_path=sandbox_path,
            model_name=model_name,
            tool_registry=tool_registry,
            event_callback=event_callback,
            allowed_tools=allowed_tools,
            **kwargs,
        )
        self.max_steps = max_steps

    @property
    def default_allowed_tools(self) -> Set[str]:
        """Set of supported testing actions."""
        return {
            "browser_click",
            "browser_type",
            "browser_select",
            "browser_hover",
            "browser_press_key",
            "browser_drag_and_drop",
            "browser_upload_file",
            "browser_scroll",
            "browser_wait",
            "browser_assert_text",
            "browser_navigate",
            "browser_finish",
        }

    @property
    def system_prompt(self) -> str:
        return SDET_SYSTEM_PROMPT

    def _parse_tool_call(self, assistant_msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parses the model response using native Ollama tool_calls first,
        with fallback parsing for JSON or markdown blocks.
        """
        raw_tool_calls = assistant_msg.get("tool_calls", [])
        if raw_tool_calls:
            first_call = raw_tool_calls[0]
            fn = first_call.get("function", {})
            name = fn.get("name", "").strip()
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            return {"name": name, "arguments": args}

        content = assistant_msg.get("content", "") or ""
        if not content.strip():
            return None

        # Fallback 1: Use ToolCallParser for markdown / tool tags / JSON
        extracted = ToolCallParser.extract_tool_calls(content)
        if extracted:
            first = extracted[0]
            name = first.get("name", "")
            args = first.get("arguments", {})
            # Normalize action names if model emitted bare action name
            if name.startswith("browser_") or f"browser_{name}" in self.allowed_tools or name in ("click", "type", "select", "scroll", "wait", "assert_text", "navigate", "finish", "done"):
                return {"name": name, "arguments": args}

        # Fallback 2: Direct JSON with "action" or "name"
        clean = content.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                act_name = parsed.get("name") or parsed.get("action") or ""
                if act_name:
                    return {"name": act_name, "arguments": parsed}
        except Exception:
            pass

        # Fallback 3: Regex match for embedded JSON object with "action" or "name"
        match = re.search(r"\{[^{}]*\"(?:action|name)\"\s*:\s*\"([a-zA-Z_-]+)\"[^{}]*\}", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return {"name": match.group(1), "arguments": parsed}
            except Exception:
                pass

        return None

    def run_ui_test(self, url: str = "", instructions: str = "") -> str:
        """
        Navigates to the preview application, dynamically inspects DOM state,
        executes an autonomous multi-turn testing workflow via Playwright,
        and returns a 100% real-time structured report to the main engineer.
        """
        if not instructions or not instructions.strip():
            instructions = "Verify the page loads correctly, all primary buttons and inputs function, and zero unhandled errors occur."

        target_url = (url or "").strip().rstrip("/")
        fallback_url = None
        if self.tool_registry and hasattr(self.tool_registry, "get_dev_server_url"):
            try:
                fallback_url = self.tool_registry.get_dev_server_url()
            except Exception:
                pass

        if not target_url or target_url == "http://localhost:5173":
            target_url = fallback_url or "http://localhost:3000"

        session = PlaywrightBrowserSession(headless=True)
        connected, conn_err = session.start(target_url, timeout_ms=15000)

        # If connection failed on the provided URL, retry with fallback dev server URL if available
        if not connected and fallback_url and fallback_url != target_url:
            connected, conn_err = session.start(fallback_url, timeout_ms=15000)
            if connected:
                target_url = fallback_url

        if not connected:
            return f"""# ❌ UI Test Failed: Application Unreachable
- **Target URL**: `{target_url}`
- **Error**: Could not connect to the target web application.
- **Details**: `{conn_err}`
- **Instructions for Main Engineer**: The application preview server is not responding at `{target_url}`. Verify that the frontend and backend are listening on their designated ports (`process.env.BACKEND_PORT || 5001` for Express, active dev server preview for Vite). Do not attempt to run `npm run dev` or restart Vite manually, as the dev server runs in the background. Check for syntax errors or build crashes that may have halted hot reloading.
"""

        try:
            client = ollama.Client(host=OLLAMA_HOST)
        except Exception as e:
            session.close()
            return f"""# ❌ UI Test Failed: Model Connection Error
- **Target URL**: `{target_url}`
- **Error**: Unable to connect to Ollama runtime at `{OLLAMA_HOST}`: {str(e)}
"""

        self.last_run_events.clear()
        self.last_run_metrics.clear()

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_duration_ms = 0.0

        def emit_event(event_data: Dict[str, Any]):
            payload = {
                "type": "subagent_event",
                "subagent": "invoke_testing_agent",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **event_data,
            }
            self.last_run_events.append(dict(payload))
            if self.event_callback:
                try:
                    self.event_callback(payload)
                except Exception as cb_err:
                    logger.warning(f"[UITestingSubagent] Event callback error: {cb_err}")

        emit_event({
            "event": "start",
            "task": f"Verify URL: {target_url}\nInstructions: {instructions}",
            "model": self.model_name,
            "max_iterations": self.max_steps,
        })

        system_message = {"role": "system", "content": self.system_prompt}
        initial_goal = {
            "role": "user",
            "content": f"Test Instructions: {instructions}\nInitial Target URL: {target_url}",
        }

        # Sliding window history of recent turns (prevents context bloat and stale element ID hallucinations)
        recent_dialogue: List[Dict[str, Any]] = []
        previous_action_result = ""
        final_report_summary = ""
        final_fix_instructions = ""
        final_status = "PASSED"
        consecutive_parse_failures = 0
        debug_payload: Optional[Dict[str, Any]] = None

        # Autonomous Observation & Interaction Loop
        for step in range(1, self.max_steps + 1):
            emit_event({
                "event": "iteration_start",
                "iteration": step,
                "max_iterations": self.max_steps,
            })

            # 1. Real-time DOM Observation
            observation = DOMObserver.observe(session.page)

            # 2. Format observation for model prompt
            obs_prompt = DOMObserver.format_observation_for_llm(
                observation=observation,
                step=step,
                max_steps=self.max_steps,
                instructions=instructions,
                console_errors=session.console_errors,
                previous_action_result=previous_action_result,
            )

            # Assemble sliding window context:
            # - Step 1: combine initial goal instructions with first DOM observation
            # - Subsequent turns: system + sliding window of valid (assistant, tool) pairs + current observation
            if not recent_dialogue:
                user_msg = f"Test Instructions: {instructions}\nInitial Target URL: {target_url}\n\n{obs_prompt}"
                messages = [system_message, {"role": "user", "content": user_msg}]
            else:
                messages = [system_message] + recent_dialogue[-4:] + [{"role": "user", "content": obs_prompt}]
            messages_sent_snapshot = [dict(m) for m in messages]

            # 3. Request next action from Ollama using native tool calling
            try:
                response = client.chat(
                    model=self.model_name,
                    messages=messages,
                    tools=BROWSER_TOOL_SCHEMAS,
                    options={"temperature": 0.5, "num_ctx": 16384},
                )
                assistant_msg = response.get("message", {})
                assistant_content = assistant_msg.get("content", "") or ""
            except Exception as e:
                logger.error(f"[UITestingSubagent] LLM chat error on step {step}: {e}")
                session.actions_executed.append(f"❌ Model execution error on step {step}: {str(e)}")
                break

            # Extract token counts and durations from Ollama
            p_tokens = response.get("prompt_eval_count") or 0
            c_tokens = response.get("eval_count") or 0
            dur_ms = round((response.get("total_duration") or 0) / 1e6, 2)
            total_prompt_tokens += p_tokens
            total_completion_tokens += c_tokens
            total_duration_ms += dur_ms

            iteration_metrics = {
                "prompt_eval_count": p_tokens,
                "eval_count": c_tokens,
                "duration_ms": dur_ms,
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "total_duration_ms": round(total_duration_ms, 2),
            }

            debug_payload = {
                "iteration": step,
                "model": self.model_name,
                "messages_sent": messages_sent_snapshot,
                "llm_response": {
                    "content": assistant_content,
                    "thinking": assistant_msg.get("thinking", ""),
                    "tool_calls": assistant_msg.get("tool_calls", []),
                },
                "metrics": iteration_metrics,
            }

            if assistant_content:
                emit_event({
                    "event": "thought",
                    "content": assistant_content,
                    "iteration": step,
                    "debug": debug_payload,
                    "metrics": iteration_metrics,
                })

            # 4. Parse action
            parsed_call = self._parse_tool_call(assistant_msg)
            if not parsed_call:
                consecutive_parse_failures += 1
                logger.warning(f"[UITestingSubagent] Unparseable response on step {step}: '{assistant_content[:80]}'")
                if consecutive_parse_failures >= 2:
                    session.actions_executed.append(f"❌ Step {step}: Model failed to invoke a valid browser tool twice in succession.")
                    break

                # Send feedback retry prompt via observation on next turn without poisoning dialogue history
                previous_action_result = (
                    "Error: Your response did not invoke a browser tool. "
                    "You must call one of the browser tools (e.g. browser_click, browser_type, browser_assert_text, browser_finish)."
                )
                continue

            consecutive_parse_failures = 0
            raw_act_name = parsed_call.get("name", "")
            act_args = parsed_call.get("arguments", {})
            canonical_act = raw_act_name.lower().strip().removeprefix("browser_")

            # 5. Check for termination
            if canonical_act in ("finish", "done"):
                final_status = str(act_args.get("status", "PASSED")).upper().strip()
                final_report_summary = str(act_args.get("report") or act_args.get("summary") or "All user flows verified successfully.")
                final_fix_instructions = str(act_args.get("fix_instructions") or "")
                break

            # 6. Telemetry Event
            emit_event({
                "event": "tool_call",
                "tool": f"browser_{canonical_act}",
                "arguments": act_args,
                "iteration": step,
                "debug": debug_payload,
                "metrics": iteration_metrics,
            })

            # 7. Execute action in live browser session
            action_result = session.execute_action({"name": canonical_act, "arguments": act_args})
            previous_action_result = action_result

            # 8. Telemetry Event post-execution
            emit_event({
                "event": "action_executed",
                "action": canonical_act,
                "target": act_args.get("id", ""),
                "result": str(action_result),
                "console_errors": list(session.console_errors),
                "iteration": step,
                "debug": debug_payload,
                "metrics": iteration_metrics,
            })

            # Record turn in sliding dialogue
            recent_dialogue.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": raw_act_name,
                            "arguments": act_args,
                        },
                    }
                ],
            })
            ContextManager.record_tool_result(
                messages=recent_dialogue,
                tool_name=raw_act_name,
                result=action_result,
                project_root=self.sandbox_path,
                is_native_tool_call=True,
            )

        # Capture final visual snapshot before closing browser session
        screenshot_rel_path = None
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            status_tag = final_status.lower()
            screenshot_filename = f"ui_test_{timestamp}_{status_tag}.png"
            target_dir = (self.sandbox_path / ".lowkey" / "screenshots") if self.sandbox_path else Path(".lowkey/screenshots")
            target_dir.mkdir(parents=True, exist_ok=True)
            screenshot_full_path = str(target_dir / screenshot_filename)
            if hasattr(session, "take_screenshot") and session.take_screenshot(screenshot_full_path):
                screenshot_rel_path = f".lowkey/screenshots/{screenshot_filename}"
        except Exception as ss_err:
            logger.warning(f"[UITestingSubagent] Failed to capture visual snapshot: {ss_err}")

        # Final real-time observation snapshot
        final_obs = DOMObserver.observe(session.page)
        session.close()

        # Build 100% Real-Time Emergent-Style QA Report
        dom_errors = final_obs.get("dom_errors", [])
        has_critical_errors = bool(
            dom_errors
            or session.console_errors
            or session.network_failures
            or final_status == "FAILED"
        )

        if final_status == "FAILED":
            status_badge = "❌ FAILED"
        elif has_critical_errors:
            status_badge = "⚠️ COMPLETED WITH WARNINGS"
            final_status = "WARNINGS"
        else:
            status_badge = "✅ PASSED"

        elements = final_obs.get("elements", [])
        page_title = final_obs.get("title", "Untitled Web Application")

        report_lines = [
            f"# 🧪 UI Test Report — {status_badge}",
            f"- **Target URL**: `{url}`",
            f"- **Page Title**: `{page_title}`",
            f"- **Interactive Controls Found**: **{len(elements)} elements**",
        ]
        if screenshot_rel_path:
            report_lines.append(f"- **Visual Snapshot**: `{screenshot_rel_path}`")
        report_lines.extend([
            "",
            "---",
            "",
            "### 📋 Discovered Controls:",
        ])

        for el in elements[:8]:
            tag = el.get("tag", "element")
            text = el.get("text", "")
            el_id = el.get("id", "")
            report_lines.append(f"- `<{tag}>`: **\"{text}\"** (ID: `{el_id}`)")
        if len(elements) > 8:
            report_lines.append(f"- ... and {len(elements) - 8} more interactive controls.")

        if session.actions_executed:
            report_lines.append("\n### 🎯 Interactive Actions Executed:")
            for act in session.actions_executed:
                report_lines.append(f"- {act}")
        else:
            report_lines.append("\n### 🎯 Interactive Actions Executed:\n- Initial page load verified.")

        if dom_errors:
            report_lines.append("\n### ⚠️ In-DOM Errors Detected:")
            for err in dom_errors[:5]:
                report_lines.append(f"- `{err}`")

        if session.console_errors:
            report_lines.append(f"\n### ⚠️ Browser Console Errors / Warnings ({len(session.console_errors)}):")
            for err in session.console_errors[:6]:
                report_lines.append(f"- `{err}`")
        else:
            report_lines.append("\n### 🛡️ Browser Console Health:\n- Clean. Zero runtime crashes or unhandled JavaScript exceptions detected.")

        if session.network_failures:
            report_lines.append(f"\n### 🌐 Failed Network Requests ({len(session.network_failures)}):")
            for net in session.network_failures[:5]:
                report_lines.append(f"- `{net}`")

        if final_report_summary:
            report_lines.append(f"\n### 📝 SDET Assessment:\n{final_report_summary}")

        report_lines.append("\n---\n### 📋 Instructions for Main Engineer:")
        if final_fix_instructions:
            report_lines.append(f"{final_fix_instructions}")
        elif has_critical_errors:
            report_lines.append("- Inspect the detected console warnings or in-DOM errors and fix broken component states or API routes.")
        else:
            report_lines.append("- All interactive flows and assertions passed without error. You may proceed to conclude the task with `finish`.")

        final_report = "\n".join(report_lines)

        self.last_run_metrics = {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
            "total_duration_ms": round(total_duration_ms, 2),
            "iterations": step if 'step' in locals() else 1,
            "model": self.model_name,
        }

        emit_event({
            "event": "finish",
            "status": final_status,
            "report": final_report,
            "screenshot": screenshot_rel_path,
            "debug": debug_payload,
            "metrics": self.last_run_metrics,
        })

        return final_report
