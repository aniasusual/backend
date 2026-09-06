import unittest
import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from config.settings import PROJECTS_ROOT
from subagents.runner import SubagentRunner
from subagents.troubleshoot_subagent import TroubleshootSubagent
from tools.registry import ToolRegistry
from config.agent_loader import AgentLoader


class TestSubagentRunner(unittest.TestCase):
    """Unit tests for the autonomous child-loop SubagentRunner."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_runner_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)

        # Create dummy workspace files
        self.app_file = self.sandbox_path / "src" / "App.jsx"
        self.app_file.parent.mkdir(parents=True, exist_ok=True)
        self.app_file.write_text("import React from 'react';\nexport default function App() {\n  return <div>Hello</div>;\n}\n")

        self.registry = ToolRegistry(self.sandbox_path)

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_scoped_tool_filtering(self):
        """Verify runner only scopes whitelisted tools in schema and map."""
        allowed = {"read_file", "grep_search"}
        runner = SubagentRunner(
            name="test_subagent",
            system_prompt="Test prompt",
            allowed_tools=allowed,
            tool_registry=self.registry,
        )

        scoped_schemas = runner._get_scoped_schemas()
        schema_names = {s["function"]["name"] for s in scoped_schemas}
        self.assertEqual(schema_names, allowed)

        scoped_tools = runner._get_scoped_tool_map()
        self.assertEqual(set(scoped_tools.keys()), allowed)

    def test_permission_denied_on_forbidden_tool(self):
        """Verify that attempting to call a non-whitelisted tool returns permission denied."""
        allowed = {"read_file"}
        runner = SubagentRunner(
            name="read_only_agent",
            system_prompt="Read only prompt",
            allowed_tools=allowed,
            tool_registry=self.registry,
        )

        # Mock Ollama chat to attempt calling write_file
        with patch("ollama.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            # Iteration 1: model attempts to call forbidden tool 'write_file'
            mock_client.chat.side_effect = [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "write_file",
                                    "arguments": {"file_path": "hacked.txt", "content": "bad"},
                                }
                            }
                        ],
                    }
                },
                # Iteration 2: model realizes it's denied and gives up
                {
                    "message": {
                        "content": "I apologize, I do not have permission to write files.",
                        "tool_calls": [],
                    }
                },
            ]

            result = runner.run("Please write a file.")
            self.assertIn("do not have permission to write files", result)
            # Ensure hacked.txt was NOT written
            self.assertFalse((self.sandbox_path / "hacked.txt").exists())

    def test_allowed_tool_execution(self):
        """Verify whitelisted tool is executed and result fed back to child loop."""
        allowed = {"read_file"}
        events = []
        runner = SubagentRunner(
            name="reader_agent",
            system_prompt="Reader prompt",
            allowed_tools=allowed,
            tool_registry=self.registry,
            event_callback=lambda evt: events.append(evt),
        )

        with patch("ollama.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            mock_client.chat.side_effect = [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_file",
                                    "arguments": {"file_path": "src/App.jsx"},
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "content": "File contains standard React App component.",
                        "tool_calls": [],
                    }
                },
            ]

            result = runner.run("Inspect App.jsx")
            self.assertIn("File contains standard React App component", result)
            # Verify event telemetry was dispatched
            tool_events = [e for e in events if e.get("event") == "tool_executed"]
            self.assertTrue(len(tool_events) >= 1)
            self.assertEqual(tool_events[0]["tool"], "read_file")


class TestTroubleshootSubagent(unittest.TestCase):
    """Unit tests for TroubleshootSubagent."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_troubleshoot_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)

        self.app_file = self.sandbox_path / "src" / "App.jsx"
        self.app_file.parent.mkdir(parents=True, exist_ok=True)
        self.app_file.write_text("import React from 'react';\nexport default function App() {\n  return <div>{user.name}</div>;\n}\n")

        self.registry = ToolRegistry(self.sandbox_path)
        self.subagent = TroubleshootSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
        )

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_read_only_tool_restriction(self):
        """Verify TroubleshootSubagent only allows read-only tools including glob_files."""
        self.assertEqual(
            self.subagent.allowed_tools,
            {"read_file", "view_bulk", "grep_search", "lint_javascript", "glob_files"},
        )
        self.assertNotIn("write_file", self.subagent.allowed_tools)
        self.assertNotIn("edit_file", self.subagent.allowed_tools)
        self.assertNotIn("execute_command", self.subagent.allowed_tools)

    def test_deterministic_missing_dependency_prefilter(self):
        """Verify fast-path for missing npm dependency."""
        error = "Failed to resolve import 'lucide-react' from 'src/App.jsx'. Does the file exist?"
        result = self.subagent.diagnose_error(error)
        self.assertIn("Root Cause Analysis (RCA): Missing Dependency", result)
        self.assertIn("npm install lucide-react", result)

    def test_relative_import_disambiguation(self):
        """Verify local relative import is never diagnosed as npm package or npm install ."""
        error = "Failed to resolve import './components/Header' from 'src/App.jsx'. Does the file exist?"
        result = self.subagent.diagnose_error(error)
        self.assertIn("Root Cause Analysis (RCA): Missing Local File / Component", result)
        self.assertNotIn("npm install .", result)
        self.assertNotIn("Missing Dependency", result)

    def test_ansi_stripping_and_location_extraction(self):
        """Verify ANSI color codes are stripped and file location extracted correctly."""
        ansi_log = "\x1b[31m[vite] Internal server error\x1b[39m\n  at App (\x1b[36msrc/App.jsx:42:15\x1b[39m)"
        from subagents.troubleshoot import StackTraceParser
        loc = StackTraceParser.extract_file_location(ansi_log)
        self.assertEqual(loc, "src/App.jsx:42")

    def test_python_stack_trace_extraction(self):
        """Verify Python stack trace line extraction."""
        py_log = 'Traceback (most recent call last):\n  File "server/server.py", line 42, in get_users\nZeroDivisionError: division by zero'
        from subagents.troubleshoot import StackTraceParser
        loc = StackTraceParser.extract_file_location(py_log)
        self.assertEqual(loc, "server/server.py:42")

    def test_deterministic_port_conflict_prefilter(self):
        """Verify fast-path for EADDRINUSE port collision."""
        error = "Error: listen EADDRINUSE: address already in use 0.0.0.0:3000"
        result = self.subagent.diagnose_error(error)
        self.assertIn("Root Cause Analysis (RCA): Port Conflict", result)
        self.assertIn("3000", result)

    def test_deterministic_cors_prefilter(self):
        """Verify fast-path for CORS security block."""
        error = "Access to XMLHttpRequest at 'http://localhost:3000/api' has been blocked by CORS policy"
        result = self.subagent.diagnose_error(error)
        self.assertIn("Root Cause Analysis (RCA): CORS Security Block", result)
        self.assertIn("cors", result)

    def test_autonomous_investigation_call(self):
        """Verify autonomous child runner is invoked for complex runtime errors."""
        error = "TypeError: Cannot read properties of undefined (reading 'name') at App (src/App.jsx:3:28)"

        with patch("subagents.troubleshoot_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = "### 🩺 Root Cause Analysis (RCA)\n- **Issue**: user object is undefined\n- **Root Cause**: missing initial state"

            result = self.subagent.diagnose_error(error)
            mock_runner.run.assert_called_once()
            self.assertIn("user object is undefined", result)

    def test_runner_failure_string_triggers_heuristic_fallback(self):
        """Verify runner error string (e.g. Subagent execution failed...) triggers fallback rather than raw error return."""
        error = "TypeError: Cannot read properties of undefined (reading 'name') at App (src/App.jsx:3:28)"

        with patch("subagents.troubleshoot_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = "Subagent execution failed due to model error: Connection refused to Ollama"

            result = self.subagent.diagnose_error(error)
            self.assertIn("Root Cause Analysis (RCA): Undefined Property Access", result)
            self.assertNotIn("Subagent execution failed", result)
            self.assertIn("?.name", result)




class TestToolStandardization(unittest.TestCase):
    """Verifies that tool registries, agent profiles, and parsers use strict canonical names without ghost aliases."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_tools_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.registry = ToolRegistry(self.sandbox_path)

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_no_ghost_aliases_in_registry(self):
        """Ensure deprecated ghost aliases are absent from the tool registry."""
        tools = self.registry.get_tools()
        forbidden_aliases = [
            "get_assets_tool",
            "design_agent",
            "troubleshoot_agent",
            "vision_agent",
            "test_ui",
            "search_replace",
        ]
        for alias in forbidden_aliases:
            self.assertNotIn(alias, tools, f"Ghost alias '{alias}' should not be present in tool registry.")

    def test_canonical_subagents_in_registry(self):
        """Ensure all subagents adhere strictly to the invoke_*_agent naming convention."""
        tools = self.registry.get_tools()
        expected_subagents = [
            "invoke_design_agent",
            "invoke_troubleshoot_agent",
            "invoke_vision_agent",
            "invoke_testing_agent",
            "invoke_code_reviewer_agent",
        ]
        for subagent in expected_subagents:
            self.assertIn(subagent, tools, f"Canonical subagent '{subagent}' missing from registry.")
            self.assertTrue(callable(tools[subagent]))

    def test_agent_profile_no_synthetic_aliases(self):
        """Verify AgentProfile.all_callable_tools does not generate redundant short-name aliases."""
        from config.agent_loader import AgentProfile
        profile = AgentProfile(
            id="test_profile",
            name="Test",
            tier=1,
            whitelisted_tools=["read_file", "get_assets"],
            enabled_subagents=["invoke_design_agent", "invoke_testing_agent", "invoke_code_reviewer_agent"],
        )
        tools = profile.all_callable_tools
        self.assertIn("invoke_design_agent", tools)
        self.assertIn("invoke_testing_agent", tools)
        self.assertIn("invoke_code_reviewer_agent", tools)
        self.assertNotIn("design_agent", tools)
        self.assertNotIn("testing_agent", tools)
        self.assertNotIn("code_reviewer_agent", tools)
        self.assertNotIn("test_ui", tools)

    def test_parser_known_tools_canonical(self):
        """Verify ToolCallParser.KNOWN_TOOLS has only canonical tool names."""
        from tools.parser import KNOWN_TOOLS
        self.assertIn("get_assets", KNOWN_TOOLS)
        self.assertNotIn("get_assets_tool", KNOWN_TOOLS)
        self.assertIn("invoke_testing_agent", KNOWN_TOOLS)
        self.assertIn("invoke_code_reviewer_agent", KNOWN_TOOLS)
        self.assertNotIn("test_ui", KNOWN_TOOLS)
        self.assertNotIn("design_agent", KNOWN_TOOLS)
    def test_subagent_model_synchronization(self):
        """Verify that all subagents inherit and synchronize with the active main agent model."""
        test_model = "deepseek-r1:14b"
        self.registry.set_model_name(test_model)

        self.assertEqual(self.registry.design_subagent.model_name, test_model)
        self.assertEqual(self.registry.troubleshoot_subagent.model_name, test_model)
        self.assertEqual(self.registry.vision_subagent.model_name, test_model)
        self.assertEqual(self.registry.ui_testing_subagent.model_name, test_model)
        self.assertEqual(self.registry.code_reviewer_subagent.model_name, test_model)

        # Also verify invoker methods maintain synchronization
        another_model = "claude-3-7-sonnet"
        self.registry.set_model_name(another_model)
        self.assertEqual(self.registry.design_subagent.model_name, another_model)
        self.assertEqual(self.registry.troubleshoot_subagent.model_name, another_model)
        self.assertEqual(self.registry.vision_subagent.model_name, another_model)
        self.assertEqual(self.registry.ui_testing_subagent.model_name, another_model)
        self.assertEqual(self.registry.code_reviewer_subagent.model_name, another_model)



class TestDesignSubagent(unittest.TestCase):
    """Unit tests for upgraded autonomous DesignSubagent."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_design_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.registry = ToolRegistry(self.sandbox_path)
        from subagents.design_subagent import DesignSubagent
        self.subagent = DesignSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
        )

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_allowed_tools(self):
        """Verify design subagent is scoped to write_file, get_assets, read_file, and view_bulk."""
        self.assertEqual(
            self.subagent.allowed_tools,
            {"write_file", "get_assets", "read_file", "view_bulk"},
        )
        self.assertNotIn("execute_command", self.subagent.allowed_tools)
        self.assertNotIn("edit_file", self.subagent.allowed_tools)

    def test_autonomous_design_runner_invocation(self):
        """Verify autonomous child runner is invoked and generates design blueprint."""
        with patch("subagents.design_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = "# 🎨 UI/UX Design System Blueprint\n**Aesthetic Direction**: Neon Cyberpunk\n"

            result = self.subagent.generate_layout_blueprint(
                problem_statement="Build a futuristic DJ audio mixer",
                app_type="audio_app",
            )
            mock_runner.run.assert_called_once()
            self.assertIn("Neon Cyberpunk", result)

            # Ensure baseline index.css was created on disk
            css_file = self.sandbox_path / "src" / "index.css"
            self.assertTrue(css_file.exists())
            self.assertIn("--primary", css_file.read_text())

    def test_heuristic_fallback_on_runner_error(self):
        """Verify graceful fallback synthesizing bespoke taste and topology when runner throws an error."""
        with patch("subagents.design_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.side_effect = RuntimeError("Ollama connection refused")

            result = self.subagent.generate_layout_blueprint(
                problem_statement="Crypto trading wealth tracker",
                app_type="fintech",
                theme_preference="warm terracotta",
            )
            self.assertIn("Warm Terracotta", result)
            css_file = self.sandbox_path / "src" / "index.css"
            self.assertTrue(css_file.exists())
            self.assertIn("--primary", css_file.read_text())

    def test_tailwind_directive_preservation(self):
        """Verify that Tailwind directives are never wiped out when generating design systems."""
        css_file = self.sandbox_path / "src" / "index.css"
        css_file.parent.mkdir(parents=True, exist_ok=True)
        css_file.write_text("@tailwind base;\n@tailwind components;\n@tailwind utilities;\n")

        with patch("subagents.design_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.side_effect = RuntimeError("Ollama connection refused")

            result = self.subagent.generate_layout_blueprint(
                problem_statement="E-commerce boutique shop",
                app_type="ecommerce",
            )

            # Check that file still has Tailwind directives
            content = css_file.read_text()
            self.assertIn("@tailwind base;", content)
            self.assertIn("@tailwind components;", content)
            self.assertIn("@tailwind utilities;", content)
            self.assertIn("@layer components", content)
            self.assertIn("--primary", content)

    def test_archetype_component_topology(self):
        """Verify dynamic archetype detection derives tailored components instead of generic StatsGrid."""
        from subagents.design.topology import detect_archetype

        chat_arch = detect_archetype("Team collaboration and direct messaging app", "messaging_chat")
        self.assertEqual(chat_arch["name"], "Messaging & Real-time Collaboration")
        comp_names = [c["name"] for c in chat_arch["components"]]
        self.assertIn("ChatStream.jsx", comp_names)
        self.assertIn("MessageInput.jsx", comp_names)
        self.assertNotIn("StatsGrid.jsx", comp_names)

        canvas_arch = detect_archetype("Vector graphics illustrator and drawing canvas", "canvas_tool")
        self.assertEqual(canvas_arch["name"], "Creative Studio & Interactive Canvas")
        comp_names = [c["name"] for c in canvas_arch["components"]]
        self.assertIn("ToolFloatingDock.jsx", comp_names)
        self.assertIn("InteractiveWorkspace.jsx", comp_names)
        self.assertNotIn("StatsGrid.jsx", comp_names)
class TestCodeReviewerSubagent(unittest.TestCase):
    """Unit tests for CodeReviewerSubagent."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_reviewer_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.registry = ToolRegistry(self.sandbox_path)

        # Create a sample file with security and performance smells
        self.vuln_file = self.sandbox_path / "src" / "api.js"
        self.vuln_file.parent.mkdir(parents=True, exist_ok=True)
        self.vuln_file.write_text("""
const apiKey = "sk-1234567890abcdef12345678";
app.get("/search", (req, res) => {
    const q = "SELECT * FROM users WHERE name = '" + req.query.name + "'";
    eval(req.query.cmd);
    res.send(q);
});
""")
        from subagents.code_reviewer_subagent import CodeReviewerSubagent
        self.subagent = CodeReviewerSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
        )

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_allowed_tools(self):
        """Verify code reviewer subagent is strictly scoped to read-only tools including glob_files."""
        self.assertEqual(
            self.subagent.allowed_tools,
            {"read_file", "view_bulk", "grep_search", "lint_javascript", "glob_files"},
        )
        self.assertNotIn("write_file", self.subagent.allowed_tools)
        self.assertNotIn("edit_file", self.subagent.allowed_tools)
        self.assertNotIn("execute_command", self.subagent.allowed_tools)

    def test_multi_file_discovery(self):
        """Verify multi-file discovery finds components in src/components and routes in server/routes."""
        from subagents.reviewer import StaticSecurityScanner
        comp_dir = self.sandbox_path / "src" / "components"
        comp_dir.mkdir(parents=True, exist_ok=True)
        (comp_dir / "Button.jsx").write_text("export function Button() { return <button>Click</button>; }")

        routes_dir = self.sandbox_path / "server" / "routes"
        routes_dir.mkdir(parents=True, exist_ok=True)
        (routes_dir / "users.js").write_text("router.get('/', (req, res) => res.json([]));")

        discovered = StaticSecurityScanner.discover_code_files(self.sandbox_path)
        self.assertIn("src/components/Button.jsx", discovered)
        self.assertIn("server/routes/users.js", discovered)
        self.assertIn("src/api.js", discovered)

    def test_autonomous_review_runner_invocation(self):
        """Verify autonomous child runner is invoked with target files and focus areas."""
        with patch("subagents.code_reviewer_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = "### 🧐 Code Review & Security Audit\n**Overall Code Quality Score**: 85/100\n- **Security**: SQL Injection detected\n"

            result = self.subagent.review_code(
                target_files=["src/api.js"],
                focus_areas=["security", "correctness"],
            )
            mock_runner.run.assert_called_once()
            self.assertIn("SQL Injection detected", result)

    def test_runner_failure_string_triggers_heuristic_fallback(self):
        """Verify runner error string (e.g. Subagent execution failed...) triggers fallback rather than raw error return."""
        with patch("subagents.code_reviewer_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = "Subagent execution failed due to model error: Connection refused to Ollama"

            result = self.subagent.review_code(
                target_files=["src/api.js"],
                focus_areas=["security"],
            )
            self.assertIn("Code Review & Security Audit", result)
            self.assertNotIn("Subagent execution failed", result)
            self.assertIn("eval()", result)

    def test_template_literal_sql_injection_detection(self):
        """Verify StaticSecurityScanner catches ES6 template literal SQL injection."""
        sql_file = self.sandbox_path / "server" / "db.js"
        sql_file.parent.mkdir(parents=True, exist_ok=True)
        sql_file.write_text("""
app.get("/user/:id", async (req, res) => {
    try {
        const query = `SELECT * FROM accounts WHERE id = ${req.params.id}`;
        res.send(query);
    } catch (e) {
        res.status(500).send(e);
    }
});
""")
        from subagents.reviewer import StaticSecurityScanner
        findings, score = StaticSecurityScanner.scan(self.sandbox_path, ["server/db.js"])
        self.assertTrue(any("template literal interpolation" in f for f in findings))
        self.assertLess(score, 75)

    def test_heuristic_fallback_on_runner_error(self):
        """Verify deterministic heuristic fallback when runner throws an error."""
        with patch("subagents.code_reviewer_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.side_effect = RuntimeError("Model timeout")

            result = self.subagent.review_code(
                target_files=["src/api.js"],
                focus_areas=["security"],
            )
            self.assertIn("Code Review & Security Audit", result)
            self.assertIn("eval()", result)
            self.assertIn("SQL injection", result)
            self.assertIn("hardcoded API secret", result)


class TestUITestingSubagent(unittest.TestCase):
    """Unit tests for upgraded Goal-Driven Autonomous UITestingSubagent."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_ui_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.registry = ToolRegistry(self.sandbox_path)
        from subagents.ui_subagent import UITestingSubagent
        self.subagent = UITestingSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
            max_steps=5,
        )

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_allowed_tools(self):
        """Verify testing subagent is scoped to goal-driven browser actions."""
        expected = {"click", "type", "select", "wait", "assert_text", "navigate", "done"}
        self.assertEqual(self.subagent.allowed_tools, expected)

    def test_clean_and_parse_action(self):
        """Verify action parser handles direct JSON, markdown codeblocks, and raw text."""
        # 1. Plain JSON
        act1 = self.subagent._clean_and_parse_action('{"action": "click", "id": "el_0"}')
        self.assertEqual(act1, {"action": "click", "id": "el_0"})

        # 2. Markdown wrapped JSON
        act2 = self.subagent._clean_and_parse_action('```json\n{"action": "type", "id": "el_1", "text": "hello"}\n```')
        self.assertEqual(act2, {"action": "type", "id": "el_1", "text": "hello"})

        # 3. Embedded text with JSON
        act3 = self.subagent._clean_and_parse_action('I will click now: {"action": "click", "id": "el_2"}')
        self.assertEqual(act3, {"action": "click", "id": "el_2"})

        # 4. Invalid text
        act4 = self.subagent._clean_and_parse_action('I am not sure what to do.')
        self.assertIsNone(act4)

    def test_console_log_noise_filtering(self):
        """Verify Emergent-style console log noise filter."""
        from subagents.testing.session import PlaywrightBrowserSession
        session = PlaywrightBrowserSession(headless=True)

        # Noisy logs should be skipped
        self.assertTrue(session._should_skip_log("Using fallback translation for language en"))
        self.assertTrue(session._should_skip_log("https://us-assets.i.posthog.com/static/array.js 403"))
        self.assertTrue(session._should_skip_log("Failed to load resource: fonts.googleapis.com"))

        # Real errors should NOT be skipped
        self.assertFalse(session._should_skip_log("Uncaught TypeError: Cannot read property 'map' of undefined"))
        self.assertFalse(session._should_skip_log("HTTP 500 Internal Server Error at /api/users"))

    def test_dom_observer_formatting(self):
        """Verify DOMObserver formats elements and errors cleanly."""
        from subagents.testing.observer import DOMObserver

        obs = {
            "url": "http://localhost:3000",
            "title": "Test App",
            "elements": [
                {"id": "el_0", "tag": "button", "type": "button", "text": "Submit", "testid": "btn-submit"},
                {"id": "el_1", "tag": "input", "type": "text", "text": "", "name": "username"},
            ],
            "dom_errors": ["Invalid credentials"],
        }

        formatted = DOMObserver.format_observation_for_llm(
            observation=obs,
            step=1,
            max_steps=5,
            console_errors=["[ERROR] 401 Unauthorized"],
            previous_action_result="Clicked el_0",
        )

        self.assertIn("[Step 1/5]", formatted)
        self.assertIn("Test App", formatted)
        self.assertIn("Invalid credentials", formatted)
        self.assertIn("[el_0] <button> \"Submit\"", formatted)
        self.assertIn("testid='btn-submit'", formatted)
        self.assertIn("401 Unauthorized", formatted)

    def test_connection_error_handling(self):
        """Verify graceful error reporting when preview URL is unreachable."""
        with patch("subagents.ui_subagent.PlaywrightBrowserSession") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.start.return_value = (False, "Connection refused at 127.0.0.1:9999")

            report = self.subagent.run_ui_test("http://localhost:9999", "Check page")
            self.assertIn("UI Test Failed: Connection Error", report)
            self.assertIn("Connection refused", report)

    def test_autonomous_interaction_loop_success(self):
        """Verify multi-turn autonomous interaction loop and structured report."""
        with patch("subagents.ui_subagent.PlaywrightBrowserSession") as mock_session_cls, \
             patch("subagents.ui_subagent.DOMObserver") as mock_observer, \
             patch("ollama.Client") as mock_ollama_cls:

            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.start.return_value = (True, "")
            mock_session.console_errors = []
            mock_session.network_failures = []
            mock_session.actions_executed = ["Clicked 'el_0' (Click login button)"]

            mock_observer.observe.return_value = {
                "url": "http://localhost:5173",
                "title": "Welcome Dashboard",
                "elements": [{"id": "el_0", "tag": "button", "type": "button", "text": "Login"}],
                "dom_errors": [],
            }
            mock_observer.format_observation_for_llm.return_value = "Observation prompt"

            mock_client = MagicMock()
            mock_ollama_cls.return_value = mock_client

            # Step 1: click login, Step 2: done
            mock_client.chat.side_effect = [
                {"message": {"content": '{"action": "click", "id": "el_0", "reason": "Click login button"}'}},
                {"message": {"content": '{"action": "done", "status": "PASSED", "report": "Login flow verified successfully."}'}},
            ]

            report = self.subagent.run_ui_test("http://localhost:5173", "Test login")

            self.assertIn("UI Test Report — ✅ PASSED", report)
            self.assertIn("Welcome Dashboard", report)
            self.assertIn("Login flow verified successfully.", report)
            mock_session.execute_action.assert_called_once()
            mock_session.close.assert_called()

    def test_deterministic_smoke_fallback_on_llm_error(self):
        """Verify fallback to deterministic smoke test when LLM errors out."""
        with patch("subagents.ui_subagent.PlaywrightBrowserSession") as mock_session_cls, \
             patch("subagents.ui_subagent.DOMObserver") as mock_observer, \
             patch("ollama.Client") as mock_ollama_cls:

            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.start.return_value = (True, "")
            mock_session.console_errors = []
            mock_session.network_failures = []
            mock_session.actions_executed = []

            mock_observer.observe.return_value = {
                "url": "http://localhost:5173",
                "title": "App Title",
                "elements": [{"id": "el_0", "tag": "button", "type": "button", "text": "Get Started"}],
                "dom_errors": [],
            }
            mock_observer.format_observation_for_llm.return_value = "Observation prompt"

            mock_client = MagicMock()
            mock_ollama_cls.return_value = mock_client
            mock_client.chat.side_effect = RuntimeError("Ollama connection refused")

            report = self.subagent.run_ui_test("http://localhost:5173", "Smoke test")

            self.assertIn("Automated Deterministic Smoke Test (Resilient Fallback)", report)
            self.assertIn("App Title", report)
            self.assertIn("Get Started", report)
            mock_session.close.assert_called()


class TestVisionExpertSubagent(unittest.TestCase):
    """Unit tests for upgraded Goal-Driven Autonomous VisionExpertSubagent."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_vision_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.registry = ToolRegistry(self.sandbox_path)
        from subagents.vision_subagent import VisionExpertSubagent
        self.subagent = VisionExpertSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
            max_iterations=4,
        )

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_allowed_tools(self):
        """Verify vision subagent is scoped to read_file, grep_search, view_bulk, and get_assets."""
        expected = {"read_file", "grep_search", "view_bulk", "get_assets"}
        self.assertEqual(self.subagent.allowed_tools, expected)
        self.assertNotIn("write_file", self.subagent.allowed_tools)
        self.assertNotIn("edit_file", self.subagent.allowed_tools)
        self.assertNotIn("execute_command", self.subagent.allowed_tools)

    def test_autonomous_vision_runner_invocation(self):
        """Verify autonomous child runner is invoked with task description and returns structured report."""
        with patch("subagents.vision_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = """# 👁️ Vision & Aesthetic Review Report
**Design Intent**: Futuristic Audio Station
**Target Component**: `src/App.jsx`
**Overall Visual Quality Score**: **92/100**
**Status**: [APPROVED]
"""
            report = self.subagent.critique_ui(
                target_component_or_file="src/App.jsx",
                design_intent="Futuristic Audio Station",
            )
            mock_runner.run.assert_called_once()
            self.assertIn("Vision & Aesthetic Review Report", report)
            self.assertIn("92/100", report)

    def test_static_vision_analyzer_detection(self):
        """Verify StaticVisionAnalyzer detects font absence, raw hex, unstyled buttons, and placeholder images."""
        from subagents.vision.analyzer import StaticVisionAnalyzer

        # Create files with aesthetic issues
        src_dir = self.sandbox_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        (self.sandbox_path / "index.html").write_text("<!DOCTYPE html><html><body><div id='root'></div></body></html>")
        (src_dir / "index.css").write_text("body { margin: 0; }")
        (src_dir / "App.jsx").write_text("""
export default function App() {
  return (
    <div className="grid grid-cols-3">
      <button>Click Me</button>
      <input type="text" />
      <span style={{ color: '#ff0000' }}>Error</span>
      <img src="https://via.placeholder.com/150" alt="avatar" />
    </div>
  );
}
""")

        analysis = StaticVisionAnalyzer.analyze(self.sandbox_path, target_component_or_file="src/App.jsx")
        findings_text = " ".join(analysis["findings"])

        self.assertIn("Missing Google Font Pairings", findings_text)
        self.assertIn("Missing Semantic Theme Tokens", findings_text)
        self.assertIn("Static Grid Columns Detected", findings_text)
        self.assertIn("Unstyled Raw Button Elements", findings_text)
        self.assertIn("Unstyled Input Fields", findings_text)
        self.assertIn("Generic Placeholder Images Detected", findings_text)

        report = StaticVisionAnalyzer.generate_report(analysis, design_intent="Modern SaaS")
        self.assertIn("Vision & Aesthetic Review Report", report)
        self.assertIn("Recommended Polish Actions", report)

    def test_heuristic_fallback_on_runner_error(self):
        """Verify fallback to deterministic static analyzer when LLM runner encounters an error."""
        with patch("subagents.vision_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.side_effect = RuntimeError("Ollama connection timeout")

            # Create baseline files
            src_dir = self.sandbox_path / "src"
            src_dir.mkdir(parents=True, exist_ok=True)
            (src_dir / "index.css").write_text(":root { --primary: #6366f1; --bg-main: #0f172a; }")
            (src_dir / "App.jsx").write_text("export default function App() { return <div>App</div>; }")

            report = self.subagent.critique_ui(
                target_component_or_file="src/App.jsx",
                design_intent="Clean Dashboard",
            )
            self.assertIn("Vision & Aesthetic Review Report", report)
            self.assertIn("Score Breakdown", report)
            self.assertIn("src/App.jsx", report)


if __name__ == "__main__":
    unittest.main()





