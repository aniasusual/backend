"""
Unit tests verifying browser interaction tools, DOM observation, and tester subagent tool configuration.
"""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

from tools.interaction_tools import InteractionTools, DOMObserver, PlaywrightBrowserSession
from task.agents import load_bundled_agents, clear_bundled_agents_cache


class TestBrowserToolsAndTesterAgent(unittest.IsolatedAsyncioTestCase):
    """Test browser tool bindings and tester agent definition."""

    def setUp(self):
        clear_bundled_agents_cache()

    def tearDown(self):
        clear_bundled_agents_cache()

    def test_tester_agent_has_browser_tools(self):
        """Verify the tester subagent definition includes all required browser tools."""
        bundled = load_bundled_agents()
        self.assertIn("tester", bundled)
        tester = bundled["tester"]

        required_tools = [
            "browser_navigate",
            "browser_click",
            "browser_fill",
            "browser_snapshot",
            "browser_screenshot",
            "browser_scroll",
            "yield",
            "hub",
        ]
        for tool in required_tools:
            self.assertIn(tool, tester.tools, f"Tester subagent missing tool '{tool}'")

    def test_interaction_tools_has_browser_methods(self):
        """Verify InteractionTools exposes the browser automation methods."""
        tools = InteractionTools()
        self.assertTrue(hasattr(tools, "browser_navigate"))
        self.assertTrue(hasattr(tools, "browser_click"))
        self.assertTrue(hasattr(tools, "browser_fill"))
        self.assertTrue(hasattr(tools, "browser_snapshot"))
        self.assertTrue(hasattr(tools, "browser_screenshot"))
        self.assertTrue(hasattr(tools, "browser_scroll"))
        self.assertTrue(hasattr(tools, "cleanup"))

    def test_dom_observer_formatting(self):
        """Verify DOMObserver formats observation state for LLM."""
        obs = {
            "url": "http://localhost:3000",
            "title": "Kanban App",
            "elements": [
                {"id": "el_0", "tag": "button", "text": "Add Task", "disabled": False, "checked": False},
                {"id": "el_1", "tag": "input", "placeholder": "Enter task title", "disabled": False, "checked": False},
            ],
            "dom_errors": ["Network error 500"],
            "can_scroll_down": True,
        }

        formatted = DOMObserver.format_observation_for_llm(
            observation=obs,
            step=1,
            max_steps=10,
            instructions="Test adding task",
            console_errors=["Uncaught TypeError: Cannot read properties of undefined"],
        )

        self.assertIn("Kanban App", formatted)
        self.assertIn("http://localhost:3000", formatted)
        self.assertIn("Add Task", formatted)
        self.assertIn("el_0", formatted)
        self.assertIn("Network error 500", formatted)
        self.assertIn("Uncaught TypeError", formatted)

    @patch.object(PlaywrightBrowserSession, "ensure_page")
    async def test_browser_session_methods(self, mock_ensure_page):
        mock_page = MagicMock()
        mock_ensure_page.return_value = mock_page
        mock_page.url = "http://localhost:3000"
        mock_page.title = AsyncMock(return_value="Kanban App")
        mock_page.evaluate = AsyncMock(return_value={"elements": [], "can_scroll_down": False})
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.click = AsyncMock()
        mock_page.fill = AsyncMock()

        session = PlaywrightBrowserSession()

        # Test navigate
        res = await session.navigate("http://localhost:3000")
        self.assertIn("Kanban App", res)
        mock_page.goto.assert_called_once()

        # Test click
        mock_page.reset_mock()
        await session.click("el_0")
        mock_page.click.assert_called_with('[data-sdet-id="el_0"]', timeout=5000)

        # Test fill
        mock_page.reset_mock()
        await session.fill("el_1", "New Task")
        mock_page.fill.assert_called_with('[data-sdet-id="el_1"]', "New Task", timeout=5000)

        # Test scroll
        mock_page.reset_mock()
        await session.scroll(direction="down", amount=300)
        mock_page.evaluate.assert_called()

if __name__ == "__main__":
    unittest.main()
