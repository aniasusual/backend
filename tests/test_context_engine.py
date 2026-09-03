"""
Test Suite for Lowkey Production Context Management Engine.
Verifies TokenEstimator, ContextSquasher, ContextCompactor, and ContextManager using standard unittest.
"""

import json
import unittest

from utils.context_manager import (
    ContextConfig,
    TokenEstimator,
    ContextSquasher,
    ContextCompactor,
    ContextManager,
)
from config.models import get_model_context_window


class TestModelContextWindow(unittest.TestCase):
    def test_context_window_lookup(self):
        self.assertEqual(get_model_context_window("qwen2.5-coder:14b"), 32768)
        self.assertEqual(get_model_context_window("llama3.1:8b"), 131072)
        self.assertEqual(get_model_context_window("deepseek-r1:14b"), 65536)
        self.assertEqual(get_model_context_window("gemma2:9b"), 8192)
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

        # Latest user prompt must have the confirmation anchor
        latest_user = res[3]
        self.assertEqual(latest_user["role"], "user")
        self.assertIn("yes", latest_user["content"])
        self.assertIn("You now have the user's response/confirmation", latest_user["content"])

    def test_prepare_messages_error_handling(self):
        existing = [{"role": "user", "content": "Initial prompt"}]
        res = ContextManager.prepare_messages("It failed with a SyntaxError in App.jsx", "System Prompt", existing)

        latest_user = res[-1]
        self.assertIn("An error or bug was reported", latest_user["content"])

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


if __name__ == "__main__":
    unittest.main()
