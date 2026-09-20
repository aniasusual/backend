"""
Tier 1 Context Squashing (Micro-Pruning & Ingestion Compression).

Implements [CP-103.1, Section 3] from the Dynamic Context Management Specification:
1. Ingestion-time tool compression for outputs > 1,800 chars.
2. Lossless disk spillover caching to .lowkey/tool_artifacts/.
3. Line-aware head (35) and tail (35) retention with error-preserving middle scanning.
4. Line-boundary historical tool middle-truncation.
5. Reasoning (<think>) sanitization.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from context.config import ContextConfig


INGESTION_COMPRESSION_THRESHOLD: int = 1800
DEFAULT_HEAD_LINES: int = 35
DEFAULT_TAIL_LINES: int = 35

ERROR_PATTERN = re.compile(
    r"\b(error|errors|exception|exceptions|fail|failed|failure|traceback|syntaxerror|typeerror|referenceerror|assertionerror|valueerror|indexerror|keyerror|fatal|panic|enoent)\b",
    re.IGNORECASE,
)


class ContextSquasher:
    """
    Tier 1 Context Squashing & Ingestion Compression:
    Compresses large tool outputs immediately upon ingestion, preserves error diagnostics,
    persists unabridged spillover logs to disk, and applies line-aware middle-truncation to older turns.
    """

    @classmethod
    def record_tool_result(
        cls,
        messages: List[Dict[str, Any]],
        tool_name: str,
        result: Any,
        project_root: Optional[str | Path] = None,
        is_native_tool_call: bool = True,
    ) -> Dict[str, Any]:
        """
        Records a tool execution result into the conversation message history (CP-103.1):
        1. Compresses outputs exceeding 1,800 chars at ingestion time (35 head / 35 tail lines).
        2. Preserves error signatures and persists lossless spillover logs to .lowkey/tool_artifacts/.
        3. Appends the appropriate role schema (native 'tool' vs conversational 'user' fallback).
        4. Returns the created message dictionary.
        """
        if result is None:
            tool_msg_content = ""
        elif isinstance(result, str):
            tool_msg_content = result
        elif isinstance(result, (dict, list)):
            try:
                tool_msg_content = json.dumps(result, indent=2)
            except Exception:
                tool_msg_content = str(result)
        else:
            tool_msg_content = str(result)

        compressed_content = cls.compress_tool_output(
            text=tool_msg_content,
            tool_name=tool_name,
            project_root=project_root,
        )

        if is_native_tool_call:
            msg: Dict[str, Any] = {"role": "tool", "name": tool_name, "content": compressed_content}
        else:
            msg = {
                "role": "user",
                "content": f"[Tool Result for '{tool_name}']:\n{compressed_content}",
            }

        messages.append(msg)
        return msg

    @classmethod
    def save_spillover_artifact(
        cls,
        text: str,
        tool_name: str,
        project_root: Optional[str | Path] = None,
    ) -> Optional[str]:
        """
        Saves the full uncompressed tool output to disk under .lowkey/tool_artifacts/
        and returns the workspace-relative path for referencing in the context window.
        """
        if not project_root:
            return None

        try:
            root_path = Path(project_root).resolve()
            if not root_path.exists() or not root_path.is_dir():
                return None

            artifacts_dir = root_path / ".lowkey" / "tool_artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)

            clean_name = re.sub(r"[^\w\-]", "_", tool_name).strip("_") or "tool"
            short_id = uuid.uuid4().hex[:8]
            artifact_file = artifacts_dir / f"{clean_name}_{short_id}.log"

            artifact_file.write_text(text, encoding="utf-8", errors="replace")
            return f".lowkey/tool_artifacts/{artifact_file.name}"
        except Exception as e:
            print(f"[ContextSquasher] Failed to save spillover artifact: {e}")
            return None

    @classmethod
    def compress_tool_output(
        cls,
        text: str,
        tool_name: str = "tool",
        project_root: Optional[str | Path] = None,
        max_chars: int = INGESTION_COMPRESSION_THRESHOLD,
        head_lines: int = DEFAULT_HEAD_LINES,
        tail_lines: int = DEFAULT_TAIL_LINES,
    ) -> str:
        """
        Compresses tool outputs exceeding max_chars (1,800 chars) at ingestion time:
        1. Persists full uncompressed raw output to .lowkey/tool_artifacts/ on disk.
        2. Retains the top head_lines (default 35) and bottom tail_lines (default 35).
        3. Scans middle lines for error signatures and retains up to 10 matching failure lines.
        4. Injects an omission banner referencing the saved artifact path for zero-loss random access.
        """
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)

        if len(text) <= max_chars:
            return text

        lines = text.splitlines()

        # If lines fit within head + tail, but total chars exceed max_chars (e.g. minified single lines)
        if len(lines) <= head_lines + tail_lines:
            # Check if any individual line is excessively long
            has_long_line = any(len(l) > 300 for l in lines)
            if not has_long_line:
                return text

        # Save unabridged spillover artifact
        artifact_rel_path = cls.save_spillover_artifact(text, tool_name=tool_name, project_root=project_root)

        if len(lines) > head_lines + tail_lines:
            head = lines[:head_lines]
            tail = lines[-tail_lines:]
            middle = lines[head_lines:-tail_lines]
            omitted_count = len(middle)

            # Scan middle lines for critical error and failure signatures
            preserved_errors: List[str] = []
            for idx, m_line in enumerate(middle):
                if ERROR_PATTERN.search(m_line):
                    line_no = head_lines + idx + 1
                    err_str = m_line.strip()
                    if len(err_str) > 400:
                        err_str = err_str[:400] + "... [truncated line]"
                    preserved_errors.append(f"  [Line {line_no}] {err_str}")
                    if len(preserved_errors) >= 10:
                        break

            # Construct omission banner
            if artifact_rel_path:
                banner = (
                    f"... [Omitted {omitted_count} lines. Full uncompressed output saved to {artifact_rel_path}. "
                    f"Use read_file to inspect specific lines if needed.] ..."
                )
            else:
                omitted_chars = sum(len(l) for l in middle)
                banner = f"... [Omitted {omitted_count} lines / {omitted_chars} chars of intermediate output] ..."

            parts = ["\n".join(head), f"\n{banner}\n"]
            if preserved_errors:
                parts.append("[Preserved middle diagnostics & failure lines]:\n" + "\n".join(preserved_errors) + "\n")
            parts.append("\n".join(tail))

            return "\n".join(parts)

        # Fallback for very few lines with excessive horizontal length
        return cls.middle_truncate(text, max_chars=max_chars, artifact_path=artifact_rel_path)

    @staticmethod
    def middle_truncate(text: str, max_chars: int = 500, artifact_path: Optional[str] = None) -> str:
        """
        Line-aware middle-truncation.
        Preserves top and bottom lines without cutting mid-line or mid-token.
        """
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)

        if len(text) <= max_chars:
            return text

        lines = text.splitlines()
        if len(lines) <= 2:
            # For 1-2 massive lines, slice with character counts
            half = max_chars // 2
            omitted = len(text) - max_chars
            banner = f"... [truncated {omitted} chars"
            if artifact_path:
                banner += f". Full uncompressed output saved to {artifact_path}"
            banner += "] ..."
            return f"{text[:half]}\n{banner}\n{text[-half:]}"

        half_chars = max_chars // 2

        # Collect head lines
        head_lines: List[str] = []
        head_chars = 0
        for line in lines:
            if head_chars + len(line) + 1 > half_chars and head_lines:
                break
            head_lines.append(line)
            head_chars += len(line) + 1

        # Collect tail lines
        tail_lines: List[str] = []
        tail_chars = 0
        for line in reversed(lines):
            if tail_chars + len(line) + 1 > half_chars and tail_lines:
                break
            tail_lines.append(line)
            tail_chars += len(line) + 1
        tail_lines.reverse()

        omitted_lines = max(0, len(lines) - len(head_lines) - len(tail_lines))
        omitted_chars = max(0, len(text) - head_chars - tail_chars)

        banner = f"... [Omitted {omitted_lines} lines / {omitted_chars} chars"
        if artifact_path:
            banner += f". Full uncompressed output saved to {artifact_path}"
        banner += "] ..."

        return (
            "\n".join(head_lines)
            + f"\n{banner}\n"
            + "\n".join(tail_lines)
        )

    @staticmethod
    def sanitize_assistant_history(text: str) -> str:
        """
        Strips internal reasoning (<think> tags) and raw markdown code blocks from past turns
        so the assistant doesn't learn conversational code dumps.
        """
        if not text:
            return ""

        # Strip reasoning tags
        cleaned = re.sub(r"<(think|thought|tool_call|tool_response|tool_code)>[\s\S]*?</\1>", "", text)
        cleaned = re.sub(r"</?(?:think|thought|tool_call|tool_response|tool_code|tool|tools)>", "", cleaned)

        # Strip raw markdown code blocks (```...```)
        cleaned = re.sub(r"```[\w]*\s*\n?[\s\S]*?\n?```", "", cleaned)

        # Collapse excess newlines
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    @staticmethod
    def is_success_milestone(content: str, tool_name: str = "") -> bool:
        """
        Determines whether a tool output represents a validated milestone success.
        - Commands: exit code 0, 'PASS' test runner output, 'Tests: X passed, 0 failed'
        - Linter: '✅ No syntax errors found'
        - Edits/Writes: 'File written successfully', 'Successfully edited', 'Text inserted successfully'
        """
        if not content or not isinstance(content, str):
            return False

        lower = content.lower()

        # Disqualifiers: non-zero exit code or explicit syntax/runtime error indicators
        exit_match = re.search(r"\[Command failed with exit code (\d+)\]", content) or re.search(r"\bexit code (\d+)\b", content, re.IGNORECASE)
        if exit_match and exit_match.group(1) != "0":
            return False
        if "❌ found" in lower:
            return False
        if re.search(r"\b(SyntaxError|TypeError|ReferenceError|UnhandledPromiseRejection|Traceback \(most recent call last\))\b", content):
            return False

        # Positive indicators
        if "✅ no syntax errors found" in lower:
            return True
        if "command completed with exit code 0" in lower:
            return True
        if any(kw in lower for kw in [
            "file written successfully",
            "successfully edited",
            "text inserted successfully",
            "files written successfully",
            "patch applied successfully"
        ]):
            return True

        # Test runner success indicators
        if re.search(r"^\s*PASS\b", content, re.MULTILINE):
            return True
        if re.search(r"\b\d+\s+passed\b", lower) and not re.search(r"\b[1-9]\d*\s+failed\b", lower):
            return True
        if "tests:" in lower and ("0 failed" in lower or ("passed" in lower and "failed" not in lower)):
            return True
        if re.search(r"^\s*OK\s*(?:\(.*\))?$", content, re.MULTILINE):
            return True

        return False

    @classmethod
    def extract_tool_error_summary(cls, content: str, tool_name: str = "", max_chars: int = 350) -> Optional[str]:
        """
        Detects failure signatures in tool outputs and returns a concise, bounded diagnostic summary.
        Detects:
        - Non-zero exit codes: e.g. [Command failed with exit code X], exit code X (where X != 0)
        - Syntax/Linter errors: ❌ Found N syntax error(s), [file.jsx] SyntaxError, esbuild errors
        - Exceptions & stack traces: SyntaxError, TypeError, ReferenceError, Traceback, UnhandledPromiseRejection
        - Test failures: FAIL src/App.test.jsx, Tests: N failed
        """
        if not content or not isinstance(content, str):
            return None

        # If it's a proven success milestone, it's not an error
        if cls.is_success_milestone(content, tool_name):
            return None

        # Check non-zero exit codes
        exit_code_match = re.search(r"\[Command failed with exit code (\d+)\]", content)
        if not exit_code_match:
            exit_code_match = re.search(r"\bexit code (\d+)\b", content, re.IGNORECASE)

        has_non_zero_exit = False
        exit_code_str = ""
        if exit_code_match:
            code = exit_code_match.group(1)
            if code != "0":
                has_non_zero_exit = True
                exit_code_str = f"exit code {code}"

        # Check linter syntax errors
        has_linter_error = "❌ Found" in content or "syntax error" in content.lower()

        # Check test failure
        test_fail_match = re.search(r"\bFAIL\b\s+([^\n]+)", content)
        has_test_fail = bool(test_fail_match or ("tests:" in content.lower() and "failed" in content.lower()))

        # Check generic errors or exceptions
        has_generic_error = (
            content.strip().startswith("Error:")
            or content.strip().startswith("Error executing")
            or bool(re.search(r"\b(?:Error|[A-Z]\w*(?:Error|Exception)|FATAL|UnhandledPromiseRejection|Traceback \(most recent call last\)|npm ERR!)\b", content))
        )
        if not (has_non_zero_exit or has_linter_error or has_test_fail or has_generic_error):
            return None

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return None

        summary_parts = []
        if exit_code_str:
            summary_parts.append(f"Command failed ({exit_code_str})")

        if test_fail_match:
            summary_parts.append(f"FAIL {test_fail_match.group(1).strip()}")

        # Extract up to 3 diagnostic/failure lines
        diag_lines = []
        for line in lines:
            line_lower = line.lower()
            # Skip raw exit code lines if exit_code_str already captured to prevent duplicates
            if exit_code_str and ("exit code" in line_lower or "command failed" in line_lower):
                continue
            if any(k in line_lower for k in ["failed", "error", "syntaxerror", "typeerror", "exception", "traceback", "●", "expected", "received"]):
                if not any(neg in line_lower for neg in ["0 error", "0 failed", "no error", "without error", "zero error"]):
                    diag_lines.append(line)
                    if len(diag_lines) >= 3:
                        break

        if not diag_lines and lines:
            for line in lines[:2]:
                if not (exit_code_str and ("exit code" in line.lower() or "command failed" in line.lower())):
                    diag_lines.append(line)

        for dl in diag_lines:
            if dl not in summary_parts and not any(dl.lower() == sp.lower() for sp in summary_parts):
                summary_parts.append(dl)

        res = " — ".join(summary_parts) if summary_parts else lines[0]
        if len(res) > max_chars:
            res = res[:max_chars].rstrip() + "..."
        return res

    @classmethod
    def rollup_milestones(cls, messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Scans messages for intra-turn execution loops where a tool call failed
        and was subsequently resolved by a successful tool execution.
        Purges the bulky intermediate failure diagnostic output and replaces it with a milestone roll-up marker.
        Spec [CP-103.2]: Once a sub-goal validates successfully (e.g., tests pass),
        intermediate diagnostic conversation iterations are purged and summarized into a single structural success state marker.
        """
        if not messages or len(messages) < 2:
            return messages, False

        import json

        # Helper to extract tool calls and targets from an assistant message
        def _extract_assistant_targets(msg: Dict[str, Any]) -> List[Tuple[str, str]]:
            targets = []
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                    fname = fn.get("name", "")
                    fargs = fn.get("arguments", {})
                    if isinstance(fargs, str):
                        try:
                            fargs = json.loads(fargs)
                        except Exception:
                            fargs = {}
                    target = fargs.get("command") or fargs.get("file_path") or fname
                    targets.append((fname, target))
            else:
                raw_c = msg.get("content", "")
                if "{" in raw_c and "name" in raw_c:
                    try:
                        parsed = json.loads(raw_c)
                        fname = parsed.get("name", "")
                        fargs = parsed.get("arguments", {})
                        target = fargs.get("command") or fargs.get("file_path") or fname
                        targets.append((fname, target))
                    except Exception:
                        pass
            return targets

        # Identify all tool result events with their tool name, target, error status, and success status
        tool_records: List[Dict[str, Any]] = []
        last_assistant_targets: List[Tuple[str, str]] = []

        for idx, m in enumerate(messages):
            role = m.get("role")
            content = m.get("content", "")

            if role == "assistant":
                last_assistant_targets = _extract_assistant_targets(m)
            elif role == "tool" or (role == "user" and isinstance(content, str) and content.startswith("[Tool Result")):
                tool_name = m.get("name", "")
                if not tool_name and isinstance(content, str) and content.startswith("[Tool Result for '"):
                    m_name = re.search(r"\[Tool Result for '([^']+)'\]", content)
                    if m_name:
                        tool_name = m_name.group(1)

                # Match target from last assistant targets (consuming to support multiple tools in one turn)
                target = tool_name
                for target_idx, (fname, ftarget) in enumerate(last_assistant_targets):
                    if fname == tool_name or not tool_name:
                        target = ftarget
                        if not tool_name:
                            tool_name = fname
                        last_assistant_targets.pop(target_idx)
                        break
                is_milestone = cls.is_success_milestone(content, tool_name)
                err_summary = cls.extract_tool_error_summary(content, tool_name)
                is_rolled_up = "[Milestone Roll-up:" in str(content)

                tool_records.append({
                    "msg_idx": idx,
                    "role": role,
                    "tool_name": tool_name,
                    "target": target,
                    "is_milestone": is_milestone,
                    "is_error": bool(err_summary) and not is_milestone,
                    "err_summary": err_summary,
                    "is_rolled_up": is_rolled_up,
                })

        rolled_up_any = False

        # Scan for successful milestones and resolve earlier matching errors
        for j, rec_j in enumerate(tool_records):
            if rec_j["is_milestone"]:
                target_j = rec_j["target"]
                tool_name_j = rec_j["tool_name"]

                # Find any earlier failure with matching target or tool
                for i in range(j):
                    rec_i = tool_records[i]
                    if rec_i["is_error"] and not rec_i["is_rolled_up"]:
                        # Matching target or command
                        same_target = (rec_i["target"] == target_j) or (tool_name_j == rec_i["tool_name"] and target_j == rec_i["target"])
                        # Or test suite rerun: e.g. both are execute_command and test-related
                        is_test_command = "test" in str(rec_i["target"]).lower() and "test" in str(target_j).lower()
                        is_lint_check = "lint" in str(tool_name_j).lower() and ("lint" in str(rec_i["tool_name"]).lower() or rec_i["target"] in str(target_j))

                        if same_target or is_test_command or is_lint_check:
                            # Collapse the earlier error into a milestone roll-up marker
                            msg_idx = rec_i["msg_idx"]
                            old_msg = messages[msg_idx]
                            marker_text = f"[Milestone Roll-up: Prior failure on '{rec_i['target']}' resolved by subsequent successful run.]"

                            if rec_i["role"] == "tool":
                                old_msg["content"] = marker_text
                            else:
                                old_msg["content"] = f"[Tool Result for '{rec_i['tool_name']}']:\n{marker_text}"

                            rec_i["is_rolled_up"] = True
                            rec_i["is_error"] = False
                            rolled_up_any = True

        return messages, rolled_up_any

    @classmethod
    def apply_squash(
        cls,
        messages: List[Dict[str, Any]],
        config: ContextConfig,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Applies in-place squashing to messages:
        1. Collapses intermediate resolved failure loops via Milestone Roll-ups (CP-103.2).
        2. Identifies message-level tool turns.
        3. Preserves the last `preserve_last_n_tools` tool turns intact.
        4. Middle-truncates all older tool results cleanly at line boundaries.
        5. Prunes historical <think> blocks from previous turns.
        """
        if not messages:
            return messages, False

        # 1. Milestone Roll-up pass: collapse intermediate resolved failure loops
        messages, rolled_up = cls.rollup_milestones(messages)
        squashed_any = rolled_up

        # Identify indices of messages that represent tool results
        tool_turn_indices: List[int] = []
        for idx, m in enumerate(messages):
            role = m.get("role")
            content = m.get("content", "")
            if role == "tool":
                tool_turn_indices.append(idx)
            elif role == "user" and isinstance(content, str) and content.startswith("[Tool Result"):
                tool_turn_indices.append(idx)

        # If tool results don't exceed preserve_last_n_tools, nothing to truncate
        cutoff_index = -1
        if len(tool_turn_indices) > config.preserve_last_n_tools:
            # Cutoff is the index of the tool turn right before the preserved tail
            cutoff_index = tool_turn_indices[-(config.preserve_last_n_tools + 1)]

        for idx, m in enumerate(messages):
            role = m.get("role")
            content = m.get("content", "")

            # 2. Middle-truncate older tool results
            if idx <= cutoff_index and idx in tool_turn_indices:
                if isinstance(content, str) and len(content) > config.truncation_length:
                    m["content"] = cls.middle_truncate(content, config.truncation_length)
                    squashed_any = True

            # 3. Prune <think> blocks from all assistant messages except the very last one
            if role == "assistant" and idx < len(messages) - 1:
                if isinstance(content, str) and ("<think>" in content or "<thought>" in content):
                    cleaned = cls.sanitize_assistant_history(content)
                    if cleaned != content:
                        m["content"] = cleaned
                        squashed_any = True

        return messages, squashed_any

