"""
Master Context Manager for Lowkey.

Orchestrates in-loop squashing, inter-turn preparation, and macro-compaction.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from context.config import (
    ContextConfig,
    ALERT_EVICTION_MARKER,
)

from context.estimator import TokenEstimator
from context.squasher import ContextSquasher
from context.compactor import ContextCompactor
from context.static_layer import StaticLayerManager


class ContextManager:
    """
    Master Context Manager for Lowkey.
    Orchestrates in-loop squashing, inter-turn preparation, and macro-compaction.
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
        Records a tool execution result into the conversation message history (CP-103.1).
        Delegates to ContextSquasher.record_tool_result.
        """
        return ContextSquasher.record_tool_result(
            messages=messages,
            tool_name=tool_name,
            result=result,
            project_root=project_root,
            is_native_tool_call=is_native_tool_call,
        )

    @staticmethod
    def sanitize_assistant_text(text: str) -> str:
        """Sanitizes assistant text by removing thinking tags and markdown code blocks."""
        return ContextSquasher.sanitize_assistant_history(text)

    @staticmethod
    def compact_prior_turns(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Compacts past completed turns into clean (user, assistant) message pairs.
        Preserves questions asked via ask_human, files modified, and retained tool errors / milestones (CP-103.2).
        """
        if not messages:
            return []

        compacted: List[Dict[str, Any]] = []
        current_user = None
        current_assistant_content: List[str] = []
        modified_files: List[str] = []
        inspected_files: List[str] = []
        asked_questions: List[str] = []
        invoked_actions: List[str] = []
        has_finish: bool = False
        finish_summary: str = ""

        recent_tool_targets: List[Tuple[str, str]] = []
        unresolved_errors: Dict[str, Tuple[str, str]] = {}
        resolved_milestones: List[str] = []

        def _process_tool_result(content: str, tool_name: str, role: str):
            nonlocal unresolved_errors, resolved_milestones, recent_tool_targets
            if not tool_name and role == "user" and content.startswith("[Tool Result for '"):
                m_name = re.search(r"\[Tool Result for '([^']+)'\]", content)
                if m_name:
                    tool_name = m_name.group(1)

            target = tool_name
            for target_idx, (fname, ftarget) in enumerate(recent_tool_targets):
                if fname == tool_name or not tool_name:
                    target = ftarget
                    if not tool_name:
                        tool_name = fname
                    recent_tool_targets.pop(target_idx)
                    break

            is_milestone = ContextSquasher.is_success_milestone(content, tool_name)
            err_summary = ContextSquasher.extract_tool_error_summary(content, tool_name)

            if is_milestone:
                matched_keys = [
                    k for k in unresolved_errors.keys()
                    if k == target
                    or (tool_name == "execute_command" and "test" in str(k).lower() and "test" in str(target).lower())
                    or (tool_name == "lint_javascript" and "lint" in str(k).lower())
                    or (str(k) in str(target) or str(target) in str(k))
                ]
                for k in matched_keys:
                    unresolved_errors.pop(k, None)
                    resolved_milestones.append(f"{target} passed after retry")
            elif err_summary:
                unresolved_errors[target] = (tool_name, err_summary)

        def _finalize_turn():
            nonlocal current_assistant_content, modified_files, inspected_files
            nonlocal asked_questions, invoked_actions, has_finish, finish_summary
            nonlocal unresolved_errors, resolved_milestones, recent_tool_targets

            raw_text = " ".join(current_assistant_content).strip()
            sanitized_text = ContextSquasher.sanitize_assistant_history(raw_text)

            parts = []
            if sanitized_text:
                parts.append(sanitized_text)
            if invoked_actions:
                parts.append(f"{'; '.join(invoked_actions)}.")
            if asked_questions:
                parts.append(f"Question asked: {asked_questions[-1]}")
            if modified_files:
                parts.append(f"Updated files: {', '.join(sorted(set(modified_files)))}.")
            elif inspected_files:
                parts.append(f"Inspected files: {', '.join(sorted(set(inspected_files)))}.")
            elif has_finish:
                parts.append(finish_summary or "Task finished.")

            if unresolved_errors:
                err_lines = [f"- [{t_name}] {err}" for _, (t_name, err) in unresolved_errors.items()]
                parts.append("Failures / Unresolved Errors:\n" + "\n".join(err_lines))

            if resolved_milestones:
                unique_milestones = list(dict.fromkeys(resolved_milestones))
                parts.append(f"Milestones resolved: {'; '.join(unique_milestones)}.")

            final_text = "\n".join(parts) if parts else "Understood."
            compacted.append({"role": "user", "content": current_user})
            compacted.append({"role": "assistant", "content": final_text})

            current_assistant_content = []
            modified_files = []
            inspected_files = []
            asked_questions = []
            invoked_actions = []
            has_finish = False
            finish_summary = ""
            unresolved_errors = {}
            resolved_milestones = []
            recent_tool_targets = []

        for m in messages:
            role = m.get("role")
            content = m.get("content", "")

            if role == "system":
                continue

            elif role == "user":
                # Fallback tool executions append messages as {"role": "user", "content": "[Tool Result for '...']: ..."}
                if isinstance(content, str) and content.startswith("[Tool Result"):
                    _process_tool_result(content=content, tool_name="", role="user")
                    continue

                if current_user:
                    _finalize_turn()
                clean_user = content
                if ALERT_EVICTION_MARKER in clean_user:
                    clean_user = clean_user.replace(ALERT_EVICTION_MARKER, "").strip()
                current_user = clean_user

            elif role == "tool":
                _process_tool_result(content=content, tool_name=m.get("name", ""), role="tool")

            elif role == "assistant":
                recent_tool_targets = []
                if content:
                    current_assistant_content.append(content)
                    if "{" in content and "name" in content:
                        try:
                            parsed = json.loads(content)
                            fn_name = parsed.get("name", "")
                            args = parsed.get("arguments", {})
                            target = args.get("command") or args.get("file_path") or fn_name
                            recent_tool_targets.append((fn_name, target))
                        except Exception:
                            pass

                if m.get("tool_calls"):
                    for tc in m["tool_calls"]:
                        fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                        fn_name = fn.get("name", "")
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {}

                        target = args.get("command") or args.get("file_path") or fn_name
                        recent_tool_targets.append((fn_name, target))

                        if fn_name == "ask_human":
                            q = args.get("question") or args.get("prompt")
                            opts = args.get("options")
                            if q:
                                q_str = q
                                if opts and isinstance(opts, list):
                                    q_str += f" (Options: {', '.join(str(o) for o in opts)})"
                                asked_questions.append(q_str)
                        elif fn_name == "task":
                            ag = args.get("agent", "task")
                            if ag == "scout":
                                invoked_actions.append("Explored codebase structure and architecture")
                            elif ag == "reviewer":
                                invoked_actions.append("Audited code quality, security, and React/Express architecture")
                            elif ag == "troubleshoot":
                                invoked_actions.append("Diagnosed runtime issue with Troubleshoot subagent")
                            elif ag == "design":
                                invoked_actions.append("Applied design system tokens to src/index.css")
                            elif ag == "tester":
                                invoked_actions.append("Ran automated UI verification tests")
                            else:
                                invoked_actions.append(f"Delegated task to {ag} subagent")
                        elif fn_name == "invoke_design_agent":
                            invoked_actions.append("Applied design system tokens to src/index.css")
                        elif fn_name == "invoke_troubleshoot_agent":
                            invoked_actions.append("Diagnosed runtime issue with Troubleshoot subagent")
                        elif fn_name == "invoke_vision_agent":
                            invoked_actions.append("Audited UI design polish with Vision subagent")
                        elif fn_name == "invoke_testing_agent":
                            invoked_actions.append("Ran automated UI verification tests")
                        elif fn_name == "invoke_code_reviewer_agent":
                            invoked_actions.append("Audited code quality, security, and React/Express architecture")
                        elif fn_name.startswith("invoke_"):
                            subagent_title = fn_name.replace("invoke_", "").replace("_", " ").title()
                            invoked_actions.append(f"Executed {subagent_title} subagent")
                        elif fn_name in ["execute_command", "run_background_command"]:
                            cmd = args.get("command", "")
                            if cmd:
                                invoked_actions.append(f"Executed command: {cmd}")
                        elif fn_name == "finish":
                            has_finish = True
                            if args.get("summary"):
                                finish_summary = args.get("summary")

                        file_path = args.get("file_path")
                        if file_path:
                            if fn_name in ["write_file", "edit_file", "insert_text"]:
                                modified_files.append(file_path)
                            elif fn_name == "read_file":
                                inspected_files.append(file_path)

                        batch_files = args.get("files")
                        if isinstance(batch_files, list):
                            for bf in batch_files:
                                if isinstance(bf, dict) and bf.get("file_path"):
                                    modified_files.append(bf["file_path"])

        if current_user:
            _finalize_turn()

        return compacted


    RAM_HEADER: str = "=============================================================================\n[DYNAMIC ENVIRONMENT RAM REGISTER - MOUNTED ACTIVE FILES]\n============================================================================="
    RAM_FOOTER: str = "=============================================================================\n[END DYNAMIC ENVIRONMENT RAM REGISTER]\n============================================================================="

    @classmethod
    def format_virtual_ram_block(cls, mounted_virtual_ram: Optional[Dict[str, str]]) -> str:
        """
        Formats active mounted files into the dedicated Dynamic Virtual RAM Register block.
        Spec [CP-101.2]: Pinned volatile working memory directly beneath the Static Layer.
        """
        if not mounted_virtual_ram:
            return ""

        parts = [
            cls.RAM_HEADER,
            "The following files are actively mounted in your working memory.",
            "You do NOT need to call read_file on these files. They reflect live workspace state.",
            "When you edit these files, this register is automatically synchronized.",
            "Call unmount_file(file_path=\"...\") when finished with a file to free working memory.\n",
        ]

        for path in sorted(mounted_virtual_ram.keys()):
            content = mounted_virtual_ram[path]
            lines = content.splitlines()
            total_lines = len(lines)
            parts.append(f"--- FILE: {path} ({total_lines} lines) ---")
            parts.append(content)
            parts.append("")

        parts.append(cls.RAM_FOOTER)
        return "\n".join(parts)

    @classmethod
    def sync_virtual_ram_block(cls, messages: List[Dict[str, Any]], mounted_virtual_ram: Optional[Dict[str, str]]) -> None:
        """
        Synchronizes the Dynamic Virtual RAM Register inside the system message (messages[0]).
        If files are mounted, updates or appends the RAM register block.
        If all files are unmounted, removes the RAM register block to free context.
        """
        if not messages or messages[0].get("role") != "system":
            return

        sys_content = messages[0].get("content", "")
        new_ram_block = cls.format_virtual_ram_block(mounted_virtual_ram) if mounted_virtual_ram else ""

        if cls.RAM_HEADER in sys_content:
            start_idx = sys_content.find(cls.RAM_HEADER)
            end_idx = sys_content.find(cls.RAM_FOOTER, start_idx + len(cls.RAM_HEADER))
            if end_idx != -1:
                end_idx += len(cls.RAM_FOOTER)
                if new_ram_block:
                    updated_content = sys_content[:start_idx] + new_ram_block + sys_content[end_idx:]
                else:
                    prefix = sys_content[:start_idx].rstrip()
                    suffix = sys_content[end_idx:].lstrip()
                    updated_content = f"{prefix}\n\n{suffix}".strip() if suffix else prefix
                messages[0]["content"] = updated_content
        else:
            if new_ram_block:
                messages[0]["content"] = f"{sys_content.rstrip()}\n\n{new_ram_block.strip()}"

    ALERT_EVICTION_MARKER: str = ALERT_EVICTION_MARKER

    @classmethod
    def enforce_rolling_budget(
        cls,
        messages: List[Dict[str, Any]],
        target_limit: Optional[int] = None,
        config: Optional[ContextConfig] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        virtual_ram: Optional[Dict[str, str]] = None,
        max_messages: Optional[int] = None,
    ) -> bool:
        """
        Rolling FIFO eviction loop matching CP-103.2 and CP-106.
        When total tokens exceed target_limit (or message count exceeds max_messages),
        pops earliest dynamic turns from messages[1] (preserving messages[0] Static Layer)
        and injects ALERT_EVICTION_MARKER into the remaining conversation head.

        Enforces critical production invariants:
        1. Static Layer Preservation: messages[0] is pinned and preserved if role == "system".
        2. Tool Transaction Integrity: If an assistant message with tool_calls is evicted,
           all its corresponding tool result messages are evicted atomically.
        3. Orphaned Tool Cleanup: No orphaned tool messages can sit at the head of dynamic context.
        4. Turn Alternation & Continuity: Injects ALERT_EVICTION_MARKER cleanly without creating
           broken role sequences (e.g. user -> tool or consecutive duplicate user turns).
        5. Strict Budget & Count Bounds: Enforces len(messages) <= max_messages and
           total_tokens <= target_limit even after alert injection.
        """
        if not messages:
            return False

        has_system = bool(messages[0].get("role") == "system")
        drop_idx = 1 if has_system else 0
        min_len = 2 if has_system else 1

        if len(messages) <= min_len:
            return False

        if config is None:
            config = ContextConfig()

        if target_limit is None:
            target_limit = int(config.context_window * config.compact_threshold)

        if max_messages is None and config.max_history_messages:
            max_messages = config.max_history_messages

        def _get_tokens() -> int:
            return TokenEstimator.estimate_total(messages, tools=tools, virtual_ram=virtual_ram)

        def _is_over_budget(current_tokens: int) -> bool:
            if current_tokens > target_limit:
                return True
            if max_messages and len(messages) > max_messages:
                return True
            return False

        def _pop_at_drop_idx() -> Dict[str, Any]:
            popped = messages.pop(drop_idx)
            # If popped message was an assistant with tool_calls, evict all following tool responses atomically
            if popped.get("role") == "assistant" and popped.get("tool_calls"):
                while len(messages) > min_len and messages[drop_idx].get("role") == "tool":
                    messages.pop(drop_idx)
            return popped

        total_tokens = _get_tokens()
        is_over = _is_over_budget(total_tokens)
        has_orphaned_tool = bool(len(messages) > min_len and messages[drop_idx].get("role") == "tool")

        if not is_over and not has_orphaned_tool:
            return False

        evicted = False

        # Evict messages until budget and message count constraints are satisfied
        while len(messages) > min_len and _is_over_budget(total_tokens):
            _pop_at_drop_idx()
            evicted = True
            total_tokens = _get_tokens()

        # Clean any orphaned tool responses sitting at the head of dynamic context
        while len(messages) > min_len and messages[drop_idx].get("role") == "tool":
            messages.pop(drop_idx)
            evicted = True
            total_tokens = _get_tokens()

        if evicted and len(messages) >= min_len:
            # Check if ALERT_EVICTION_MARKER already present in remaining conversation head
            has_marker = any(
                ALERT_EVICTION_MARKER in str(m.get("content") or "")
                for m in messages[drop_idx : drop_idx + 2]
            )
            if not has_marker and len(messages) > drop_idx:
                head_role = messages[drop_idx].get("role")
                if head_role == "user":
                    user_content = str(messages[drop_idx].get("content") or "").strip()
                    messages[drop_idx]["content"] = (
                        f"{ALERT_EVICTION_MARKER}\n\n{user_content}".strip()
                        if user_content
                        else ALERT_EVICTION_MARKER
                    )
                else:
                    # Assistant message at head: insert user alert turn to preserve alternation
                    messages.insert(drop_idx, {"role": "user", "content": ALERT_EVICTION_MARKER})

            # Post-injection invariant check: ensure inserting/prepending did not exceed limits
            # If max_messages or target_limit exceeded due to inserted alert, trim subsequent messages
            total_tokens = _get_tokens()
            while len(messages) > min_len and _is_over_budget(total_tokens):
                if len(messages) <= drop_idx + 1:
                    break
                # messages[drop_idx] is the alert marker; trim at drop_idx + 1
                popped = messages.pop(drop_idx + 1)
                if popped.get("role") == "assistant" and popped.get("tool_calls"):
                    while len(messages) > min_len and len(messages) > drop_idx + 1 and messages[drop_idx + 1].get("role") == "tool":
                        messages.pop(drop_idx + 1)
                # If the next message is a user message, merge the alert into it cleanly
                if len(messages) > drop_idx + 1 and messages[drop_idx + 1].get("role") == "user":
                    user_content = str(messages[drop_idx + 1].get("content") or "").strip()
                    messages[drop_idx + 1]["content"] = (
                        f"{ALERT_EVICTION_MARKER}\n\n{user_content}".strip()
                        if user_content
                        else ALERT_EVICTION_MARKER
                    )
                    messages.pop(drop_idx)
                total_tokens = _get_tokens()
        return evicted

    _enforce_rolling_budget = enforce_rolling_budget

    @classmethod
    def prepare_messages(
        cls,
        user_prompt: str,
        system_prompt: str,
        existing_messages: List[Dict[str, Any]],
        model_name: str = "qwen2.5-coder:14b",
        tools: Optional[List[Dict[str, Any]]] = None,
        project_root: Optional[str | Path] = None,
        mounted_virtual_ram: Optional[Dict[str, str]] = None,
        config: Optional[ContextConfig] = None,
    ) -> List[Dict[str, Any]]:
        """
        Prepares message history for a new user turn:
        1. Compacts prior completed turns into clean, code-free user/assistant pairs.
        2. Preserves in-flight questions asked via ask_human.
        3. Appends the new user prompt.
        4. Runs macro-compaction if total token estimate exceeds compact_threshold.
        5. Mounts discovered Static Layer repository rules if project_root provided and not already present.
        6. Mounts Dynamic Virtual RAM Register if mounted_virtual_ram provided.
        """
        if config is None:
            config = ContextConfig.for_model(model_name)

        # Mount repository rules if project_root provided and not already present in system_prompt
        effective_system_prompt = system_prompt
        if project_root and "## Repository Directives & Guidelines" not in effective_system_prompt:
            rule_info = StaticLayerManager.discover_project_rules(project_root)
            if rule_info:
                rules_block = StaticLayerManager.format_rules_block(rule_info)
                if rules_block:
                    effective_system_prompt = f"{effective_system_prompt.rstrip()}\n\n{rules_block.strip()}"

        # Mount Dynamic Virtual RAM Register if files are currently mounted
        if mounted_virtual_ram and cls.RAM_HEADER not in effective_system_prompt:
            ram_block = cls.format_virtual_ram_block(mounted_virtual_ram)
            if ram_block:
                effective_system_prompt = f"{effective_system_prompt.rstrip()}\n\n{ram_block.strip()}"

        # 1. Compact prior turns
        compacted_history = cls.compact_prior_turns(existing_messages)

        # 2. Rebuild message list with system prompt
        existing_messages.clear()
        existing_messages.append({"role": "system", "content": effective_system_prompt})
        existing_messages.extend(compacted_history)

        # 3. Append user prompt
        existing_messages.append({"role": "user", "content": user_prompt.strip()})

        # 4. Check if token count exceeds compact threshold (82%)
        total_tokens = TokenEstimator.estimate_total(existing_messages, tools=tools, virtual_ram=mounted_virtual_ram)
        compact_limit = int(config.context_window * config.compact_threshold)

        if total_tokens >= compact_limit and len(existing_messages) > 6:
            # Macro-compaction: Keep system prompt (index 0) and the last 4 messages intact
            system_msg = existing_messages[0]
            tail_messages = existing_messages[-4:]
            messages_to_summarize = existing_messages[1:-4]

            synthetic_analysis = ContextCompactor.generate_synthetic_head(messages_to_summarize)

            existing_messages.clear()
            existing_messages.append(system_msg)
            existing_messages.append({"role": "user", "content": synthetic_analysis})
            existing_messages.append({"role": "assistant", "content": "Understood. Proceeding with active task."})
            existing_messages.extend(tail_messages)

        # 5. Enforce rolling budget & safety limit on message count (ITEM-11, CP-103.2, CP-106)
        cls.enforce_rolling_budget(
            existing_messages,
            target_limit=compact_limit,
            config=config,
            tools=tools,
            virtual_ram=mounted_virtual_ram,
            max_messages=config.max_history_messages,
        )

        return existing_messages

    prepare_context_for_model = prepare_messages

    @classmethod
    def maybe_squash(
        cls,
        messages: List[Dict[str, Any]],
        model_name: str = "qwen2.5-coder:14b",
        config: Optional[ContextConfig] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        mounted_virtual_ram: Optional[Dict[str, str]] = None,
        return_details: bool = False,
    ) -> Union[bool, Tuple[bool, bool, bool, bool]]:
        """
        In-loop squashing executed inside CodingHarness before every Ollama call.
        Middle-truncates older tool results when total tokens exceed squash_threshold (70%)
        or when more than preserve_last_n_tools results have accumulated.
        If tokens still exceed compact_threshold (82%) after squashing, applies rolling FIFO eviction.

        When return_details is True, returns (was_applied, squashed, evicted, rolled_up).
        When return_details is False (default), returns was_applied (bool).
        """
        if not messages:
            return (False, False, False, False) if return_details else False

        if mounted_virtual_ram is not None:
            cls.sync_virtual_ram_block(messages, mounted_virtual_ram)

        if config is None:
            config = ContextConfig.for_model(model_name)

        total_tokens = TokenEstimator.estimate_total(messages, tools=tools, virtual_ram=mounted_virtual_ram)
        threshold_tokens = int(config.context_window * config.squash_threshold)

        # Trigger squashing if above threshold OR if many tool results have accumulated
        tool_count = sum(1 for m in messages if m.get("role") == "tool")
        should_squash = total_tokens >= threshold_tokens or tool_count > config.preserve_last_n_tools

        # 1. Milestone Roll-up pass: collapse intermediate resolved failure loops
        messages, rolled_up = ContextSquasher.rollup_milestones(messages)
        was_applied = rolled_up
        squashed = False

        if should_squash:
            _, squashed = ContextSquasher.apply_squash(messages, config)
            was_applied = was_applied or squashed

        # In-loop critical overflow protection: If tokens still exceed compact threshold (82%)
        # or message count exceeds max_history_messages, trigger rolling eviction so active
        # session never overflows Ollama num_ctx or bounds
        compact_limit = int(config.context_window * config.compact_threshold)
        post_tokens = TokenEstimator.estimate_total(messages, tools=tools, virtual_ram=mounted_virtual_ram)
        should_enforce_budget = (post_tokens >= compact_limit) or (
            bool(config.max_history_messages and len(messages) > config.max_history_messages)
        )
        evicted = False
        if should_enforce_budget:
            evicted = cls.enforce_rolling_budget(
                messages,
                target_limit=compact_limit,
                config=config,
                tools=tools,
                virtual_ram=mounted_virtual_ram,
                max_messages=config.max_history_messages,
            )
            was_applied = was_applied or evicted

        if return_details:
            return (was_applied, squashed, evicted, rolled_up)
        return was_applied

    @classmethod
    def rollup_milestones(cls, messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Exposes ContextSquasher.rollup_milestones through master ContextManager.
        Scans messages for intra-turn execution loops where a tool call failed
        and was subsequently resolved by a successful tool execution.
        """
        return ContextSquasher.rollup_milestones(messages)

    @classmethod
    def get_context_telemetry(
        cls,
        messages: List[Dict[str, Any]],
        model_name: str = "qwen2.5-coder:14b",
        tools: Optional[List[Dict[str, Any]]] = None,
        mounted_virtual_ram: Optional[Dict[str, str]] = None,
        config: Optional[ContextConfig] = None,
        squashed: bool = False,
        evicted: bool = False,
        rolled_up: bool = False,
    ) -> Dict[str, Any]:
        """
        Calculates comprehensive real-time context telemetry for WebSocket emission and UI visualization.
        Spec [CP-106]: Tracks total tokens, dynamic RAM allocation, window capacity %, and compaction flags.
        """
        if config is None:
            config = ContextConfig.for_model(model_name)

        context_window = config.context_window

        # Layer breakdowns
        static_msg = next((m for m in messages if isinstance(m, dict) and m.get("role") == "system"), None)

        # Check if Virtual RAM register block is currently embedded inside the system message
        ram_in_static = False
        ram_block_content = ""
        if static_msg and isinstance(static_msg.get("content"), str):
            sys_content = static_msg["content"]
            if cls.RAM_HEADER in sys_content:
                ram_in_static = True
                start_idx = sys_content.find(cls.RAM_HEADER)
                end_idx = sys_content.find(cls.RAM_FOOTER, start_idx)
                if end_idx != -1:
                    end_idx += len(cls.RAM_FOOTER)
                    pure_static_content = (sys_content[:start_idx] + sys_content[end_idx:]).strip()
                    ram_block_content = sys_content[start_idx:end_idx]
                else:
                    pure_static_content = sys_content[:start_idx].strip()
                    ram_block_content = sys_content[start_idx:]
                static_tokens = TokenEstimator.estimate_text(pure_static_content) + TokenEstimator.MESSAGE_OVERHEAD_TOKENS
            else:
                static_tokens = TokenEstimator.estimate_message(static_msg)
        else:
            static_tokens = 0

        # Virtual RAM accounting
        virtual_ram_files_list: List[str] = []
        if mounted_virtual_ram:
            ram_tokens = TokenEstimator.estimate_virtual_ram(mounted_virtual_ram)
            ram_files = len(mounted_virtual_ram)
            virtual_ram_files_list = sorted(list(mounted_virtual_ram.keys()))
        elif ram_in_static and ram_block_content:
            ram_tokens = TokenEstimator.estimate_text(ram_block_content)
            ram_files = ram_block_content.count("--- FILE: ")
            for line in ram_block_content.splitlines():
                if line.startswith("--- FILE: "):
                    parts = line.split("--- FILE: ")[1].split(" (")
                    if parts:
                        virtual_ram_files_list.append(parts[0].strip())
            virtual_ram_files_list.sort()
        else:
            ram_tokens = 0
            ram_files = 0
        schema_tokens = TokenEstimator.estimate_schemas(tools) if tools else 0
        ephemeral_tokens = sum(TokenEstimator.estimate_message(m) for m in messages if m is not static_msg)

        total_tokens = TokenEstimator.estimate_total(messages, tools=tools, virtual_ram=mounted_virtual_ram)
        usage_pct = round((total_tokens / context_window) * 100, 1) if context_window else 0.0
        ram_pct = round((ram_tokens / context_window) * 100, 1) if context_window else 0.0
        static_pct = round((static_tokens / context_window) * 100, 1) if context_window else 0.0
        ephemeral_pct = round((ephemeral_tokens / context_window) * 100, 1) if context_window else 0.0

        # Check compaction markers from historical message contents
        has_eviction_marker = any(
            isinstance(m, dict) and ALERT_EVICTION_MARKER in str(m.get("content", ""))
            for m in messages
        )
        has_rollup_marker = any(
            isinstance(m, dict) and "[Milestone Roll-up:" in str(m.get("content", ""))
            for m in messages
        )
        has_squash_marker = any(
            isinstance(m, dict) and (
                "[... LOG TRUNCATED BY ENGINE" in str(m.get("content", ""))
                or "[... truncated ...]" in str(m.get("content", ""))
            )
            for m in messages
        )

        effective_evicted = bool(evicted or has_eviction_marker)
        effective_squashed = bool(squashed or has_squash_marker)
        effective_rolled_up = bool(rolled_up or has_rollup_marker)

        squash_threshold_pct = config.squash_threshold * 100
        compact_threshold_pct = config.compact_threshold * 100

        if usage_pct >= compact_threshold_pct or effective_evicted:
            status = "critical"
        elif usage_pct >= squash_threshold_pct or effective_squashed:
            status = "warning"
        else:
            status = "normal"

        return {
            "total_tokens": total_tokens,
            "context_window": context_window,
            "usage_pct": usage_pct,
            "static_tokens": static_tokens,
            "static_pct": static_pct,
            "virtual_ram_tokens": ram_tokens,
            "virtual_ram_files": ram_files,
            "virtual_ram_files_list": virtual_ram_files_list,
            "virtual_ram_pct": ram_pct,
            "ephemeral_tokens": ephemeral_tokens,
            "ephemeral_pct": ephemeral_pct,
            "schema_tokens": schema_tokens,
            "message_count": len(messages),
            "squashed": effective_squashed,
            "evicted": effective_evicted,
            "rolled_up": effective_rolled_up,
            "squash_threshold_pct": round(squash_threshold_pct, 1),
            "compact_threshold_pct": round(compact_threshold_pct, 1),
            "status": status,
            "model": model_name,
        }
