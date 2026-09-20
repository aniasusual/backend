"""
Unit tests for StaticLayerManager and repository rule discovery.
Verifies compliance with [CP-101.1] in the Dynamic Context Management Specification.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from context.static_layer import StaticLayerManager
from context.manager import ContextManager
from context.estimator import TokenEstimator
from plugins.coding_harness import CodingHarness


class TestStaticLayerManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_discovery_precedence(self):
        """Verifies discovery priority: .agentrules > AGENTS.md > .cursorrules > CLAUDE.md > README.md."""
        agentrules = self.project_root / ".agentrules"
        agents_md = self.project_root / "AGENTS.md"
        cursorrules = self.project_root / ".cursorrules"
        claude_md = self.project_root / "CLAUDE.md"
        readme_md = self.project_root / "README.md"

        agentrules.write_text("Priority 1: .agentrules", encoding="utf-8")
        agents_md.write_text("Priority 2: AGENTS.md", encoding="utf-8")
        cursorrules.write_text("Priority 3: .cursorrules", encoding="utf-8")
        claude_md.write_text("Priority 4: CLAUDE.md", encoding="utf-8")
        readme_md.write_text("Priority 5: README.md", encoding="utf-8")

        # 1. .agentrules wins
        rule1 = StaticLayerManager.discover_project_rules(self.project_root)
        self.assertIsNotNone(rule1)
        self.assertEqual(rule1["file_name"], ".agentrules")
        self.assertEqual(rule1["content"], "Priority 1: .agentrules")

        # 2. AGENTS.md wins when .agentrules is removed
        agentrules.unlink()
        rule2 = StaticLayerManager.discover_project_rules(self.project_root)
        self.assertIsNotNone(rule2)
        self.assertEqual(rule2["file_name"], "AGENTS.md")
        self.assertEqual(rule2["content"], "Priority 2: AGENTS.md")

        # 3. .cursorrules wins when AGENTS.md is removed
        agents_md.unlink()
        rule3 = StaticLayerManager.discover_project_rules(self.project_root)
        self.assertIsNotNone(rule3)
        self.assertEqual(rule3["file_name"], ".cursorrules")
        self.assertEqual(rule3["content"], "Priority 3: .cursorrules")

        # 4. CLAUDE.md wins when .cursorrules is removed
        cursorrules.unlink()
        rule4 = StaticLayerManager.discover_project_rules(self.project_root)
        self.assertIsNotNone(rule4)
        self.assertEqual(rule4["file_name"], "CLAUDE.md")
        self.assertEqual(rule4["content"], "Priority 4: CLAUDE.md")

        # 5. README.md wins when CLAUDE.md is removed
        claude_md.unlink()
        rule5 = StaticLayerManager.discover_project_rules(self.project_root)
        self.assertIsNotNone(rule5)
        self.assertEqual(rule5["file_name"], "README.md")
        self.assertEqual(rule5["content"], "Priority 5: README.md")

    def test_readme_fallback_when_no_agent_rules_present(self):
        """Verifies README.md is loaded as a fallback when no dedicated agent instruction files exist."""
        readme = self.project_root / "README.md"
        readme.write_text("# Project Title\n\nRun `npm install` and start on port 5001.", encoding="utf-8")

        rule_info = StaticLayerManager.discover_project_rules(self.project_root)
        self.assertIsNotNone(rule_info)
        self.assertEqual(rule_info["file_name"], "README.md")
        self.assertIn("# Project Title", rule_info["content"])

        block = StaticLayerManager.format_rules_block(rule_info)
        self.assertIn("## Repository Directives & Guidelines (README.md)", block)
        self.assertIn("Run `npm install`", block)

    def test_missing_or_empty_rules_returns_none(self):
        """Verifies None returned cleanly when no rule files exist or files are empty."""
        # Empty directory
        self.assertIsNone(StaticLayerManager.discover_project_rules(self.project_root))
        self.assertIsNone(StaticLayerManager.discover_project_rules(None))
        self.assertIsNone(StaticLayerManager.discover_project_rules(self.project_root / "nonexistent"))

        # Empty rule file
        (self.project_root / ".agentrules").write_text("   \n   ", encoding="utf-8")
        self.assertIsNone(StaticLayerManager.discover_project_rules(self.project_root))

    def test_strict_token_budget_truncation(self):
        """Verifies rule files exceeding the 1,500 token ceiling are bounded with a notice."""
        long_rule_lines = [f"Rule {i}: Always maintain strict TypeScript typings and unit test coverage." for i in range(250)]
        long_rule_text = "\n".join(long_rule_lines)

        raw_tokens = TokenEstimator.estimate_text(long_rule_text)
        self.assertGreater(raw_tokens, 1500)

        (self.project_root / ".agentrules").write_text(long_rule_text, encoding="utf-8")

        rule_info = StaticLayerManager.discover_project_rules(self.project_root, max_tokens=1500)
        self.assertIsNotNone(rule_info)
        self.assertTrue(rule_info["truncated"])
        self.assertLessEqual(rule_info["tokens"], 1500)
        self.assertTrue(rule_info["content"].endswith(StaticLayerManager.TRUNCATION_NOTICE))

    def test_format_rules_block(self):
        """Verifies markdown formatting of the rules block."""
        rule_info = {
            "file_name": ".agentrules",
            "content": "Rule 1: Use Tailwind v4.\nRule 2: Avoid any.",
        }
        block = StaticLayerManager.format_rules_block(rule_info)
        self.assertIn("## Repository Directives & Guidelines (.agentrules)", block)
        self.assertIn("Rule 1: Use Tailwind v4.", block)
        self.assertEqual(StaticLayerManager.format_rules_block(None), "")

    def test_build_static_prompt(self):
        """Verifies complete Static Layer prompt composition."""
        (self.project_root / "AGENTS.md").write_text("Strict naming: camelCase for methods.", encoding="utf-8")

        prompt = StaticLayerManager.build_static_prompt(
            base_prompt="You are an autonomous developer.",
            project_root=self.project_root,
            runtime_context="Active server on port 5173",
            reasoning_fallback="Tool Calling JSON Protocol",
        )

        self.assertIn("You are an autonomous developer.", prompt)
        self.assertIn("## Repository Directives & Guidelines (AGENTS.md)", prompt)
        self.assertIn("Strict naming: camelCase for methods.", prompt)
        self.assertIn("Active server on port 5173", prompt)
        self.assertIn("Tool Calling JSON Protocol", prompt)


class TestStaticLayerIntegration(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_prepare_messages_mounts_repo_rules(self):
        """Verifies ContextManager.prepare_messages mounts discovered rules into the system message."""
        (self.project_root / ".agentrules").write_text("Rule A: Never delete database migrations.", encoding="utf-8")

        messages = ContextManager.prepare_messages(
            user_prompt="Add user email column",
            system_prompt="Base Identity.",
            existing_messages=[],
            project_root=self.project_root,
        )

        self.assertGreaterEqual(len(messages), 1)
        system_msg = messages[0]
        self.assertEqual(system_msg["role"], "system")
        self.assertIn("Base Identity.", system_msg["content"])
        self.assertIn("## Repository Directives & Guidelines (.agentrules)", system_msg["content"])
        self.assertIn("Rule A: Never delete database migrations.", system_msg["content"])

        # Subsequent call does not create duplicate rule blocks
        messages_turn2 = ContextManager.prepare_messages(
            user_prompt="Second turn",
            system_prompt=system_msg["content"],
            existing_messages=messages,
            project_root=self.project_root,
        )
        count = messages_turn2[0]["content"].count("## Repository Directives & Guidelines")
        self.assertEqual(count, 1)

    async def test_coding_harness_injects_agentrules_into_ollama(self):
        """Verifies CodingHarness discovers .agentrules from sandbox_path and passes them to client.chat()."""
        (self.project_root / ".agentrules").write_text("Rule X: Express port must be 5001.", encoding="utf-8")

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {}
        mock_registry.get_dev_server_info.return_value = None
        mock_registry.sandbox_path = self.project_root

        context = {
            "registry": mock_registry,
            "messages": [],
            "model": "qwen2.5-coder:7b",
        }

        mock_chunk = MagicMock()
        mock_chunk.message.thinking = None
        mock_chunk.message.tool_calls = None
        mock_chunk.message.content = "Confirmed rules."

        async def mock_stream_gen():
            yield mock_chunk

        with patch("ollama.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_stream_gen())
            mock_client_cls.return_value = mock_client

            harness = CodingHarness(model_name="qwen2.5-coder:7b")
            async for _ in harness.process_prompt("Initialize app", context):
                pass

            self.assertTrue(mock_client.chat.called)
            chat_messages = mock_client.chat.call_args.kwargs["messages"]
            system_content = chat_messages[0]["content"]

            self.assertIn("## Repository Directives & Guidelines (.agentrules)", system_content)
            self.assertIn("Rule X: Express port must be 5001.", system_content)


if __name__ == "__main__":
    unittest.main()
