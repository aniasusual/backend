"""
Unit test to verify that the UI testing subagent correctly auto-resolves
the application URL from the active dev server.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import shutil
import uuid
from config.settings import PROJECTS_ROOT
from tools.process_tools import ProcessTools
from tools.registry import ToolRegistry
from plugins.argument_normalizer import ToolArgumentNormalizer
from subagents.ui_subagent import UITestingSubagent


class TestTestingAgentUrlResolution(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = PROJECTS_ROOT / f"_test_url_{uuid.uuid4().hex[:8]}"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.registry = ToolRegistry(self.tmp_dir)

    def tearDown(self):
        self.registry.cleanup()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_get_dev_server_info_empty_when_no_server(self):
        info = self.registry.get_dev_server_info()
        self.assertIsNone(info)

    def test_get_dev_server_info_when_running(self):
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running

        self.registry.process_tools.background_processes[12345] = {
            "process": mock_process,
            "command": "npm run dev",
            "port": 3005,
            "backend_port": 5005,
            "is_dev_server": True,
        }

        info = self.registry.get_dev_server_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["port"], 3005)
        self.assertEqual(info["backend_port"], 5005)
        self.assertEqual(info["url"], "http://localhost:3005")
        self.assertEqual(info["backend_url"], "http://localhost:5005")

    def test_invoke_testing_agent_auto_resolves_empty_url(self):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        self.registry.process_tools.background_processes[12345] = {
            "process": mock_process,
            "command": "npm run dev",
            "port": 3002,
            "backend_port": 5002,
            "is_dev_server": True,
        }

        with patch.object(self.registry.ui_testing_subagent, "run_ui_test") as mock_run:
            mock_run.return_value = "PASSED"

            # Case 1: Empty URL
            self.registry.invoke_testing_agent(url="", instructions="Check buttons")
            mock_run.assert_called_with("http://localhost:3002", "Check buttons")

            # Case 2: Vite default 5173 hallucination
            self.registry.invoke_testing_agent(url="http://localhost:5173", instructions="Check inputs")
            mock_run.assert_called_with("http://localhost:3002", "Check inputs")

            # Case 3: Accidental backend port passed
            self.registry.invoke_testing_agent(url="http://localhost:5002", instructions="Check API")
            mock_run.assert_called_with("http://localhost:3002", "Check API")

            # Case 4: Explicit valid custom URL preserved
            self.registry.invoke_testing_agent(url="http://localhost:4000/app", instructions="Check custom")
            mock_run.assert_called_with("http://localhost:4000/app", "Check custom")

    def test_argument_normalizer_handles_missing_url(self):
        args = {"instructions": "Test the page"}
        normalized = ToolArgumentNormalizer.normalize("invoke_testing_agent", args)
        self.assertIn("url", normalized)
        self.assertEqual(normalized["url"], "")
        self.assertEqual(normalized["instructions"], "Test the page")

    def test_argument_normalizer_handles_target_url(self):
        args = {"target_url": "http://localhost:3000", "prompt": "Check login"}
        normalized = ToolArgumentNormalizer.normalize("invoke_testing_agent", args)
        self.assertEqual(normalized["url"], "http://localhost:3000")
        self.assertEqual(normalized["instructions"], "Check login")


if __name__ == "__main__":
    unittest.main()
