"""
Test Suite for Lowkey Production Context Management Engine.
Verifies TokenEstimator, ContextSquasher, ContextCompactor, and ContextManager using standard unittest.
"""

import json
import unittest
from pathlib import Path

from utils.context_manager import (
    ContextConfig,
    ALERT_EVICTION_MARKER,
    TokenEstimator,
    ContextSquasher,
    ContextCompactor,
    ContextManager,
)
from config.models import get_model_context_window


class TestModelContextWindow(unittest.TestCase):
    def test_context_window_lookup(self):
        self.assertEqual(get_model_context_window("qwen2.5-coder:7b"), 32768)
        self.assertEqual(get_model_context_window("qwen2.5-coder:14b"), 32768)
        self.assertEqual(get_model_context_window("deepseek-coder-v2:16b"), 131072)
        self.assertEqual(get_model_context_window("qwen3-coder:30b-a3b"), 262144)
        self.assertEqual(get_model_context_window("muse-glimmer:30b"), 131072)
        self.assertEqual(get_model_context_window("unknown-model"), 32768)


class TestTokenEstimator(unittest.TestCase):
    def test_estimate_text(self):
        self.assertEqual(TokenEstimator.estimate_text(""), 0)
        self.assertEqual(TokenEstimator.estimate_text(None), 0)
        sample = "a" * 37
        self.assertEqual(TokenEstimator.estimate_text(sample), 10)

    def test_estimate_message(self):
        msg = {"role": "user", "content": "Hello world!"}
        tokens = TokenEstimator.estimate_message(msg)
        self.assertGreater(tokens, 4)

    def test_estimate_total(self):
        messages = [
            {"role": "user", "content": "Build me a Notes app"},
            {"role": "assistant", "content": "Understood."},
        ]
        total = TokenEstimator.estimate_total(messages, system_prompt="You are Lowkey.")
        self.assertGreater(total, 15)

    def test_estimate_schema(self):
        sample_schema = {
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "A test tool for estimation.",
                "parameters": {
                    "type": "object",
                    "properties": {"arg1": {"type": "string"}},
                    "required": ["arg1"],
                },
            },
        }
        tokens = TokenEstimator.estimate_schema(sample_schema)
        self.assertGreater(tokens, 20)
        self.assertEqual(TokenEstimator.estimate_schema({}), 0)
        self.assertEqual(TokenEstimator.estimate_schema(None), 0)

    def test_estimate_schemas_empty_and_real(self):
        from tools.schemas import TOOL_SCHEMAS

        self.assertEqual(TokenEstimator.estimate_schemas([]), 0)
        self.assertEqual(TokenEstimator.estimate_schemas(None), 0)

        # Real TOOL_SCHEMAS in Lowkey (24 tools) should estimate between 2,500 and 5,500 tokens
        total_schema_tokens = TokenEstimator.estimate_schemas(TOOL_SCHEMAS)
        self.assertGreater(total_schema_tokens, 2500)
        self.assertLess(total_schema_tokens, 6500)

    def test_estimate_total_includes_tool_schemas(self):
        from tools.schemas import TOOL_SCHEMAS

        messages = [{"role": "user", "content": "Hello"}]
        without_tools = TokenEstimator.estimate_total(messages, system_prompt="System")
        with_tools = TokenEstimator.estimate_total(messages, system_prompt="System", tools=TOOL_SCHEMAS)

        schema_tokens = TokenEstimator.estimate_schemas(TOOL_SCHEMAS)
        self.assertEqual(with_tools, without_tools + schema_tokens)

    def test_estimate_schemas_supports_dict_and_iterables(self):
        from tools.schemas import TOOL_SCHEMAS

        # 1. As a dictionary: {tool_name: schema}
        schema_dict = {
            s.get("function", {}).get("name", f"tool_{i}"): s
            for i, s in enumerate(TOOL_SCHEMAS)
        }
        tokens_from_dict = TokenEstimator.estimate_schemas(schema_dict)
        tokens_from_list = TokenEstimator.estimate_schemas(TOOL_SCHEMAS)
        self.assertEqual(tokens_from_dict, tokens_from_list)

        # 2. As a tuple / iterable
        tokens_from_tuple = TokenEstimator.estimate_schemas(tuple(TOOL_SCHEMAS))
        self.assertEqual(tokens_from_tuple, tokens_from_list)

        # 3. As a generator expression
        tokens_from_gen = TokenEstimator.estimate_schemas((s for s in TOOL_SCHEMAS))
        self.assertEqual(tokens_from_gen, tokens_from_list)

        # 4. Invalid/unsupported types return 0 without raising
        self.assertEqual(TokenEstimator.estimate_schemas(12345), 0)
        self.assertEqual(TokenEstimator.estimate_schemas("not_a_schema"), 0)
        self.assertEqual(TokenEstimator.estimate_schemas(b"bytes_schema"), 0)

    def test_estimate_message_invalid_inputs(self):
        self.assertEqual(TokenEstimator.estimate_message(None), 0)
        self.assertEqual(TokenEstimator.estimate_message("not_a_dict"), 0)
        self.assertEqual(TokenEstimator.estimate_message(123), 0)

    def test_estimate_total_with_schemas_keyword(self):
        from tools.schemas import TOOL_SCHEMAS

        messages = [{"role": "user", "content": "Hello"}]
        with_tools_kwarg = TokenEstimator.estimate_total(messages, tools=TOOL_SCHEMAS)
        with_schemas_kwarg = TokenEstimator.estimate_total(messages, schemas=TOOL_SCHEMAS)
        self.assertEqual(with_tools_kwarg, with_schemas_kwarg)

    def test_estimate_total_prevents_system_prompt_double_counting(self):
        sys_text = "You are Chico, autonomous full-stack agent."
        messages_with_sys = [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": "Build an app."},
        ]

        # Calling estimate_total with redundant system_prompt should not double count
        total_implicit = TokenEstimator.estimate_total(messages_with_sys)
        total_explicit = TokenEstimator.estimate_total(messages_with_sys, system_prompt=sys_text)
        self.assertEqual(total_implicit, total_explicit)

    def test_estimate_text_robustness(self):
        self.assertEqual(TokenEstimator.estimate_text(None), 0)
        self.assertEqual(TokenEstimator.estimate_text(""), 0)
        self.assertGreater(TokenEstimator.estimate_text(12345), 0)
        self.assertGreater(TokenEstimator.estimate_text(99.99), 0)
        self.assertGreater(TokenEstimator.estimate_text(b"raw bytes payload"), 0)
        self.assertGreater(TokenEstimator.estimate_text(bytearray(b"bytearray payload")), 0)

    def test_estimate_schemas_single_schema_dict(self):
        from tools.schemas import TOOL_SCHEMAS

        # Standard schema with function dict
        single_schema = TOOL_SCHEMAS[0]
        self.assertEqual(
            TokenEstimator.estimate_schemas(single_schema),
            TokenEstimator.estimate_schema(single_schema),
        )

        # Flat schema format
        flat_schema = {
            "name": "custom_search",
            "description": "Searches internal database.",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        }
        self.assertEqual(
            TokenEstimator.estimate_schemas(flat_schema),
            TokenEstimator.estimate_schema(flat_schema),
        )

    def test_estimate_total_none_safety(self):
        # Messages as None
        self.assertEqual(TokenEstimator.estimate_total(None), 3)
        # system_prompt as None with virtual_ram
        total = TokenEstimator.estimate_total([], system_prompt=None, virtual_ram={"app.py": "print('hi')"})
        self.assertGreater(total, 3)

    def test_estimate_message_with_metadata_and_thinking(self):
        # Tool response with name
        tool_msg = {"role": "tool", "name": "read_file", "content": "file output"}
        tokens_with_name = TokenEstimator.estimate_message(tool_msg)
        tool_msg_no_name = {"role": "tool", "content": "file output"}
        tokens_without_name = TokenEstimator.estimate_message(tool_msg_no_name)
        self.assertGreater(tokens_with_name, tokens_without_name)

        # Assistant message with thinking
        assistant_msg = {
            "role": "assistant",
            "content": "Result",
            "thinking": "Analyzing user request...",
        }
        tokens_with_think = TokenEstimator.estimate_message(assistant_msg)
        assistant_msg_no_think = {"role": "assistant", "content": "Result"}
        tokens_without_think = TokenEstimator.estimate_message(assistant_msg_no_think)
        self.assertGreater(tokens_with_think, tokens_without_think)

        # Tool calls with id and arguments
        msg_with_call = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_12345",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": {"file_path": "test.txt"}},
                }
            ],
        }
        self.assertGreater(TokenEstimator.estimate_message(msg_with_call), 15)
    def test_tool_schemas_trigger_early_compaction(self):
        """Proves that including tool schemas triggers compaction threshold earlier to protect context window."""
        from tools.schemas import TOOL_SCHEMAS

        # 10,000 tokens window, 82% compaction limit = 8,200 tokens
        config = ContextConfig(context_window=10000, compact_threshold=0.82)

        # Create history where messages alone take ~4,800 tokens (< 8,200 compact_limit)
        existing = []
        for i in range(1, 8):
            existing.append({"role": "user", "content": f"Implement feature {i}"})
            existing.append({
                "role": "assistant",
                "content": f"Working on feature {i}. " + ("code analysis and step execution details " * 60),
            })

        # 1. Without tool schemas: total tokens (~4,800) are under 8,200 compact_limit, so NO compaction occurs
        res_without_tools = ContextManager.prepare_messages(
            user_prompt="Continue next",
            system_prompt="System",
            existing_messages=list(existing),
            config=config,
            tools=None,
        )
        self.assertFalse(any("<analysis>" in m.get("content", "") for m in res_without_tools))

        # 2. With tool schemas: schemas (~4,700 tokens) push total to ~9,500 tokens (> 8,200 compact_limit),
        # which properly triggers macro-compaction to protect context window
        res_with_tools = ContextManager.prepare_messages(
            user_prompt="Continue next",
            system_prompt="System",
            existing_messages=list(existing),
            config=config,
            tools=TOOL_SCHEMAS,
        )
        self.assertTrue(any("<analysis>" in m.get("content", "") for m in res_with_tools))


class TestContextSquasher(unittest.TestCase):
    def test_middle_truncate_short_text(self):
        short = "This is a short string"
        self.assertEqual(ContextSquasher.middle_truncate(short, max_chars=500), short)

    def test_middle_truncate_long_text(self):
        long_text = "HEADER_START" + ("x" * 2000) + "FOOTER_END"
        truncated = ContextSquasher.middle_truncate(long_text, max_chars=200)

        self.assertLess(len(truncated), len(long_text))
        self.assertTrue(truncated.startswith("HEADER_START"))
        self.assertTrue(truncated.endswith("FOOTER_END"))
        self.assertIn("[truncated", truncated)

    def test_sanitize_assistant_history(self):
        dirty = (
            "<think>Thinking deeply about the universe...</think>\n"
            "I will write the file.\n"
            "```javascript\nconsole.log('hello');\n```"
        )
        cleaned = ContextSquasher.sanitize_assistant_history(dirty)
        self.assertNotIn("<think>", cleaned)
        self.assertNotIn("Thinking deeply", cleaned)
        self.assertNotIn("```", cleaned)
        self.assertIn("I will write the file.", cleaned)

    def test_apply_squash_preserves_last_n_tools(self):
        config = ContextConfig(preserve_last_n_tools=2, truncation_length=100)

        # 4 tool results
        messages = [
            {"role": "user", "content": "Start"},
            {"role": "assistant", "content": "Calling tool 1", "tool_calls": []},
            {"role": "tool", "content": "Tool 1: " + ("A" * 500)},
            {"role": "assistant", "content": "Calling tool 2", "tool_calls": []},
            {"role": "tool", "content": "Tool 2: " + ("B" * 500)},
            {"role": "assistant", "content": "Calling tool 3", "tool_calls": []},
            {"role": "tool", "content": "Tool 3: " + ("C" * 500)},
            {"role": "assistant", "content": "Calling tool 4", "tool_calls": []},
            {"role": "tool", "content": "Tool 4: " + ("D" * 500)},
        ]

        squashed, was_applied = ContextSquasher.apply_squash(messages, config)
        self.assertTrue(was_applied)

        # Tool 1 and 2 (older than last 2) must be truncated
        self.assertIn("[truncated", squashed[2]["content"])
        self.assertLessEqual(len(squashed[2]["content"]), 200)
        self.assertIn("[truncated", squashed[4]["content"])
        self.assertLessEqual(len(squashed[4]["content"]), 200)

        # Tool 3 and 4 (the last 2) MUST remain 100% full
        self.assertNotIn("[truncated", squashed[6]["content"])
        self.assertGreater(len(squashed[6]["content"]), 500)
        self.assertNotIn("[truncated", squashed[8]["content"])
        self.assertGreater(len(squashed[8]["content"]), 500)


class TestContextCompactor(unittest.TestCase):
    def test_generate_synthetic_head(self):
        messages = [
            {"role": "user", "content": "Build me a fullstack Notes app with tags"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "invoke_design_agent", "arguments": {}}},
                    {"function": {"name": "write_file", "arguments": {"file_path": "server/index.js"}}},
                    {"function": {"name": "write_file", "arguments": {"file_path": "src/App.jsx"}}},
                ],
            },
            {"role": "tool", "content": "Files written successfully."},
        ]

        head = ContextCompactor.generate_synthetic_head(messages)

        self.assertIn("<analysis>", head)
        self.assertIn("</analysis>", head)
        self.assertIn("Original User Request: Build me a fullstack Notes app with tags", head)
        self.assertIn("server/index.js", head)
        self.assertIn("src/App.jsx", head)
        self.assertIn("Continuation Posture", head)
        self.assertIn("Do NOT execute unprompted background tasks", head)


class TestContextManager(unittest.TestCase):
    def test_prepare_messages_confirmation_handling(self):
        # User confirmed with "yes" after ask_human
        existing = [
            {"role": "user", "content": "Build me a notes app"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "ask_human",
                            "arguments": {
                                "question": "Do you want dark mode?",
                                "options": ["Yes", "No"],
                            },
                        }
                    }
                ],
            },
            {"role": "tool", "content": "Question displayed to user."},
        ]

        res = ContextManager.prepare_messages("yes", "System Prompt", existing)

        # Assistant turn must preserve the question
        assistant_turn = res[2]
        self.assertEqual(assistant_turn["role"], "assistant")
        self.assertIn("Question asked: Do you want dark mode? (Options: Yes, No)", assistant_turn["content"])

        # Latest user prompt must be the clean user prompt without any injected anchors
        latest_user = res[3]
        self.assertEqual(latest_user["role"], "user")
        self.assertEqual(latest_user["content"], "yes")

    def test_maybe_squash_in_loop(self):
        messages = [
            {"role": "user", "content": "Build app"},
            {"role": "assistant", "content": "Run tool 1"},
            {"role": "tool", "content": "Result 1: " + ("x" * 2000)},
            {"role": "assistant", "content": "Run tool 2"},
            {"role": "tool", "content": "Result 2: " + ("y" * 2000)},
            {"role": "assistant", "content": "Run tool 3"},
            {"role": "tool", "content": "Result 3: " + ("z" * 2000)},
            {"role": "assistant", "content": "Run tool 4"},
            {"role": "tool", "content": "Result 4: " + ("w" * 2000)},
            {"role": "assistant", "content": "Run tool 5"},
            {"role": "tool", "content": "Result 5: " + ("v" * 2000)},
        ]

        # 5 tool results with preserve_last_n_tools=3 should trigger squashing on tools 1 and 2
        applied = ContextManager.maybe_squash(messages, model_name="qwen2.5-coder:14b")
        self.assertTrue(applied)

        # Tool 1 and 2 should be squashed
        self.assertIn("[truncated", messages[2]["content"])
        self.assertIn("[truncated", messages[4]["content"])

        # Last 3 tool results (tools 3, 4, 5) must be preserved in full
        self.assertNotIn("[truncated", messages[6]["content"])
        self.assertNotIn("[truncated", messages[8]["content"])
        self.assertNotIn("[truncated", messages[10]["content"])

    def test_compact_prior_turns_ignores_fallback_tool_results(self):
        # Conversation containing fallback tool outputs with role="user"
        existing = [
            {"role": "user", "content": "build me a notes app"},
            {"role": "assistant", "content": '{"name": "write_file", "arguments": {"file_path": "src/App.jsx"}}'},
            {"role": "user", "content": "[Tool Result for 'write_file']:\nFile written successfully.\n\nPlease proceed."},
            {"role": "assistant", "content": '{"name": "finish", "arguments": {"summary": "Completed"}}'},
            {"role": "user", "content": "[Tool Result for 'finish']:\n🎉 [Task Completed Successfully]\n\nPlease proceed."},
        ]

        compacted = ContextManager.compact_prior_turns(existing)
        # Compacted history should have exactly 1 turn pair: User ("build me a notes app") + Assistant summary
        self.assertEqual(len(compacted), 2)
        self.assertEqual(compacted[0]["role"], "user")
        self.assertEqual(compacted[0]["content"], "build me a notes app")
        self.assertEqual(compacted[1]["role"], "assistant")
        self.assertNotIn("[Tool Result", compacted[0]["content"])

    def test_maybe_squash_with_tool_schemas(self):
        from tools.schemas import TOOL_SCHEMAS

        config = ContextConfig(context_window=10000, squash_threshold=0.50, preserve_last_n_tools=3)
        # 50% threshold is 5,000 tokens
        # Create messages with ~2,000 tokens of text and a historical think block
        messages = [
            {"role": "user", "content": "x" * 7400},
            {"role": "assistant", "content": "<think>Pondering</think>Step 1"},
            {"role": "tool", "content": "Result 1"},
            {"role": "assistant", "content": "Step 2"},
        ]
        # Without tools: total tokens is ~2,000 (< 5,000 threshold) -> does NOT squash
        applied_without = ContextManager.maybe_squash(messages, config=config, tools=None)
        self.assertFalse(applied_without)

        # With TOOL_SCHEMAS (~3,600 tokens): total tokens is ~5,600 (> 5,000 threshold) -> triggers squashing
        applied_with = ContextManager.maybe_squash(messages, config=config, tools=TOOL_SCHEMAS)
        self.assertTrue(applied_with)
        # Verify the think block was pruned from the historical assistant turn
        self.assertNotIn("<think>", messages[1]["content"])


class TestToolOutputCompression(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_compress_tool_output_below_threshold(self):
        """Outputs <= 1,800 characters must remain untouched."""
        short_text = "Build successful. Generated 4 chunks in 120ms."
        res = ContextSquasher.compress_tool_output(short_text, tool_name="execute_command")
        self.assertEqual(res, short_text)

    def test_compress_tool_output_head_and_tail_retention(self):
        """Outputs > 1,800 characters retain top 35 and bottom 35 lines with omission banner."""
        lines = [f"Step {i}: Processing component {i} in build pipeline" for i in range(1, 151)]
        raw_text = "\n".join(lines)
        self.assertGreater(len(raw_text), 1800)

        compressed = ContextSquasher.compress_tool_output(
            raw_text,
            tool_name="execute_command",
            head_lines=35,
            tail_lines=35,
        )

        self.assertIn("Step 1: Processing component 1", compressed)
        self.assertIn("Step 35: Processing component 35", compressed)
        self.assertIn("Step 116: Processing component 116", compressed)
        self.assertIn("Step 150: Processing component 150", compressed)
        self.assertIn("Omitted 80 lines", compressed)
        # Verify middle line was omitted from direct listing
        self.assertNotIn("Step 50: Processing component 50", compressed)

    def test_compress_tool_output_middle_error_preservation(self):
        """Errors occurring in the omitted middle lines must be preserved in context."""
        lines = [f"Trace log item {i}: normal execution" for i in range(1, 151)]
        lines[59] = "Error: Connection refused by upstream API on port 5001"
        lines[75] = "FATAL: Unhandled exception in authentication handler"
        raw_text = "\n".join(lines)

        compressed = ContextSquasher.compress_tool_output(
            raw_text,
            tool_name="execute_command",
            head_lines=35,
            tail_lines=35,
        )

        self.assertIn("[Preserved middle diagnostics & failure lines]:", compressed)
        self.assertIn("Error: Connection refused by upstream API on port 5001", compressed)
        self.assertIn("FATAL: Unhandled exception in authentication handler", compressed)


    def test_compress_tool_output_truncates_excessively_long_error_lines(self):
        """Preserved middle error lines exceeding 400 characters are capped to prevent token blowout."""
        lines = [f"Step {i}: normal execution" for i in range(1, 151)]
        massive_error = "Error: " + ("X" * 1000)
        lines[60] = massive_error
        raw_text = "\n".join(lines)

        compressed = ContextSquasher.compress_tool_output(
            raw_text,
            tool_name="execute_command",
            head_lines=35,
            tail_lines=35,
        )

        self.assertIn("[Preserved middle diagnostics & failure lines]:", compressed)
        self.assertIn("... [truncated line]", compressed)
        self.assertNotIn("X" * 1000, compressed)
    def test_compress_tool_output_saves_spillover_artifact(self):
        """Full unabridged tool outputs are saved to .lowkey/tool_artifacts/ on disk."""
        lines = [f"Log line {i}: detail info" for i in range(1, 120)]
        raw_text = "\n".join(lines)

        compressed = ContextSquasher.compress_tool_output(
            raw_text,
            tool_name="test_runner",
            project_root=self.project_root,
        )

        # Verify notice references the artifact file
        self.assertIn(".lowkey/tool_artifacts/test_runner_", compressed)
        self.assertIn("Full uncompressed output saved to", compressed)

        # Verify the file exists on disk with full content
        artifacts_dir = self.project_root / ".lowkey" / "tool_artifacts"
        self.assertTrue(artifacts_dir.exists())
        saved_files = list(artifacts_dir.glob("test_runner_*.log"))
        self.assertEqual(len(saved_files), 1)
        saved_content = saved_files[0].read_text(encoding="utf-8")
        self.assertEqual(saved_content, raw_text)

    def test_middle_truncate_line_integrity(self):
        """middle_truncate must split on newlines and avoid mid-line cuts."""
        lines = [f"Line {i:03d} of structured configuration data" for i in range(1, 31)]
        raw_text = "\n".join(lines)

        truncated = ContextSquasher.middle_truncate(raw_text, max_chars=300)
        self.assertIn("... [Omitted", truncated)
        # Verify lines are intact, without partial prefixes or suffixes
        for line in truncated.splitlines():
            if not line.startswith("..."):
                self.assertTrue(line.startswith("Line ") or line == "")

    def test_record_tool_result_native(self):
        """ContextManager.record_tool_result creates a native tool message with name and compressed content."""
        messages = []
        msg = ContextManager.record_tool_result(
            messages=messages,
            tool_name="read_file",
            result="Line 1: def test(): pass",
            project_root=self.project_root,
            is_native_tool_call=True,
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(msg["role"], "tool")
        self.assertEqual(msg["name"], "read_file")
        self.assertEqual(msg["content"], "Line 1: def test(): pass")

    def test_record_tool_result_fallback(self):
        """ContextManager.record_tool_result creates a user-role fallback message for non-native reasoning models."""
        messages = []
        msg = ContextManager.record_tool_result(
            messages=messages,
            tool_name="read_file",
            result="Line 1: def test(): pass",
            project_root=self.project_root,
            is_native_tool_call=False,
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(msg["role"], "user")
        self.assertIn("[Tool Result for 'read_file']:\nLine 1: def test(): pass", msg["content"])

    def test_record_tool_result_ingestion_compression_and_spillover(self):
        """ContextManager.record_tool_result immediately compresses > 1,800 chars and creates spillover logs."""
        messages = []
        huge_output = "\n".join([f"Log row {i}: status normal and running smoothly" for i in range(1, 150)])
        self.assertGreater(len(huge_output), 1800)

        msg = ContextManager.record_tool_result(
            messages=messages,
            tool_name="build_app",
            result=huge_output,
            project_root=self.project_root,
            is_native_tool_call=True,
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(msg["role"], "tool")
        self.assertEqual(msg["name"], "build_app")
        # Check compression banner and spillover reference
        self.assertIn("Full uncompressed output saved to .lowkey/tool_artifacts/build_app_", msg["content"])
        self.assertIn("Log row 1:", msg["content"])
        self.assertIn("Log row 149:", msg["content"])

        # Check artifact on disk
        artifacts = list((self.project_root / ".lowkey" / "tool_artifacts").glob("build_app_*.log"))
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].read_text(encoding="utf-8"), huge_output)

    def test_record_tool_result_non_string_result(self):
        """ContextManager.record_tool_result safely stringifies dicts, ints, and None."""
        messages = []
        msg1 = ContextManager.record_tool_result(messages, "json_tool", {"status": "ok", "code": 200})
        self.assertIn('"status": "ok"', msg1["content"])

        msg2 = ContextManager.record_tool_result(messages, "count_tool", 42)
        self.assertEqual(msg2["content"], "42")

        msg3 = ContextManager.record_tool_result(messages, "void_tool", None)
        self.assertEqual(msg3["content"], "")

    def test_record_tool_result_preserves_middle_assertionerror(self):
        """Preserves AssertionError and Panic diagnostics in middle lines."""
        lines = [f"Output {i}: running unit test case" for i in range(1, 120)]
        lines[50] = "AssertionError: Expected 200 OK but received 500 Internal Server Error"
        lines[60] = "fatal: repository corruption detected"
        raw_text = "\n".join(lines)

        messages = []
        msg = ContextManager.record_tool_result(
            messages=messages,
            tool_name="pytest",
            result=raw_text,
            project_root=self.project_root,
        )
        self.assertIn("[Preserved middle diagnostics & failure lines]:", msg["content"])
        self.assertIn("AssertionError: Expected 200 OK", msg["content"])
        self.assertIn("fatal: repository corruption detected", msg["content"])



class TestRollingFifoEviction(unittest.TestCase):
    """
    Test suite for ITEM-11: Rolling FIFO Eviction & Alert Injection (CP-103.2, CP-106).
    """

    def test_enforce_rolling_budget_evicts_oldest_when_over_token_limit(self):
        """When total tokens exceed target_limit, oldest dynamic messages are popped in FIFO order."""
        messages = [
            {"role": "system", "content": "You are Lowkey AI. Pinned Static Layer instruction."},
            {"role": "user", "content": "Turn 1: " + ("alpha " * 200)},
            {"role": "assistant", "content": "Turn 1 response: " + ("beta " * 200)},
            {"role": "user", "content": "Turn 2: " + ("gamma " * 200)},
            {"role": "assistant", "content": "Turn 2 response: " + ("delta " * 200)},
            {"role": "user", "content": "Turn 3: recent user task"},
        ]

        # Calculate initial tokens
        initial_tokens = TokenEstimator.estimate_total(messages)
        self.assertGreater(initial_tokens, 800)

        # Set target limit lower than total tokens so Turn 1 is evicted
        target_limit = 500
        evicted = ContextManager.enforce_rolling_budget(messages, target_limit=target_limit)
        self.assertTrue(evicted)

        # Static Layer must remain intact at index 0
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "You are Lowkey AI. Pinned Static Layer instruction.")

        # Turn 1 should be gone
        all_contents = " ".join(m.get("content", "") for m in messages)
        self.assertNotIn("Turn 1:", all_contents)

        # Alert marker should be injected
        self.assertIn(ALERT_EVICTION_MARKER, messages[1]["content"])

        # Remaining tokens must be within target_limit
        final_tokens = TokenEstimator.estimate_total(messages)
        self.assertLessEqual(final_tokens, target_limit)

    def test_enforce_rolling_budget_preserves_static_layer(self):
        """Even with an aggressive budget limit, messages[0] is never evicted."""
        messages = [
            {"role": "system", "content": "Static Layer System Prompt"},
            {"role": "user", "content": "User message 1: " + ("xyz " * 500)},
            {"role": "assistant", "content": "Assistant message 1: " + ("xyz " * 500)},
            {"role": "user", "content": "Active prompt"},
        ]

        # Target limit below system prompt + all messages
        ContextManager.enforce_rolling_budget(messages, target_limit=50)

        # messages[0] must still be the system prompt
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "Static Layer System Prompt")
        # At least active turn is kept (len >= 2)
        self.assertGreaterEqual(len(messages), 2)

    def test_enforce_rolling_budget_no_duplicate_alerts(self):
        """Multiple successive evictions do not duplicate ALERT_EVICTION_MARKER."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Msg 1: " + ("foo " * 300)},
            {"role": "assistant", "content": "Msg 2: " + ("bar " * 300)},
            {"role": "user", "content": "Msg 3: " + ("baz " * 300)},
            {"role": "assistant", "content": "Msg 4: " + ("qux " * 300)},
            {"role": "user", "content": "Msg 5: " + ("quux " * 300)},
        ]

        # Pass 1 eviction
        ContextManager.enforce_rolling_budget(messages, target_limit=800)
        marker_count_pass1 = sum(m.get("content", "").count(ALERT_EVICTION_MARKER) for m in messages)
        self.assertEqual(marker_count_pass1, 1)

        # Pass 2 eviction with tighter limit
        ContextManager.enforce_rolling_budget(messages, target_limit=400)
        marker_count_pass2 = sum(m.get("content", "").count(ALERT_EVICTION_MARKER) for m in messages)
        self.assertEqual(marker_count_pass2, 1)

    def test_enforce_rolling_budget_role_integrity_when_odd_eviction(self):
        """If eviction leaves an assistant message at head, a user alert turn is inserted to preserve alternation."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User large turn: " + ("a " * 500)},
            {"role": "assistant", "content": "Assistant small response"},
            {"role": "user", "content": "User next turn"},
        ]

        # Target limit designed so only messages[1] (User large turn) is popped
        tokens_without_large_user = TokenEstimator.estimate_total([
            messages[0], messages[2], messages[3]
        ])
        ContextManager.enforce_rolling_budget(messages, target_limit=tokens_without_large_user + 50)

        # Since messages[1] was popped, messages[1] would have been assistant.
        # Check that role alternation is preserved: system -> user -> assistant -> user
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn(ALERT_EVICTION_MARKER, messages[1]["content"])
        self.assertEqual(messages[2]["role"], "assistant")
        self.assertEqual(messages[2]["content"], "Assistant small response")

    def test_enforce_rolling_budget_message_count_limit(self):
        """When message count exceeds max_messages, early messages are evicted with alert marker."""
        messages = [{"role": "system", "content": "System"}]
        for i in range(1, 35):
            role = "user" if i % 2 == 1 else "assistant"
            messages.append({"role": role, "content": f"Message {i}"})

        self.assertEqual(len(messages), 35)

        # Evict with max_messages=25
        ContextManager.enforce_rolling_budget(messages, target_limit=100000, max_messages=25)

        self.assertEqual(len(messages), 25)
        self.assertEqual(messages[0]["role"], "system")
        # Early messages like Message 1, 2, etc. should be evicted
        all_content = " ".join(m.get("content", "") for m in messages)
        self.assertNotIn("Message 1\n", all_content)
        self.assertIn(ALERT_EVICTION_MARKER, all_content)

    def test_prepare_messages_rolling_budget_integration(self):
        """prepare_messages enforces rolling eviction and continuity alert for long conversations."""
        existing = []
        for i in range(1, 40):
            role = "user" if i % 2 == 1 else "assistant"
            existing.append({"role": role, "content": f"History step {i}"})

        config = ContextConfig(max_history_messages=20)
        res = ContextManager.prepare_messages(
            user_prompt="Continue current work",
            system_prompt="System Prompt",
            existing_messages=existing,
            config=config,
        )

        # After prepare_messages, message count should be within max_history_messages
        self.assertLessEqual(len(res), config.max_history_messages + 5)
        self.assertEqual(res[0]["role"], "system")
        all_content = " ".join(m.get("content", "") for m in res)
        self.assertIn(ALERT_EVICTION_MARKER, all_content)

    def test_maybe_squash_rolling_eviction_on_critical_overflow(self):
        """When in-loop tool squashing still leaves tokens >= compact_threshold, rolling eviction kicks in."""
        config = ContextConfig(context_window=1000, compact_threshold=0.82, squash_threshold=0.70)
        # 1000 * 0.82 = 820 tokens limit
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Heavy turn 1: " + ("data " * 300)},
            {"role": "assistant", "content": "Heavy turn 2: " + ("data " * 300)},
            {"role": "user", "content": "Heavy turn 3: " + ("data " * 300)},
            {"role": "tool", "content": "Tool result: success"},
        ]

        applied = ContextManager.maybe_squash(messages, config=config)
        self.assertTrue(applied)

        # Verify eviction reduced token load and preserved system prompt
        self.assertEqual(messages[0]["role"], "system")
        final_tokens = TokenEstimator.estimate_total(messages)
        self.assertLessEqual(final_tokens, int(config.context_window * config.compact_threshold))
        all_content = " ".join(m.get("content", "") for m in messages)
        self.assertIn(ALERT_EVICTION_MARKER, all_content)


    def test_enforce_rolling_budget_atomic_tool_call_eviction(self):
        """When an assistant message with tool_calls is evicted, its tool results are evicted atomically."""
        messages = [
            {"role": "system", "content": "You are a coding assistant."},
            {"role": "user", "content": "Run the test suite: " + ("word " * 50)},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {"name": "run_tests", "arguments": "{}"}}],
            },
            {"role": "tool", "content": "PASSED 10 tests\nFAILED 0 tests", "name": "run_tests"},
            {"role": "assistant", "content": "Tests passed!"},
            {"role": "user", "content": "Now deploy the app: " + ("word " * 50)},
            {"role": "assistant", "content": "Deployed successfully."},
        ]

        # Target limit designed to evict Turn 1 (user + assistant tool call)
        tokens_step2 = TokenEstimator.estimate_total(messages[0:1] + messages[3:])
        target = tokens_step2 + 5

        evicted = ContextManager.enforce_rolling_budget(messages, target_limit=target)
        self.assertTrue(evicted)

        # Static layer must remain intact
        self.assertEqual(messages[0]["role"], "system")
        # Ensure no tool message is orphaned (any tool message must follow an assistant with tool_calls)
        for i in range(len(messages)):
            if messages[i]["role"] == "tool":
                self.assertGreater(i, 0)
                self.assertEqual(messages[i-1]["role"], "assistant")
                self.assertTrue(bool(messages[i-1].get("tool_calls")))
        # Alert marker should be present
        all_content = " ".join(str(m.get("content") or "") for m in messages)
        self.assertIn(ALERT_EVICTION_MARKER, all_content)

    def test_enforce_rolling_budget_cleans_orphaned_tool_messages(self):
        """If an orphaned tool message sits at the head of dynamic context, it is cleaned."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "tool", "content": "Orphaned tool result", "name": "read_file"},
            {"role": "user", "content": "Current active task"},
            {"role": "assistant", "content": "Current active response"},
        ]

        ContextManager.enforce_rolling_budget(messages, target_limit=10000)
        self.assertEqual(messages[0]["role"], "system")
        self.assertNotEqual(messages[1]["role"], "tool")
        self.assertEqual(messages[1]["role"], "user")

    def test_enforce_rolling_budget_strict_max_messages_even_when_alert_inserted(self):
        """When max_messages is set to an even count where assistant is at head, len <= max_messages is strictly maintained."""
        messages = [{"role": "system", "content": "System"}]
        for i in range(1, 35):
            role = "user" if i % 2 == 1 else "assistant"
            messages.append({"role": role, "content": f"Message {i}"})

        ContextManager.enforce_rolling_budget(messages, target_limit=100000, max_messages=24)
        self.assertLessEqual(len(messages), 24)
        self.assertEqual(messages[0]["role"], "system")
        all_content = " ".join(str(m.get("content") or "") for m in messages)
        self.assertIn(ALERT_EVICTION_MARKER, all_content)

    def test_enforce_rolling_budget_without_system_prompt(self):
        """When history lacks a system message, oldest ephemeral message is popped and alert is injected at index 0."""
        messages = [
            {"role": "user", "content": "Turn 1 user: " + ("word " * 60)},
            {"role": "assistant", "content": "Turn 1 response: " + ("word " * 60)},
            {"role": "user", "content": "Turn 2 user: recent prompt"},
            {"role": "assistant", "content": "Turn 2 response"},
        ]

        evicted = ContextManager.enforce_rolling_budget(messages, target_limit=80)
        self.assertTrue(evicted)
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn(ALERT_EVICTION_MARKER, messages[0]["content"])
        self.assertNotIn("Turn 1 user:", messages[0]["content"])

    def test_enforce_rolling_budget_post_injection_token_invariant(self):
        """Even if inserting/prepending alert adds tokens, total tokens remains strictly <= target_limit."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Heavy turn 1: " + ("token " * 100)},
            {"role": "assistant", "content": "Heavy response: " + ("token " * 100)},
            {"role": "user", "content": "Turn 2: " + ("token " * 50)},
            {"role": "assistant", "content": "Turn 2 response"},
        ]

        target_limit = 120
        evicted = ContextManager.enforce_rolling_budget(messages, target_limit=target_limit)
        self.assertTrue(evicted)
        final_tokens = TokenEstimator.estimate_total(messages)
        self.assertLessEqual(final_tokens, target_limit)
        self.assertEqual(messages[0]["role"], "system")
        all_content = " ".join(str(m.get("content") or "") for m in messages)
        self.assertIn(ALERT_EVICTION_MARKER, all_content)

class TestStructuredToolRetention(unittest.TestCase):
    """
    Test suite for ITEM-12: Retain non-zero exit codes, stderr outputs, and lint errors in compacted turn summaries (CP-103.2).
    """

    def test_unresolved_error_in_turn_1_is_remembered_in_turn_2(self):
        """When Turn 1 ends with a failed command, the error snippet and non-zero exit code are retained in Turn 2."""
        turn_1_messages = [
            {"role": "user", "content": "Run the tests"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "execute_command",
                            "arguments": {"command": "npm test"},
                        }
                    }
                ],
            },
            {
                "role": "tool",
                "name": "execute_command",
                "content": "[Command failed with exit code 1]\nFAIL src/App.test.jsx\n● Notes App › renders notes list\n  Expected: 2\n  Received: 0",
            },
        ]

        res = ContextManager.prepare_messages(
            user_prompt="why did the test fail?",
            system_prompt="System Prompt",
            existing_messages=turn_1_messages,
        )

        # Turn 1 assistant message is at res[2] (res[0]=system, res[1]=user "Run the tests", res[2]=assistant, res[3]=user "why did the test fail?")
        assistant_turn = res[2]
        self.assertEqual(assistant_turn["role"], "assistant")
        self.assertIn("Failures / Unresolved Errors:", assistant_turn["content"])
        self.assertIn("execute_command", assistant_turn["content"])
        self.assertIn("exit code 1", assistant_turn["content"])
        self.assertIn("FAIL src/App.test.jsx", assistant_turn["content"])

    def test_unresolved_syntax_error_from_linter_is_retained(self):
        """When Turn 1 ends with a lint failure, the syntax diagnostics are retained in Turn 2."""
        turn_1_messages = [
            {"role": "user", "content": "Check syntax"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "lint_javascript",
                            "arguments": {"file_path": "src/App.jsx"},
                        }
                    }
                ],
            },
            {
                "role": "tool",
                "name": "lint_javascript",
                "content": "❌ Found 1 syntax error(s) across 1 file(s):\n\n[src/App.jsx]\nUnexpected token (15:2)",
            },
        ]

        res = ContextManager.prepare_messages(
            user_prompt="Fix the syntax error",
            system_prompt="System Prompt",
            existing_messages=turn_1_messages,
        )

        assistant_turn = res[2]
        self.assertIn("Failures / Unresolved Errors:", assistant_turn["content"])
        self.assertIn("lint_javascript", assistant_turn["content"])
        self.assertIn("❌ Found 1 syntax error", assistant_turn["content"])

    def test_bounded_error_retention_prevents_context_explosion(self):
        """Very large failure logs (>2,000 chars) are cleanly bounded in compacted assistant turn."""
        huge_trace = "[Command failed with exit code 2]\nFATAL ERROR in build pipeline:\n" + ("Error line detail: traceback stack frame\n" * 100)
        turn_1_messages = [
            {"role": "user", "content": "Build application"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "execute_command", "arguments": {"command": "npm run build"}}}
                ],
            },
            {"role": "tool", "name": "execute_command", "content": huge_trace},
        ]

        res = ContextManager.prepare_messages(
            user_prompt="Why did the build crash?",
            system_prompt="System Prompt",
            existing_messages=turn_1_messages,
        )

        assistant_turn = res[2]
        self.assertIn("Failures / Unresolved Errors:", assistant_turn["content"])
        self.assertIn("exit code 2", assistant_turn["content"])
        # Retained error must be bounded and not repeat all 100 lines
        self.assertLess(len(assistant_turn["content"]), 800)


class TestMilestoneRollups(unittest.TestCase):
    """
    Test suite for ITEM-12: Milestone Roll-ups (CP-103.2).
    Collapses intermediate failed tool loops once an edit/test passes.
    """

    def test_intra_turn_milestone_rollup_collapses_resolved_failure_loop(self):
        """When an edit and retest pass within a turn, intermediate failure output is rolled up."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Fix the broken test"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "execute_command", "arguments": {"command": "npm test"}}}],
            },
            {
                "role": "tool",
                "name": "execute_command",
                "content": "[Command failed with exit code 1]\nFAIL src/App.test.jsx\n" + ("trace stack line\n" * 50),
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "edit_file", "arguments": {"file_path": "src/App.jsx"}}}],
            },
            {
                "role": "tool",
                "name": "edit_file",
                "content": "Successfully edited src/App.jsx",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "execute_command", "arguments": {"command": "npm test"}}}],
            },
            {
                "role": "tool",
                "name": "execute_command",
                "content": "PASS src/App.test.jsx\nTests: 2 passed, 2 total\nCommand completed with exit code 0",
            },
        ]

        # Apply milestone roll-up
        messages, rolled_up = ContextSquasher.rollup_milestones(messages)
        self.assertTrue(rolled_up)

        # First tool result (failed test) must be collapsed into milestone marker
        first_tool_res = messages[3]
        self.assertIn("[Milestone Roll-up: Prior failure on 'npm test' resolved by subsequent successful run.]", first_tool_res["content"])
        self.assertNotIn("trace stack line", first_tool_res["content"])

        # Final tool result (passing test) must remain intact
        last_tool_res = messages[7]
        self.assertIn("PASS src/App.test.jsx", last_tool_res["content"])

    def test_intra_turn_milestone_rollup_with_linter(self):
        """Linter error resolved by edit and subsequent lint pass is collapsed into milestone marker."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Check and fix syntax"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "lint_javascript", "arguments": {"file_path": "src/App.jsx"}}}],
            },
            {
                "role": "tool",
                "name": "lint_javascript",
                "content": "❌ Found 1 syntax error(s) across 1 file(s):\n\n[src/App.jsx]\nUnexpected token (14:2)",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "edit_file", "arguments": {"file_path": "src/App.jsx"}}}],
            },
            {
                "role": "tool",
                "name": "edit_file",
                "content": "Successfully edited src/App.jsx",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "lint_javascript", "arguments": {"file_path": "src/App.jsx"}}}],
            },
            {
                "role": "tool",
                "name": "lint_javascript",
                "content": "✅ No syntax errors found across 1 file(s) (src/App.jsx).",
            },
        ]

        messages, rolled_up = ContextSquasher.rollup_milestones(messages)
        self.assertTrue(rolled_up)

        # First tool result should be rolled up
        self.assertIn("[Milestone Roll-up:", messages[3]["content"])
        # Successful lint check should be intact
        self.assertIn("✅ No syntax errors found", messages[7]["content"])

    def test_inter_turn_resolved_milestones_not_reported_as_active_errors(self):
        """When a turn has a failure that was resolved in the same turn, it is not reported under active errors."""
        turn_messages = [
            {"role": "user", "content": "Run tests and fix if failing"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "execute_command", "arguments": {"command": "npm test"}}}],
            },
            {
                "role": "tool",
                "name": "execute_command",
                "content": "[Command failed with exit code 1]\nFAIL src/App.test.jsx",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "edit_file", "arguments": {"file_path": "src/App.jsx"}}}],
            },
            {
                "role": "tool",
                "name": "edit_file",
                "content": "Successfully edited src/App.jsx",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "execute_command", "arguments": {"command": "npm test"}}}],
            },
            {
                "role": "tool",
                "name": "execute_command",
                "content": "PASS src/App.test.jsx\nCommand completed with exit code 0",
            },
        ]

        compacted = ContextManager.compact_prior_turns(turn_messages)
        self.assertEqual(len(compacted), 2)
        assistant_turn = compacted[1]
        self.assertNotIn("Failures / Unresolved Errors:", assistant_turn["content"])
        self.assertIn("Updated files: src/App.jsx.", assistant_turn["content"])
        self.assertIn("Milestones resolved:", assistant_turn["content"])

    def test_milestone_detection_does_not_false_positive_on_error_with_pass(self):
        """Errors containing words like 'pass' (e.g. 'pass a valid option') are not misidentified as milestones."""
        error_content = "SyntaxError: Unexpected token. Please pass a valid option."
        self.assertFalse(ContextSquasher.is_success_milestone(error_content, "execute_command"))
        summary = ContextSquasher.extract_tool_error_summary(error_content, "execute_command")
        self.assertIsNotNone(summary)
        self.assertIn("SyntaxError", summary)

    def test_milestone_rollup_multi_tool_turn_target_matching(self):
        """When an assistant message executes multiple tools of the same type, each result consumes its matching target."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Update files and test"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "edit_file", "arguments": {"file_path": "src/App.jsx"}}},
                    {"function": {"name": "edit_file", "arguments": {"file_path": "src/index.css"}}},
                ],
            },
            {"role": "tool", "name": "edit_file", "content": "Error editing src/App.jsx: File not found"},
            {"role": "tool", "name": "edit_file", "content": "Successfully edited src/index.css"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "edit_file", "arguments": {"file_path": "src/App.jsx"}}},
                ],
            },
            {"role": "tool", "name": "edit_file", "content": "Successfully edited src/App.jsx"},
        ]

        messages, rolled_up = ContextSquasher.rollup_milestones(messages)
        self.assertTrue(rolled_up)
        # The earlier failure on src/App.jsx should be rolled up
        self.assertIn("[Milestone Roll-up: Prior failure on 'src/App.jsx' resolved by subsequent successful run.]", messages[3]["content"])
        # The success on src/index.css should remain intact
        self.assertEqual(messages[4]["content"], "Successfully edited src/index.css")

    def test_error_summary_deduplication(self):
        """extract_tool_error_summary does not append duplicate exit code lines."""
        content = "[Command failed with exit code 1]\nFAIL src/App.test.jsx"
        summary = ContextSquasher.extract_tool_error_summary(content, "execute_command")
        self.assertEqual(summary, "Command failed (exit code 1) — FAIL src/App.test.jsx")


class TestCompactorCumulativeRequirements(unittest.TestCase):
    """
    Test suite for ITEM-12: Update ContextCompactor to preserve cumulative user requirements across all turns.
    """

    def test_compactor_preserves_cumulative_user_requirements_across_turns(self):
        """When macro-compaction runs on multi-turn history, all user requirements are preserved in <analysis>."""
        messages_to_summarize = [
            {"role": "user", "content": "Build me a notes app"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "write_file", "arguments": {"file_path": "src/App.jsx"}}}],
            },
            {"role": "tool", "content": "File written successfully"},
            {"role": "user", "content": "Add tag filtering to notes"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "edit_file", "arguments": {"file_path": "src/App.jsx"}}}],
            },
            {"role": "tool", "content": "Successfully edited src/App.jsx"},
            {"role": "user", "content": "Add dark mode toggle"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "edit_file", "arguments": {"file_path": "src/App.jsx"}}}],
            },
            {"role": "tool", "content": "Successfully edited src/App.jsx"},
        ]

        head = ContextCompactor.generate_synthetic_head(messages_to_summarize)

        self.assertIn("<analysis>", head)
        self.assertIn("Original User Request: Build me a notes app", head)
        self.assertIn("Cumulative User Directives:", head)
        self.assertIn("Add tag filtering to notes", head)
        self.assertIn("Add dark mode toggle", head)
        self.assertIn("src/App.jsx", head)
        self.assertIn("Continuation Posture", head)

    def test_compactor_preserves_unresolved_diagnostics_and_milestones(self):
        """When macro-compaction summarizes history with errors or milestones, they are included in <analysis>."""
        messages_to_summarize = [
            {"role": "user", "content": "Run tests"},
            {
                "role": "assistant",
                "content": "Executed command: npm test.\nFailures / Unresolved Errors:\n- [execute_command] Command failed (exit code 1) — FAIL src/App.test.jsx",
            },
        ]

        head = ContextCompactor.generate_synthetic_head(messages_to_summarize)

        self.assertIn("<analysis>", head)
        self.assertIn("Persistent Diagnostics / Active Issues:", head)
        self.assertIn("[execute_command] Command failed (exit code 1)", head)

    def test_compactor_chronological_resolution_does_not_report_resolved_errors_as_active(self):
        """When Turn 1 fails tests, but Turn 2 passes tests, the compacted <analysis> reports milestone and no active error."""
        messages_to_summarize = [
            {"role": "user", "content": "Run tests"},
            {
                "role": "assistant",
                "content": "Executed command: npm test.\nFailures / Unresolved Errors:\n- [execute_command] Command failed (exit code 1) — FAIL src/App.test.jsx",
            },
            {"role": "user", "content": "Fix it"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "execute_command", "arguments": {"command": "npm test"}}}],
            },
            {
                "role": "tool",
                "name": "execute_command",
                "content": "PASS src/App.test.jsx\nTests: 2 passed, 0 failed\nCommand completed with exit code 0",
            },
            {"role": "assistant", "content": "Tests pass now!"},
        ]

        head = ContextCompactor.generate_synthetic_head(messages_to_summarize)
        self.assertIn("<analysis>", head)
        self.assertIn("Verified Session Milestones: Tests/verification passed", head)
        self.assertNotIn("Persistent Diagnostics / Active Issues:", head)

    def test_compactor_preserves_post_milestone_errors_as_active(self):
        """If tests passed in Turn 1, but failed in Turn 2, the Turn 2 failure IS reported as an active issue in <analysis>."""
        messages_to_summarize = [
            {"role": "user", "content": "Run initial tests"},
            {
                "role": "tool",
                "name": "execute_command",
                "content": "PASS src/App.test.jsx\nCommand completed with exit code 0",
            },
            {"role": "user", "content": "Add experimental feature"},
            {
                "role": "assistant",
                "content": "Executed command: npm test.\nFailures / Unresolved Errors:\n- [execute_command] Command failed (exit code 1) — FAIL src/App.test.jsx",
            },
        ]

        head = ContextCompactor.generate_synthetic_head(messages_to_summarize)
        self.assertIn("<analysis>", head)
        self.assertIn("Verified Session Milestones: Tests/verification passed", head)
        self.assertIn("Persistent Diagnostics / Active Issues:", head)
        self.assertIn("[execute_command] Command failed (exit code 1)", head)

    def test_compactor_strips_alerts_from_cumulative_directives(self):
        """Eviction alert markers are cleanly stripped from user directives in <analysis>."""
        messages_to_summarize = [
            {
                "role": "user",
                "content": f"{ALERT_EVICTION_MARKER}\n\nBuild a notes app",
            },
            {"role": "assistant", "content": "Created base files."},
            {
                "role": "user",
                "content": "Add dark mode toggle",
            },
            {"role": "assistant", "content": "Added dark mode."},
        ]

        head = ContextCompactor.generate_synthetic_head(messages_to_summarize)
        self.assertIn("Original User Request: Build a notes app", head)
        self.assertIn("Add dark mode toggle", head)
        self.assertNotIn(ALERT_EVICTION_MARKER, head)

class TestContextTelemetry(unittest.TestCase):
    """
    Test suite for ITEM-13: Real-Time Context Telemetry (CP-106).
    """

    def test_get_context_telemetry_breakdown(self):
        """Calculates accurate layer token breakdown, RAM count, and window utilization percentage."""
        messages = [
            {"role": "system", "content": "You are Lowkey AI. Pinned Static Layer."},
            {"role": "user", "content": "Hello Lowkey!"},
            {"role": "assistant", "content": "Hello! How can I assist you today?"},
        ]
        ram = {
            "src/App.jsx": "function App() { return <div>Hello</div>; }",
            "server/index.js": "const express = require('express');",
        }
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "sample_tool",
                    "description": "Sample tool schema",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        config = ContextConfig(context_window=10000)
        telemetry = ContextManager.get_context_telemetry(
            messages=messages,
            model_name="qwen2.5-coder:14b",
            tools=tools,
            mounted_virtual_ram=ram,
            config=config,
        )

        self.assertGreater(telemetry["total_tokens"], 0)
        self.assertEqual(telemetry["context_window"], 10000)
        self.assertEqual(telemetry["virtual_ram_files"], 2)
        self.assertGreater(telemetry["virtual_ram_tokens"], 0)
        self.assertGreater(telemetry["static_tokens"], 0)
        self.assertGreater(telemetry["ephemeral_tokens"], 0)
        self.assertGreater(telemetry["schema_tokens"], 0)
        self.assertEqual(telemetry["status"], "normal")
        self.assertFalse(telemetry["squashed"])
        self.assertFalse(telemetry["evicted"])

    def test_get_context_telemetry_status_transitions(self):
        """Status transitions cleanly: normal (<60%) -> warning (60-80%) -> critical (>80%)."""
        config = ContextConfig(context_window=1000, squash_threshold=0.60, compact_threshold=0.82)

        # 1. Normal status (< 600 tokens)
        messages_low = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Short prompt"},
        ]
        t_low = ContextManager.get_context_telemetry(messages_low, config=config)
        self.assertEqual(t_low["status"], "normal")

        # 2. Warning status (approx 700 tokens > 600 squash limit)
        messages_mid = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "x" * 2600}, # ~700 tokens
        ]
        t_mid = ContextManager.get_context_telemetry(messages_mid, config=config)
        self.assertEqual(t_mid["status"], "warning")

        # 3. Critical status (approx 900 tokens > 820 compact limit)
        messages_high = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "x" * 3300}, # ~900 tokens
        ]
        t_high = ContextManager.get_context_telemetry(messages_high, config=config)
        self.assertEqual(t_high["status"], "critical")

    def test_get_context_telemetry_with_ram_embedded_in_system_prompt(self):
        """When virtual RAM is synced into messages[0], static_tokens correctly isolates the static layer and does not double count RAM."""
        base_system = "You are Lowkey AI. Pinned Static Layer."
        messages = [
            {"role": "system", "content": base_system},
            {"role": "user", "content": "Hello"},
        ]
        ram = {
            "src/App.jsx": "export default function App() { return <div>" + "x" * 2000 + "</div>; }",
            "server/index.js": "const express = require('express');\n" + "console.log('hi');\n" * 50,
        }
        # Sync RAM into messages[0]
        ContextManager.sync_virtual_ram_block(messages, ram)
        self.assertIn(ContextManager.RAM_HEADER, messages[0]["content"])

        config = ContextConfig(context_window=32768)
        telemetry = ContextManager.get_context_telemetry(
            messages=messages,
            mounted_virtual_ram=ram,
            config=config,
        )

        # Static tokens should be just the base system prompt (<1,500 tokens), not inflated by the 2k char RAM file
        base_tokens = TokenEstimator.estimate_message({"role": "system", "content": base_system})
        self.assertAlmostEqual(telemetry["static_tokens"], base_tokens, delta=10)
        self.assertGreater(telemetry["virtual_ram_tokens"], 300)
        self.assertEqual(telemetry["virtual_ram_files"], 2)
        # Total tokens should match static + ram + ephemeral + prime overhead
        expected_total = TokenEstimator.estimate_total(messages, virtual_ram=ram)
        self.assertEqual(telemetry["total_tokens"], expected_total)

    def test_get_context_telemetry_recovers_ram_when_dict_not_passed(self):
        """Telemetry recovers RAM token counts and file count from embedded block if mounted_virtual_ram is None."""
        messages = [
            {"role": "system", "content": "Base System Prompt."},
            {"role": "user", "content": "Inspect code"},
        ]
        ram = {
            "app.py": "print('hello world')",
            "config.json": '{"port": 3000}',
        }
        ContextManager.sync_virtual_ram_block(messages, ram)

        # Call get_context_telemetry with mounted_virtual_ram=None
        telemetry = ContextManager.get_context_telemetry(messages, mounted_virtual_ram=None)
        self.assertEqual(telemetry["virtual_ram_files"], 2)
        self.assertGreater(telemetry["virtual_ram_tokens"], 0)

    def test_get_context_telemetry_compaction_flags_detection(self):
        """Historical eviction and roll-up markers in messages are detected and set telemetry flags."""
        messages_evicted = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": f"{ALERT_EVICTION_MARKER}\nNext task"},
            {"role": "assistant", "content": "Working on it"},
        ]
        t_evicted = ContextManager.get_context_telemetry(messages_evicted)
        self.assertTrue(t_evicted["evicted"])
        self.assertEqual(t_evicted["status"], "critical")

        messages_rollup = [
            {"role": "system", "content": "System prompt"},
            {"role": "tool", "name": "execute_command", "content": "[Milestone Roll-up: Prior failure on 'test' resolved by subsequent successful run.]"},
        ]
        t_rollup = ContextManager.get_context_telemetry(messages_rollup)
        self.assertTrue(t_rollup["rolled_up"])

        messages_squashed = [
            {"role": "system", "content": "System prompt"},
            {"role": "tool", "name": "read_file", "content": "head\n\n[... LOG TRUNCATED BY ENGINE ...]\n\ntail"},
        ]
        t_squashed = ContextManager.get_context_telemetry(messages_squashed)
        self.assertTrue(t_squashed["squashed"])

    def test_maybe_squash_return_details(self):
        """maybe_squash returns (was_applied, squashed, evicted, rolled_up) when return_details=True."""
        messages = [
            {"role": "user", "content": "User task"},
            {"role": "assistant", "content": "Plan"},
            {"role": "tool", "name": "cmd1", "content": "result 1: " + ("x" * 1000)},
            {"role": "assistant", "content": "Plan 2"},
            {"role": "tool", "name": "cmd2", "content": "result 2: " + ("y" * 1000)},
            {"role": "assistant", "content": "Plan 3"},
            {"role": "tool", "name": "cmd3", "content": "result 3: " + ("z" * 1000)},
            {"role": "assistant", "content": "Plan 4"},
            {"role": "tool", "name": "cmd4", "content": "result 4: " + ("w" * 1000)},
            {"role": "assistant", "content": "Plan 5"},
            {"role": "tool", "name": "cmd5", "content": "result 5: " + ("v" * 1000)},
        ]
        config = ContextConfig(context_window=32768, preserve_last_n_tools=3)
        was_applied, squashed, evicted, rolled_up = ContextManager.maybe_squash(
            messages, config=config, return_details=True
        )
        self.assertTrue(was_applied)
        self.assertTrue(squashed)
        self.assertFalse(evicted)
        self.assertFalse(rolled_up)

    def test_get_context_telemetry_dynamic_thresholds(self):
        """Telemetry includes dynamic squash and compact threshold percentages from config."""
        config = ContextConfig(context_window=10000, squash_threshold=0.65, compact_threshold=0.85)
        telemetry = ContextManager.get_context_telemetry([], config=config)
        self.assertEqual(telemetry["squash_threshold_pct"], 65.0)
        self.assertEqual(telemetry["compact_threshold_pct"], 85.0)

    def test_get_context_telemetry_empty_messages(self):
        """Edge case: empty messages and no tools returns clean zeroed telemetry without throwing."""
        telemetry = ContextManager.get_context_telemetry([])
        self.assertEqual(telemetry["message_count"], 0)
        self.assertEqual(telemetry["static_tokens"], 0)
        self.assertEqual(telemetry["ephemeral_tokens"], 0)
        self.assertEqual(telemetry["virtual_ram_tokens"], 0)
        self.assertEqual(telemetry["status"], "normal")
if __name__ == "__main__":
    unittest.main()






